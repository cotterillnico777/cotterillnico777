#!/usr/bin/env python3
"""Anbieter-Werkzeug: Schlüsselpaar erzeugen und Lizenzdateien ausstellen.

  python3 lizenz_ausstellen.py schluessel --privat /sicherer/ort/privat.pem --eintragen
      erzeugt ein Ed25519-Schlüsselpaar und trägt den öffentlichen Schlüssel in
      rechnungsbruecke/lizenz.py ein (ohne --eintragen wird er nur ausgegeben).
      privat.pem NIEMALS weitergeben oder ins Repository einchecken; offline sichern
      (z. B. verschlüsselter USB-Stick + Passwortmanager). Ohne ihn können keine Lizenzen
      mehr ausgestellt werden; ein neuer Schlüssel macht alle bisherigen Lizenzen ungültig.

  python3 lizenz_ausstellen.py ausstellen --privat privat.pem --kunde "Firma GmbH" \\
      --tarif business --bis 2027-12-31 --ziel lizenz.json
"""
import argparse
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from rechnungsbruecke.lizenz import TARIFE, nutzdaten  # noqa: E402


def oeffentlich_b64(privat: Ed25519PrivateKey) -> str:
    roh = privat.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(roh).decode()


def lade_privat(pfad: Path) -> Ed25519PrivateKey:
    return serialization.load_pem_private_key(Path(pfad).read_bytes(), password=None)


def ausstellen(privat: Ed25519PrivateKey, kunde: str, tarif: str, bis: str) -> dict:
    if tarif not in TARIFE:
        raise SystemExit(f"Unbekannter Tarif '{tarif}', erlaubt: {', '.join(TARIFE)}")
    signatur = privat.sign(nutzdaten(kunde, tarif, bis))
    return {"kunde": kunde, "tarif": tarif, "gueltig_bis": bis, "signatur": base64.b64encode(signatur).decode()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="befehl", required=True)
    s = sub.add_parser("schluessel")
    s.add_argument("--privat", required=True, type=Path)
    s.add_argument("--eintragen", action="store_true", help="öffentlichen Schlüssel in rechnungsbruecke/lizenz.py eintragen")
    a = sub.add_parser("ausstellen")
    a.add_argument("--privat", required=True, type=Path)
    a.add_argument("--kunde", required=True)
    a.add_argument("--tarif", required=True, choices=list(TARIFE))
    a.add_argument("--bis", required=True, help="Ablaufdatum JJJJ-MM-TT")
    a.add_argument("--ziel", required=True, type=Path)
    args = ap.parse_args()

    if args.befehl == "schluessel":
        if args.privat.exists():
            raise SystemExit(f"{args.privat} existiert bereits, wird nicht überschrieben")
        privat = Ed25519PrivateKey.generate()
        args.privat.write_bytes(privat.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                     serialization.NoEncryption()))
        args.privat.chmod(0o600)
        print(f"Privater Schlüssel: {args.privat} (geheim halten, sicher sichern)")
        zeile = f'OEFFENTLICHER_SCHLUESSEL = "{oeffentlich_b64(privat)}"'
        print(zeile)
        if args.eintragen:
            ziel = Path(__file__).resolve().parent.parent / "rechnungsbruecke" / "lizenz.py"
            inhalt = ziel.read_text(encoding="utf-8")
            if inhalt.count('OEFFENTLICHER_SCHLUESSEL = "REPLACE_WITH_YOUR_ED25519_PUBLIC_KEY"') != 1:
                raise SystemExit(f"{ziel}: Platzhalter nicht gefunden – ist bereits ein Schlüssel eingetragen?")
            ziel.write_text(inhalt.replace('OEFFENTLICHER_SCHLUESSEL = "REPLACE_WITH_YOUR_ED25519_PUBLIC_KEY"', zeile),
                            encoding="utf-8")
            print(f"Eingetragen in {ziel}. Danach Tests ausführen und das Windows-Paket neu bauen.")
    else:
        lizenz = ausstellen(lade_privat(args.privat), args.kunde, args.tarif, args.bis)
        args.ziel.write_text(json.dumps(lizenz, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Lizenz für {args.kunde} ({args.tarif}, bis {args.bis}) geschrieben: {args.ziel}")


if __name__ == "__main__":
    main()
