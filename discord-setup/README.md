# Discord-Server automatisch einrichten

`setup_discord.py` legt den kompletten Community-Server an: Rollen, Kategorien,
Kanäle mit Berechtigungen (18+-Freischaltung, Nur-Lesen-Kanäle, privater Team-Bereich),
Willkommens-, Regel- und Hilfetexte, Community-Funktionen und einen dauerhaften Einladungslink.
Das Skript kann gefahrlos mehrfach laufen. Vorhandenes wird aktualisiert, nicht verdoppelt.

## Vorbereitung (einmalig, ca. 5 Minuten)

1. **Leeren Server anlegen:** In Discord auf „+“ tippen, dann „Eigenen erstellen“ wählen.
2. **Server-ID kopieren:** Unter Einstellungen → Erweitert den Entwicklermodus einschalten,
   dann Rechtsklick auf den Server → „Server-ID kopieren“.
3. **Bot erstellen:** Auf https://discord.com/developers/applications „New Application“ wählen,
   dann unter „Bot“ → „Reset Token“ den Token kopieren und geheim halten.
4. **Bot einladen:** Diesen Link öffnen und `CLIENT_ID` durch die Application ID ersetzen:
   `https://discord.com/oauth2/authorize?client_id=CLIENT_ID&scope=bot&permissions=8`

## Ausführen

Oben im Skript `KANALNAME`, `STREAM_URL`, `LINKSEITE_URL` und `STREAMZEITEN` anpassen, dann:

```bash
python3 setup_discord.py <SERVER_ID> --dry-run              # nur anzeigen
DISCORD_BOT_TOKEN=... python3 setup_discord.py <SERVER_ID>  # wirklich einrichten
```

## Danach noch von Hand

- **Carl-bot**: Reaktionsrollen auf die Bot-Nachrichten in `#18-plus-bestätigen`
  (✅ → Verifiziert 18+) und `#rollen-wählen` (🔔 → Live-Ping, 🎁 → Giveaway-Ping) legen.
- **Pingcord**: Live-Meldungen für Kick, Twitch und YouTube nach `#live-jetzt` schicken lassen.
- **Ticket Tool** in `#support` einrichten, **GiveawayBot** für `#giveaways` hinzufügen.
- **2FA-Pflicht für Moderation** und **AutoMod** in den Servereinstellungen einschalten.
- Danach dem Setup-Bot die Administrator-Rechte entziehen oder ihn entfernen.
