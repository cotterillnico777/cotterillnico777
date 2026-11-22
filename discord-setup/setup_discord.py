#!/usr/bin/env python3
"""Richtet den Casino-Community-Discord automatisch ein.

Legt Rollen, Kategorien, Kanäle samt Berechtigungen an, postet Willkommens-,
Regel- und Hilfetexte, aktiviert die Community-Funktionen und erstellt einen
dauerhaften Einladungslink. Mehrfaches Ausführen ist sicher: Vorhandenes wird
anhand des Namens wiederverwendet und aktualisiert, Bot-Texte werden bearbeitet
statt doppelt gepostet.

Aufruf:
    DISCORD_BOT_TOKEN=... python3 setup_discord.py <SERVER_ID>
    python3 setup_discord.py 123 --dry-run      # nur anzeigen, ohne Discord
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("DISCORD_API", "https://discord.com/api/v10")

# ===== Anpassen =====
KANALNAME = "SlotEntdecker"
STREAM_URL = ""        # z. B. https://kick.com/DEINKANAL – leer lassen, solange es keinen gibt
LINKSEITE_URL = ""     # Adresse der Linkseite, sobald sie online ist
TELEGRAM_URL = "https://t.me/slotentdecker"
EMAIL = "slotentdecker@gmail.com"
STREAMZEITEN = "Mo · Mi · Fr ab 21 Uhr"

# Leere Angaben werden in den Texten einfach weggelassen
STREAM_AUF = f" auf {STREAM_URL}" if STREAM_URL else ""
LINK_ZEILEN = "\n".join(z for z, wert in [
    (f"🔗 **Alle Links:** {LINKSEITE_URL}", LINKSEITE_URL),
    (f"✈️ **Telegram:** {TELEGRAM_URL}", TELEGRAM_URL),
    (f"✉️ **Kooperationen:** {EMAIL}", EMAIL),
] if wert)

# ===== Berechtigungs-Bits =====
ADD_REACTIONS = 1 << 6
VIEW_AUDIT_LOG = 1 << 7
KICK = 1 << 1
BAN = 1 << 2
VIEW = 1 << 10
SEND = 1 << 11
MANAGE_MESSAGES = 1 << 13
MUTE_MEMBERS = 1 << 22
MOVE_MEMBERS = 1 << 24
MANAGE_NICKNAMES = 1 << 27
MANAGE_THREADS = 1 << 34
CREATE_PUBLIC_THREADS = 1 << 35
SEND_IN_THREADS = 1 << 38
MODERATE_MEMBERS = 1 << 40

SCHREIBEN = SEND | SEND_IN_THREADS | CREATE_PUBLIC_THREADS
MOD_RECHTE = (KICK | BAN | VIEW_AUDIT_LOG | MANAGE_MESSAGES | MUTE_MEMBERS | MOVE_MEMBERS
              | MANAGE_NICKNAMES | MANAGE_THREADS | MODERATE_MEMBERS)

# Reihenfolge = Hierarchie von oben nach unten
ROLLEN = [
    # (Name, Farbe, Rechte, separat anzeigen, erwähnbar)
    ("👑 Owner", 0xFBBF24, 0, True, False),
    ("🛡️ Moderator", 0xEF4444, MOD_RECHTE, True, False),
    ("🎬 Stream-Team", 0x8B5CF6, 0, True, False),
    ("💎 VIP / Sub", 0x14B8A6, 0, True, False),
    ("✅ Verifiziert 18+", 0x9CA3AF, 0, False, False),
    ("🔔 Live-Ping", 0, 0, False, True),
    ("🎁 Giveaway-Ping", 0, 0, False, True),
]
OWNER, MOD, VERIFIZIERT = "👑 Owner", "🛡️ Moderator", "✅ Verifiziert 18+"

# zugang: public = alle, verified = nur "Verifiziert 18+", team = nur Moderatoren
# altersbeschraenkt: Discord-Flag "Altersbeschränkt" (Pflicht bei Glücksspielinhalten)
STRUKTUR = [
    ("📌 START", "public", False, [
        ("willkommen", "text", True, "Begrüßung und alle Links"),
        ("regeln", "text", True, "Serverregeln – bitte lesen"),
        ("18-plus-bestätigen", "text", True, "Bestätige hier, dass du volljährig bist"),
        ("ankündigungen", "text", True, "Neuigkeiten vom Team"),
        ("rollen-wählen", "text", True, "Benachrichtigungen an- und abschalten"),
    ]),
    ("🔴 STREAM", "verified", True, [
        ("live-jetzt", "text", True, "Automatische Live-Meldungen"),
        ("stream-plan", "text", True, "Wann wir live sind"),
        ("clips", "text", False, "Eure Highlights aus dem Stream"),
        ("big-wins", "text", False, "Gewinn-Screenshots aus dem Stream"),
    ]),
    ("💬 COMMUNITY", "verified", True, [
        ("allgemein", "text", False, "Quatschen über alles"),
        ("slots-talk", "text", False, "Spiele, Features, Anbieter"),
        ("memes", "text", False, "Nur Spaß"),
        ("vorschläge", "text", False, "Ideen für Streams und den Server"),
    ]),
    ("🎁 EVENTS", "verified", True, [
        ("giveaways", "text", True, "Kostenlose Giveaways – Teilnahme ohne Einsatz"),
        ("bonus-hunt-tippspiel", "text", False, "Tippt das Endergebnis – ohne Einsatz"),
        ("turniere", "text", True, "Community-Turniere"),
    ]),
    ("🤝 PARTNER", "verified", True, [
        ("partner-angebote", "text", True, "Werbung – nur 21–6 Uhr, nur GGL-lizenzierte Anbieter"),
    ]),
    ("🛟 HILFE", "public", False, [
        ("verantwortungsvoll-spielen", "text", True, "Hilfe und Beratung – kostenlos und anonym"),
        ("support", "text", True, "Ticket für das Team öffnen"),
    ]),
    ("🔊 VOICE", "verified", False, [
        ("Stream-Talk", "voice", False, None),
        ("Chill", "voice", False, None),
        ("AFK", "voice", False, None),
    ]),
    ("🛡️ TEAM", "team", False, [
        ("mod-chat", "text", False, "Internes Team"),
        ("mod-log", "text", False, "Logs und Discord-Systemmeldungen"),
    ]),
]

# Discord-Standardkanäle eines neuen Servers, die nach dem Umbau weg können
STANDARD_KATEGORIEN = {"textkanäle", "sprachkanäle", "text channels", "voice channels"}
STANDARD_VOICE = {"allgemein", "general", "lounge"}

TEXTE = {
    "willkommen": f"""🎰 **Willkommen in der {KANALNAME} Community!**

