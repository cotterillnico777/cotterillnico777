"""Lokale grafische Oberfläche (im Browser) für Anwender ohne Kommandozeile.

Der Server lauscht nur auf 127.0.0.1. Schutz gegen Zugriffe fremder Webseiten:
- jede API-Anfrage braucht den Kopf `X-RB-Token` mit dem Sitzungsschlüssel aus der ausgelieferten Seite
  (fremde Seiten können diesen Kopf ohne CORS-Freigabe nicht setzen, und wir geben keine frei),
- der Host-Kopf muss 127.0.0.1 oder localhost sein (Schutz vor DNS-Rebinding).

Arbeitsordner (Standard ~/Rechnungsbruecke):
  stammdaten.json, mapping.json (optional), eingang/ (hochgeladene Exporte), ausgabe/JJJJ-MM/ (E-Rechnungen),
  gelesen/ (Ansichten eingegangener Rechnungen), gelesen/buchungsliste.csv mit Buchungsregister und
  gelesen/quarantaene/ (nicht bestandene Eingangsrechnungen mit Begründung)
"""
import io
import json
import secrets
import tempfile
import threading
import webbrowser
import zipfile
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .ansicht import als_html, buchungszeilen
from .csv_import import ImportFehler, Stammdaten
from .eingang import BuchungsFehler, buche, in_quarantaene, pruefe_eingang
from .leser import LeseFehler, xml_aus_datei
from .lizenz import LizenzFehler, Nutzung, aktuelle_lizenz, datenverzeichnis, pruefe_lizenzdatei
from .regeln import RegelFehler, aktuelles_regelwerk, einrichten
from .standards import XRECHNUNG_VERSION, ZUGFERD_PROFIL
from .verarbeitung import FORMATE, dateiname, konvertiere

SEITE = Path(__file__).resolve().parent / "oberflaeche.html"
MAX_UPLOAD = 50 * 1024 * 1024
STAMMDATEN_VORLAGE = {
    "verkaeufer": {"name": "", "strasse": "", "plz": "", "ort": "", "land": "DE", "ust_id": "", "steuernummer": "",
                   "registernummer": "", "email": "", "kontakt_name": "", "kontakt_telefon": "", "kontakt_email": ""},
    "bank": {"iban": "", "bic": "", "kontoinhaber": ""},
    "zahlungsziel_tage": 14, "ust_satz": 19, "kleinunternehmer": False,
    "zahlungsbedingungen": "Zahlbar innerhalb von {tage} Tagen ohne Abzug",
}


class Anfragefehler(Exception):
    def __init__(self, status: int, text: str):
        super().__init__(text)
        self.status = status


class Arbeitsordner:
    def __init__(self, pfad: Path, ohne_offizielle_pruefung: bool = False):
        self.pfad = Path(pfad).expanduser()
        self.ohne_offizielle_pruefung = ohne_offizielle_pruefung
        for unter in ("eingang", "ausgabe", "gelesen"):
            (self.pfad / unter).mkdir(parents=True, exist_ok=True)

    stammdaten = property(lambda self: self.pfad / "stammdaten.json")
    mapping = property(lambda self: self.pfad / "mapping.json")
    buchungsliste = property(lambda self: self.pfad / "gelesen" / "buchungsliste.csv")

    def ausgabe_monat(self) -> Path:
        return self.pfad / "ausgabe" / datetime.now().strftime("%Y-%m")

    def mapping_daten(self) -> dict | None:
        return json.loads(self.mapping.read_text(encoding="utf-8")) if self.mapping.exists() else None

    def sicherer_pfad(self, relativ: str) -> Path:
        """Nur Dateien unterhalb von ausgabe/ und gelesen/ dürfen ausgeliefert werden."""
        ziel = (self.pfad / relativ).resolve()
        for erlaubt in (self.pfad / "ausgabe", self.pfad / "gelesen"):
            if ziel.is_relative_to(erlaubt.resolve()) and ziel.is_file():
                return ziel
        raise Anfragefehler(HTTPStatus.NOT_FOUND, "Datei nicht gefunden")


