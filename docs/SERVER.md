# Bot auf einem Server betreiben (Paper)

Ziel: Der Paper-Bot läuft 24/7 auf einem kleinen Linux-Server statt auf dem Mac. Er startet
nach Abstürzen und Server-Neustarts automatisch neu. Es werden **keine API-Schlüssel**
gebraucht; der Dienst kann technisch nur Paper handeln.

Dauer: ca. 30–60 Minuten, einmalig. Kosten: kleinster Cloud-Server, ca. 4–6 € pro Monat.

## 1. SSH-Schlüssel auf dem Mac erstellen (einmalig)

Damit meldest du dich später ohne Passwort, aber sicher am Server an. Im Terminal auf dem Mac:

```bash
ls ~/.ssh/id_ed25519.pub || ssh-keygen -t ed25519 -C "quantbot"
cat ~/.ssh/id_ed25519.pub
```

Bei `ssh-keygen` dreimal Enter drücken. Die ausgegebene Zeile (`ssh-ed25519 AAAA… quantbot`)
ist dein **öffentlicher** Schlüssel – den kopierst du im nächsten Schritt. Die Datei ohne `.pub`
ist geheim und bleibt auf dem Mac.

## 2. Server mieten

Beispiel Hetzner Cloud (Deutschland), andere Anbieter funktionieren genauso:

1. Konto anlegen auf hetzner.com → Cloud → neues Projekt → **Server hinzufügen**
2. Standort: Nürnberg, Falkenstein oder Helsinki
3. Image: **Ubuntu 24.04**
4. Typ: kleinste Variante (Shared vCPU, 2 GB RAM reichen)
5. SSH-Schlüssel: **hinzufügen** → die Zeile aus Schritt 1 einfügen
6. Erstellen → die angezeigte **IPv4-Adresse** notieren (z. B. `203.0.113.10`)

Im Folgenden steht `SERVER-IP` für diese Adresse.

## 3. Server einrichten

Auf dem Mac:

```bash
ssh root@SERVER-IP
```

Beim ersten Mal fragt SSH „Are you sure you want to continue connecting?“ → `yes`.
Jetzt bist du auf dem Server (die Zeile beginnt mit `root@…`). Dort:

```bash
curl -fsSL https://raw.githubusercontent.com/cotterillnico777/cotterillnico777/claude/hopeful-goldberg-w1ms4b/deploy/setup_server.sh -o setup_server.sh
bash setup_server.sh
```

Das dauert einige Minuten. Am Ende steht „Fertig“ und „Konfiguration ok: ['ema_trend',
'squeeze_breakout']“. Das Skript richtet Benutzer, Firewall, automatische Sicherheitsupdates,
Python und den Dienst ein – startet den Bot aber noch nicht.

## 4. Paper-Konto vom Mac übernehmen

Damit das Paper Trading nahtlos weiterläuft (gleiches Konto, gleiche Trades), wird das
Journal vom Mac auf den Server kopiert.

1. **Paper-Bot auf dem Mac stoppen:** im Terminal-Fenster, in dem er läuft, **Ctrl+C**.
   Wichtig: Es darf nie auf Mac und Server gleichzeitig ein Bot mit demselben Konto laufen.
2. In einem neuen Terminal-Fenster **auf dem Mac**:

```bash
cd ~/Desktop/cotterillnico777
scp state/quantbot_paper.sqlite* quantbot@SERVER-IP:cotterillnico777/state/
```

Wer neu anfangen will, lässt diesen Schritt weg – dann startet ein neues Paper-Konto mit 10.000.

## 5. Starten und prüfen

Wieder auf dem Server (`ssh root@SERVER-IP`):

```bash
qb start
qb status
qb logs
```

`qb status` sollte „Dienst: läuft“ und kurz danach „Heartbeat: ok“ zeigen.

## Alltag

Vom Mac aus, ohne sich extra anzumelden:

```bash
ssh root@SERVER-IP qb status
```

Alle Kurzbefehle (auf dem Server):

| Befehl | Wirkung |
|---|---|
| `qb status` | Dienst, Kontostand, Drawdown, Kill Switch |
| `qb positions` | offene Positionen |
| `qb trades` | abgeschlossene Trades |
| `qb analyze` | ausführliche Auswertung |
| `qb logs` / `qb follow` | Protokoll ansehen / live mitlesen |
| `qb stop` / `qb start` / `qb restart` | Dienst steuern |
| `qb kill` | Notbremse: alles schließen, nichts Neues |
| `qb update` | neuesten Code holen und Bot neu starten |

Der Server darf neu starten (z. B. nach Sicherheitsupdates) – der Bot startet von selbst wieder.

## Auswertung nach 30 Tagen

Für `compare` (Backtest gegen Paper) werden die lokalen Marktdaten gebraucht; das läuft auf
dem Mac. Dazu das Journal **vom** Server holen:

```bash
cd ~/Desktop/cotterillnico777
scp quantbot@SERVER-IP:cotterillnico777/state/quantbot_paper.sqlite state/server_paper.sqlite
python -m quantbot data download --timeframes 4h
python -m quantbot -c configs/paper_ensemble_4h.yaml compare --journal state/server_paper.sqlite
```

## Sicherheit

- Anmeldung nur mit SSH-Schlüssel, Passwort-Login ist abgeschaltet; Firewall lässt nur SSH zu.
- Der Bot läuft als eigener Benutzer ohne Root-Rechte und darf nur in sein Verzeichnis schreiben.
- Für Paper gibt es keine Schlüssel auf dem Server. Für einen späteren Live-Betrieb kämen sie in
  `/home/quantbot/cotterillnico777/.env` (Rechte 600), mit **nur Futures-Handel, ohne
  Auszahlungsrecht** und auf die Server-IP beschränkt. Live wird nie automatisch aktiviert
  (siehe LIVE_TRADING.md); dieser Dienst startet ausdrücklich `--mode paper`.
- Ob die Börse Konten bzw. Derivatehandel für deinen Wohnsitz erlaubt, ist vor einem
  Live-Betrieb gesondert zu prüfen. Für Paper werden nur öffentliche Kursdaten abgerufen.

## Server wieder loswerden

Bei Hetzner: Server → Löschen. Vorher bei Bedarf das Journal per `scp` sichern (siehe oben).