Hier triffst du alle, die gern bei Slots, Big Wins und Bonus-Hunts zuschauen.

**So geht's los:**
1️⃣ Lies die Regeln in <#regeln>
2️⃣ Bestätige in <#18-plus-bestätigen>, dass du volljährig bist
3️⃣ Hol dir in <#rollen-wählen> den 🔔 **Live-Ping**, damit du keinen Stream verpasst

🔴 **Live:** {STREAMZEITEN}{STREAM_AUF}
{LINK_ZEILEN}

🔞 Nur ab 18 · Glücksspiel kann süchtig machen · Hilfe: <#verantwortungsvoll-spielen>""",

    "regeln": """**📜 Serverregeln**

**1. Nur ab 18.** Wer minderjährig ist, wird ohne Vorwarnung gebannt.
**2. Respekt.** Keine Beleidigungen, kein Rassismus, keine Hetze, kein Mobbing.
**3. Keine Werbung.** Keine Links zu anderen Servern, Casinos oder Angeboten. Partnerangebote postet nur das Team.
**4. Nur legale Anbieter.** Kein Content und keine Links zu Casinos ohne deutsche Lizenz (GGL-Whitelist).
**5. Keine Geldgeschäfte.** Kein Verleihen oder Leihen von Geld, keine Account-Verkäufe, keine „Signals“ oder „sicheren Strategien“.
**6. Kein Spam.** Keine Massen-Pings, keine Flut von Nachrichten oder Emojis.
**7. Datenschutz.** Keine persönlichen Daten von dir oder anderen posten. Das gilt auch für Kontostände mit Namen.
**8. Discord-Regeln gelten.** Es gelten die Community-Richtlinien von Discord: https://discord.com/guidelines

⚠️ Gewinne im Stream sind Unterhaltung und **nicht repräsentativ**. Glücksspiel kann süchtig machen.
Hilfe gibt es bei **check-dein-spiel.de** und der **BZgA-Hotline 0800 1 37 27 00** (kostenlos und anonym).

Bei Regelverstößen verwarnt, mutet oder bannt das Team nach eigenem Ermessen.""",

    "18-plus-bestätigen": """🔞 **Altersbestätigung**
Dieser Server enthält Glücksspiel-Content und ist **nur für Volljährige**.
Mit Klick auf ✅ bestätigst du, dass du **mindestens 18 Jahre alt** bist und die Regeln akzeptierst.""",

    "rollen-wählen": """🔔 **Benachrichtigungen**
🔔 = Ping, sobald der Stream startet
🎁 = Ping bei neuen Giveaways
Einfach auf das passende Emoji klicken. Nochmal klicken schaltet es wieder ab.""",

    "stream-plan": f"""📅 **Stream-Plan**
🔴 {STREAMZEITEN}{STREAM_AUF}

Änderungen kündigen wir in <#ankündigungen> an.""",

    "partner-angebote": """🤝 **Partner-Angebote**
Hier stellt das Team ausschließlich Anbieter mit deutscher Lizenz (GGL-Whitelist) vor.
Alle Beiträge sind **Werbung** und enthalten Affiliate-Links. Es gelten die Bonusbedingungen des jeweiligen Anbieters.
🔞 Nur ab 18 · Glücksspiel kann süchtig machen · Hilfe: <#verantwortungsvoll-spielen>""",

    "verantwortungsvoll-spielen": """🛟 **Spiel mit Verstand**
• Setz dir vorher ein festes Limit für Zeit und Geld und halte dich daran.
• Spiel nie mit Geld, das du für Miete, Essen oder Rechnungen brauchst.
• Versuch nicht, Verluste zurückzuholen.
• Wenn Spielen kein Spaß mehr macht, hör auf.

**Hilfe, kostenlos und anonym:**
📞 BZgA-Hotline: **0800 1 37 27 00**
🌐 **check-dein-spiel.de**
🚫 Bundesweite Selbstsperre (OASIS): **spielerschutz.de** oder direkt beim Anbieter

Du kannst dem Team jederzeit privat schreiben. Wir hören zu und urteilen nicht.""",
}
ANPINNEN = {"regeln", "verantwortungsvoll-spielen"}