def _status(ordner: Arbeitsordner) -> dict:
    try:
        lizenz = aktuelle_lizenz()
        nutzung = Nutzung(lizenz)
        liz = {"kunde": lizenz.kunde, "tarif": lizenz.tarif, "limit": lizenz.limit,
               "verbraucht": nutzung.verbraucht,
               "gueltig_bis": lizenz.gueltig_bis.isoformat() if lizenz.gueltig_bis else None}
    except LizenzFehler as e:
        liz = {"fehler": str(e)}
    try:
        werk = aktuelles_regelwerk()
        regeln = werk.beschreibung if werk else None
        regelfehler = None
    except RegelFehler as e:
        regeln, regelfehler = None, str(e)
    return {
        "version": __version__, "xrechnung": XRECHNUNG_VERSION, "zugferd": ZUGFERD_PROFIL,
        "arbeitsordner": str(ordner.pfad), "stammdaten_vorhanden": ordner.stammdaten.exists(),
        "mapping_vorhanden": ordner.mapping.exists(), "lizenz": liz, "regeln": regeln,
        "regelfehler": regelfehler, "ohne_offizielle_pruefung": ordner.ohne_offizielle_pruefung,
    }


def _speichere_upload(ordner: Arbeitsordner, name: str, daten: bytes) -> Path:
    stempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    pfad = ordner.pfad / "eingang" / f"{stempel}_{dateiname(Path(name).name) or 'export.csv'}"
    pfad.write_bytes(daten)
    return pfad


def _konvertieren(ordner: Arbeitsordner, daten: bytes, name: str, format: str, nur_pruefen: bool) -> dict:
    if format not in FORMATE:
        raise Anfragefehler(HTTPStatus.BAD_REQUEST, "Unbekanntes Format")
    if not ordner.stammdaten.exists():
        raise Anfragefehler(HTTPStatus.CONFLICT, "Bitte zuerst unter „Einstellungen“ die Firmendaten speichern.")
    try:
        stamm = Stammdaten.laden(ordner.stammdaten)
        werk = aktuelles_regelwerk()
        lizenz = aktuelle_lizenz()
    except (ImportFehler, RegelFehler, LizenzFehler) as e:
        raise Anfragefehler(HTTPStatus.CONFLICT, str(e)) from None
    if nur_pruefen:
        with tempfile.TemporaryDirectory() as tmp:
            pfad = Path(tmp) / "export.csv"
            pfad.write_bytes(daten)
            erg = konvertiere(pfad, stamm, Path(tmp) / "aus", lizenz, format, ordner.mapping_daten(), werk,
                              ordner.ohne_offizielle_pruefung, nur_pruefen=True)
    else:
        pfad = _speichere_upload(ordner, name, daten)
        erg = konvertiere(pfad, stamm, ordner.ausgabe_monat(), lizenz, format, ordner.mapping_daten(), werk,
                          ordner.ohne_offizielle_pruefung)
    return {
        "ok": erg.ok,
        "rechnungen": erg.rechnungen,
        "fehler": erg.fehler,
        "hinweise": erg.hinweise,
        "dateien": [str(p.relative_to(ordner.pfad)) for p in erg.erzeugt + erg.berichte],
        "ohne_offizielle_pruefung": werk is None,
    }


def _lesen(ordner: Arbeitsordner, daten: bytes, name: str, buchen: bool, bestaetigt: bool) -> dict:
    """Prüft eine Eingangsrechnung; fehlerhafte kommen in die Quarantäne, gebucht wird nur nach Freigabe."""
    quarantaene = ordner.pfad / "gelesen" / "quarantaene"
    with tempfile.TemporaryDirectory() as tmp:
        pfad = Path(tmp) / (dateiname(Path(name).name) or "rechnung.xml")
        pfad.write_bytes(daten)
        try:
            werk = aktuelles_regelwerk()
            pruefung = pruefe_eingang(xml_aus_datei(pfad), werk, ordner.buchungsliste, ordner.ohne_offizielle_pruefung)
        except RegelFehler as e:
            raise Anfragefehler(HTTPStatus.CONFLICT, str(e)) from None
        except (LeseFehler, ValueError) as e:
            ablage = in_quarantaene(quarantaene, name, daten, [str(e)])
            raise Anfragefehler(HTTPStatus.UNPROCESSABLE_ENTITY,
                                f"{e} (in Quarantäne abgelegt: {ablage.relative_to(ordner.pfad)})") from None
    r = pruefung.rechnung
    html = als_html(r, pruefung)
    ansicht = ordner.pfad / "gelesen" / f"{dateiname(r.verkaeufer)[:40]}_{dateiname(r.nummer)}.html"
    ansicht.write_text(html, encoding="utf-8")
    antwort = {**pruefung.als_dict(), "html": html, "buchungen": buchungszeilen(r), "gebucht": False,
               "quarantaene": None, "ansicht": str(ansicht.relative_to(ordner.pfad))}
    if pruefung.status != "bestanden":
        antwort["quarantaene"] = str(in_quarantaene(quarantaene, name, daten, pruefung.befunde, pruefung)
                                     .relative_to(ordner.pfad))
    if buchen:
        try:
            buche(pruefung, ordner.buchungsliste, bestaetigt)
        except BuchungsFehler as e:
            raise Anfragefehler(HTTPStatus.CONFLICT, str(e)) from None
        antwort["gebucht"] = True
    return antwort