class DiscordFehler(Exception):
    pass


class DiscordAPI:
    def __init__(self, token):
        self.token = token

    def request(self, methode, pfad, body=None):
        daten = json.dumps(body).encode() if body is not None else None
        for _ in range(6):
            req = urllib.request.Request(API + pfad, data=daten, method=methode, headers={
                "Authorization": f"Bot {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "DiscordBot (casino-community-setup, 1.0)",
            })
            try:
                with urllib.request.urlopen(req, timeout=30) as antwort:
                    roh = antwort.read()
                    return json.loads(roh) if roh else None
            except urllib.error.HTTPError as e:
                inhalt = e.read().decode(errors="replace")
                if e.code == 429:
                    warten = float(json.loads(inhalt or "{}").get("retry_after", 2))
                    time.sleep(warten + 0.5)
                    continue
                raise DiscordFehler(f"{methode} {pfad} -> {e.code}: {inhalt}") from None
        raise DiscordFehler(f"{methode} {pfad}: Rate-Limit")


class Probelauf:
    """Simuliert einen leeren Server, damit man den Ablauf ohne Discord sieht."""

    def __init__(self, server_id):
        self.server_id = server_id
        self.zaehler = 1000

    def request(self, methode, pfad, body=None):
        if methode != "GET":
            print(f"    [probe] {methode} {pfad}")
        if pfad == "/users/@me":
            return {"id": "1", "username": "Setup-Bot"}
        if pfad == f"/guilds/{self.server_id}":
            return {"id": self.server_id, "name": "Probe-Server", "owner_id": "2", "features": []}
        if pfad.endswith("/roles") and methode == "GET":
            return [{"id": self.server_id, "name": "@everyone"}]
        if pfad.endswith("/channels") and methode == "GET":
            return []
        if "/messages?" in pfad:
            return []
        if pfad.endswith("/invites"):
            return {"code": "PROBELAUF"}
        if isinstance(body, list):
            return body
        self.zaehler += 1
        return {"id": str(self.zaehler), **(body or {})}