def _zip(ordner: Arbeitsordner, dateien: list[str]) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in dateien:
            pfad = ordner.sicherer_pfad(rel)
            z.write(pfad, pfad.name)
    return puffer.getvalue()


def baue_handler(ordner: Arbeitsordner, token: str, port_ref: list):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"Rechnungsbruecke/{__version__}"

        def log_message(self, *args):  # keine Zugriffslogs auf der Konsole
            pass

        # --- Hilfen ---
        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            return host in (f"127.0.0.1:{port_ref[0]}", f"localhost:{port_ref[0]}")

        def _senden(self, status: int, inhalt: bytes, typ: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", typ)
            self.send_header("Content-Length", str(len(inhalt)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(inhalt)

        def _json(self, status: int, daten) -> None:
            self._senden(status, json.dumps(daten, ensure_ascii=False).encode("utf-8"),
                         "application/json; charset=utf-8")

        def _koerper(self) -> bytes:
            laenge = int(self.headers.get("Content-Length") or 0)
            if laenge > MAX_UPLOAD:
                raise Anfragefehler(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Datei ist zu groß (max. 50 MB)")
            return self.rfile.read(laenge)

        def _pruefen(self) -> bool:
            if not self._host_ok():
                self._json(HTTPStatus.FORBIDDEN, {"fehler": "Ungültiger Host"})
                return False
            if self.path.startswith("/api/") and not secrets.compare_digest(
                    self.headers.get("X-RB-Token", ""), token):
                self._json(HTTPStatus.FORBIDDEN, {"fehler": "Sitzung ungültig. Bitte die Seite neu laden."})
                return False
            return True

        # --- Routen ---
        def do_GET(self):
            if not self._pruefen():
                return
            url = urlparse(self.path)
            q = parse_qs(url.query)
            try:
                if url.path == "/":
                    seite = SEITE.read_text(encoding="utf-8").replace("__RB_TOKEN__", token)
                    self._senden(HTTPStatus.OK, seite.encode("utf-8"), "text/html; charset=utf-8",
                                 {"Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                                  "script-src 'self' 'unsafe-inline'; frame-src 'self'; img-src 'self' data:"})
                elif url.path == "/api/status":
                    self._json(HTTPStatus.OK, _status(ordner))
                elif url.path == "/api/stammdaten":
                    daten = (json.loads(ordner.stammdaten.read_text(encoding="utf-8"))
                             if ordner.stammdaten.exists() else STAMMDATEN_VORLAGE)
                    self._json(HTTPStatus.OK, daten)
                elif url.path == "/api/mapping":
                    self._json(HTTPStatus.OK, ordner.mapping_daten() or {})
                elif url.path == "/api/datei":
                    pfad = ordner.sicherer_pfad(q.get("pfad", [""])[0])
                    typ = {".pdf": "application/pdf", ".xml": "application/xml", ".json": "application/json",
                           ".html": "text/html; charset=utf-8", ".csv": "text/csv; charset=utf-8"}.get(
                        pfad.suffix.lower(), "application/octet-stream")
                    self._senden(HTTPStatus.OK, pfad.read_bytes(), typ,
                                 {"Content-Disposition": f'attachment; filename="{pfad.name}"'})
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"fehler": "Nicht gefunden"})
            except Anfragefehler as e:
                self._json(e.status, {"fehler": str(e)})

        def do_POST(self):
            if not self._pruefen():
                return
            url = urlparse(self.path)
            q = parse_qs(url.query)
            name = q.get("name", ["upload"])[0]
            try:
                daten = self._koerper()
                if url.path in ("/api/pruefen", "/api/erzeugen"):
                    self._json(HTTPStatus.OK, _konvertieren(ordner, daten, name, q.get("format", ["xrechnung"])[0],
                                                            nur_pruefen=url.path == "/api/pruefen"))
                elif url.path == "/api/lesen":
                    self._json(HTTPStatus.OK, _lesen(ordner, daten, name, q.get("buchen", ["0"])[0] == "1",
                                                     q.get("bestaetigt", ["0"])[0] == "1"))
                elif url.path == "/api/zip":
                    inhalt = _zip(ordner, json.loads(daten)["dateien"])
                    self._senden(HTTPStatus.OK, inhalt, "application/zip",
                                 {"Content-Disposition": 'attachment; filename="e-rechnungen.zip"'})
                elif url.path == "/api/stammdaten":
                    neu = json.loads(daten)
                    with tempfile.TemporaryDirectory() as tmp:  # erst prüfen, dann speichern
                        probe = Path(tmp) / "s.json"
                        probe.write_text(json.dumps(neu, ensure_ascii=False), encoding="utf-8")
                        Stammdaten.laden(probe)
                    ordner.stammdaten.write_text(json.dumps(neu, indent=2, ensure_ascii=False), encoding="utf-8")
                    self._json(HTTPStatus.OK, {"gespeichert": True})
                elif url.path == "/api/mapping":
                    neu = json.loads(daten)
                    if not isinstance(neu, dict) or not all(isinstance(v, str) for v in neu.values()):
                        raise Anfragefehler(HTTPStatus.BAD_REQUEST, "Zuordnung muss ein JSON-Objekt aus Texten sein")
                    if neu:
                        ordner.mapping.write_text(json.dumps(neu, indent=2, ensure_ascii=False), encoding="utf-8")
                    elif ordner.mapping.exists():
                        ordner.mapping.unlink()
                    self._json(HTTPStatus.OK, {"gespeichert": True})
                elif url.path == "/api/regeln":
                    with tempfile.TemporaryDirectory() as tmp:
                        quelle = Path(tmp) / (dateiname(Path(name).name) or "regeln.zip")
                        quelle.write_bytes(daten)
                        werk = einrichten(quelle)
                    self._json(HTTPStatus.OK, werk.beschreibung)
                elif url.path == "/api/lizenz":
                    with tempfile.TemporaryDirectory() as tmp:
                        probe = Path(tmp) / "lizenz.json"
                        probe.write_bytes(daten)
                        lizenz = pruefe_lizenzdatei(probe)
                    datenverzeichnis().mkdir(parents=True, exist_ok=True)
                    (datenverzeichnis() / "lizenz.json").write_bytes(daten)
                    self._json(HTTPStatus.OK, {"tarif": lizenz.tarif, "kunde": lizenz.kunde})
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"fehler": "Nicht gefunden"})
            except Anfragefehler as e:
                self._json(e.status, {"fehler": str(e)})
            except (ImportFehler, RegelFehler, LizenzFehler, ValueError, KeyError) as e:
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"fehler": str(e)})

    return Handler


def erstelle_server(ordner: Path, port: int = 8765, ohne_offizielle_pruefung: bool = False):
    """Erzeugt den Server (noch nicht gestartet). Bei belegtem Port wird ein freier gewählt."""
    arbeits = Arbeitsordner(ordner, ohne_offizielle_pruefung)
    token = secrets.token_urlsafe(24)
    port_ref = [port]
    handler = baue_handler(arbeits, token, port_ref)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError:
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port_ref[0] = server.server_address[1]
    server.daemon_threads = True
    return server, token


def starte(ordner: Path, port: int = 8765, browser: bool = True, ohne_offizielle_pruefung: bool = False) -> int:
    server, _ = erstelle_server(ordner, port, ohne_offizielle_pruefung)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Rechnungsbrücke läuft unter {url}  (Arbeitsordner: {Path(ordner).expanduser()})")
    print("Beenden mit Strg+C.")
    if browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0