def ueberschreibung(rolle_id, erlauben=0, verbieten=0):
    return {"id": rolle_id, "type": 0, "allow": str(erlauben), "deny": str(verbieten)}


def rechte_fuer(zugang, nur_lesen, server_id, rollen):
    everyone_verbot = SCHREIBEN if nur_lesen else 0
    liste = []
    if zugang in ("verified", "team"):
        everyone_verbot |= VIEW
    liste.append(ueberschreibung(server_id, verbieten=everyone_verbot))
    if zugang == "verified":
        liste.append(ueberschreibung(rollen[VERIFIZIERT], erlauben=VIEW))
    liste.append(ueberschreibung(rollen[MOD], erlauben=VIEW | SCHREIBEN))
    return liste


def art(kanal):
    return {4: "kategorie", 2: "voice", 13: "voice"}.get(kanal["type"], "text")


def main():
    parser = argparse.ArgumentParser(description="Casino-Community-Discord einrichten")
    parser.add_argument("server_id", help="ID des Discord-Servers (Rechtsklick → Server-ID kopieren)")
    parser.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts an Discord senden")
    parser.add_argument("--standardkanaele-behalten", action="store_true",
                        help="Discords Standard-Kategorien und -Sprachkanal nicht löschen")
    args = parser.parse_args()
    sid = args.server_id

    if args.dry_run:
        api = Probelauf(sid)
    else:
        token = os.environ.get("DISCORD_BOT_TOKEN")
        if not token:
            sys.exit("DISCORD_BOT_TOKEN ist nicht gesetzt.")
        api = DiscordAPI(token)

    bot = api.request("GET", "/users/@me")
    server = api.request("GET", f"/guilds/{sid}")
    print(f"Server: {server['name']}  ·  Bot: {bot['username']}\n")

    # ----- Rollen -----
    print("Rollen")
    vorhanden = {r["name"]: r["id"] for r in api.request("GET", f"/guilds/{sid}/roles")}
    rollen = {}
    for name, farbe, rechte, separat, erwaehnbar in ROLLEN:
        if name in vorhanden:
            rollen[name] = vorhanden[name]
            print(f"  = {name}")
            continue
        rolle = api.request("POST", f"/guilds/{sid}/roles", {
            "name": name, "color": farbe, "permissions": str(rechte),
            "hoist": separat, "mentionable": erwaehnbar,
        })
        rollen[name] = rolle["id"]
        print(f"  + {name}")
    # Neue Rollen landen alle auf Position 1 – Hierarchie direkt unter dem Bot festlegen
    api.request("PATCH", f"/guilds/{sid}/roles", [
        {"id": rollen[name], "position": len(ROLLEN) - i} for i, (name, *_) in enumerate(ROLLEN)])

    # ----- Kategorien und Kanäle -----
    print("\nKanäle")
    alle = api.request("GET", f"/guilds/{sid}/channels")
    nach_name = {(k["name"].lower(), art(k)): k for k in alle}
    kanal_ids = {}
    position = 0
    for kat_name, zugang, alter, kanaele in STRUKTUR:
        kat_rechte = rechte_fuer(zugang, False, sid, rollen)
        kat = nach_name.get((kat_name.lower(), "kategorie"))
        if kat:
            api.request("PATCH", f"/channels/{kat['id']}",
                        {"permission_overwrites": kat_rechte, "position": position})
            print(f"  = {kat_name}")
        else:
            kat = api.request("POST", f"/guilds/{sid}/channels", {
                "name": kat_name, "type": 4, "permission_overwrites": kat_rechte, "position": position})
            print(f"  + {kat_name}")
        position += 1
        for name, typ, nur_lesen, thema in kanaele:
            daten = {
                "name": name,
                "parent_id": kat["id"],
                "permission_overwrites": rechte_fuer(zugang, nur_lesen, sid, rollen),
                "nsfw": alter,
                "position": position,
            }
            if typ == "text":
                daten["topic"] = thema
            position += 1
            k = nach_name.get((name.lower(), typ))
            if k:
                api.request("PATCH", f"/channels/{k['id']}", daten)
                print(f"      = {name}")
            else:
                k = api.request("POST", f"/guilds/{sid}/channels",
                                {"type": 2 if typ == "voice" else 0, **daten})
                print(f"      + {name}")
            kanal_ids[name] = k["id"]

    if not args.standardkanaele_behalten:
        uebernommen = set(kanal_ids.values())
        for k in alle:
            weg = (art(k) == "kategorie" and k["name"].lower() in STANDARD_KATEGORIEN) or \
                  (art(k) == "voice" and k["name"].lower() in STANDARD_VOICE and k["id"] not in uebernommen)
            if weg:
                api.request("DELETE", f"/channels/{k['id']}")
                print(f"  - {k['name']} (Discord-Standard entfernt)")

    # ----- Community-Funktionen -----
    print("\nCommunity")
    merkmale = set(server.get("features", []))
    try:
        api.request("PATCH", f"/guilds/{sid}", {
            "verification_level": 2,          # Mittel
            "explicit_content_filter": 2,     # alle Mitglieder scannen
            "default_message_notifications": 1,  # nur Erwähnungen
            "features": sorted(merkmale | {"COMMUNITY"}),
            "rules_channel_id": kanal_ids["regeln"],
            "public_updates_channel_id": kanal_ids["mod-log"],
            "system_channel_id": kanal_ids["willkommen"],
            "preferred_locale": "de",
        })
        print("  ✓ Community, Verifizierung Mittel, Inhaltsfilter für alle")
        api.request("PATCH", f"/channels/{kanal_ids['ankündigungen']}", {"type": 5})
        print("  ✓ #ankündigungen ist jetzt ein Ankündigungskanal")
    except DiscordFehler as e:
        print(f"  ! Community konnte nicht aktiviert werden: {e}")

    # ----- Texte -----
    print("\nTexte")
    for kanal, text in TEXTE.items():
        for name, kid in kanal_ids.items():
            text = text.replace(f"<#{name}>", f"<#{kid}>")
        kid = kanal_ids[kanal]
        nachrichten = api.request("GET", f"/channels/{kid}/messages?limit=50")
        eigene = [m for m in nachrichten if m["author"]["id"] == bot["id"]]
        inhalt = {"content": text, "allowed_mentions": {"parse": []}}
        if eigene:
            nachricht = api.request("PATCH", f"/channels/{kid}/messages/{eigene[-1]['id']}", inhalt)
            print(f"  = #{kanal} aktualisiert")
        else:
            nachricht = api.request("POST", f"/channels/{kid}/messages", inhalt)
            print(f"  + #{kanal}")
        if kanal in ANPINNEN:
            api.request("PUT", f"/channels/{kid}/pins/{nachricht['id']}")

    # ----- Owner-Rollen -----
    for rolle in (OWNER, VERIFIZIERT):
        try:
            api.request("PUT", f"/guilds/{sid}/members/{server['owner_id']}/roles/{rollen[rolle]}")
        except DiscordFehler as e:
            print(f"  ! Rolle {rolle} konnte nicht vergeben werden: {e}")

    # ----- Einladung -----
    einladung = api.request("POST", f"/channels/{kanal_ids['willkommen']}/invites",
                            {"max_age": 0, "max_uses": 0, "unique": False})
    print(f"\nFertig! Dauerhafter Einladungslink: https://discord.gg/{einladung['code']}")


if __name__ == "__main__":
    main()
