# Meme-Account auf X: Posts vorbereiten und veröffentlichen

Werkzeug: `python -m xposter`. Ablauf: **Entwurf → Freigabe durch dich → Veröffentlichung**.
Ohne Freigabe wird nichts gepostet. Schlüssel liegen nur in `.env` (wird nicht committet).

## Spielregeln (im Programm eingebaut)

- Blockiert: Kursversprechen und Kaufaufforderungen („100x“, „guaranteed“, „buy now“, „risk-free“ …)
  und Contract-Adressen. Der Account ist Humor über Meme-Coin-Kultur, kein Werbekanal.
- Hinweis bei Cashtags (`$XYZ`): bewusst prüfen, ob ein konkreter Coin erwähnt werden soll.
  Wenn du einen erwähnten Coin hältst, gehört das offengelegt.
- Höchstens 4 Posts pro 24 Stunden, mindestens 90 Minuten Abstand (anpassbar).
- Pro Aufruf von `post-due` wird höchstens **ein** Post veröffentlicht.

## Einrichtung (einmalig)

1. **Account anlegen** für die Memes (eigener Account, nicht dein privater).
2. **Als automatisiert kennzeichnen** (X-Regel für Bot-Posts): auf X unter
   Einstellungen → Dein Account → Kontoinformationen → *Automatisierung* deinen privaten Account
   als verwaltenden Account eintragen. (Menünamen können sich ändern.)
3. **Entwicklerzugang:** mit dem Meme-Account auf **developer.x.com** anmelden, Projekt und App
   anlegen. Abrechnung: Pay-per-use (Guthaben aufladen; ein Post kostet laut Fachseiten ca. 1–1,5 Cent,
   bitte auf der Preisseite prüfen).
4. In der App unter *User authentication settings*:
   - App permissions: **Read and write**
   - Type of App: *Web App, Automated App or Bot*
   - Callback URL / Website: beliebige gültige Adresse, z. B. `https://example.com`
5. Unter *Keys and tokens*:
   - **API Key and Secret** (Consumer Keys) erzeugen
   - **Access Token and Secret** erzeugen – **erst nachdem** „Read and write“ gesetzt ist,
     sonst haben die Token nur Leserechte (Fehler 403 beim Posten)
6. In `~/Desktop/cotterillnico777/.env` eintragen (Datei mit TextEdit öffnen):
   ```
   X_API_KEY=...
   X_API_SECRET=...
   X_ACCESS_TOKEN=...
   X_ACCESS_SECRET=...
   ```
7. Prüfen:
   ```bash
   python -m xposter whoami
   ```
   → „Verbunden als @deinaccount“

## Täglicher Ablauf

```bash
python -m xposter import xposter/drafts.yaml   # neue Entwürfe übernehmen (doppelte werden übersprungen)
python -m xposter list --status draft          # Entwürfe ansehen (--full für den ganzen Text)
python -m xposter approve 3 7                  # freigeben
python -m xposter approve 5 --at "2026-11-03 18:30"   # freigeben für einen Zeitpunkt (deutsche Zeit)
python -m xposter reject 4                     # verwerfen
python -m xposter edit 6 "neuer Text"          # ändern (danach erneut freigeben)
python -m xposter add "eigener Post"           # eigenen Entwurf anlegen
python -m xposter post-due --dry-run           # zeigen, was als Nächstes gepostet würde
python -m xposter post-due                     # nächsten fälligen Post veröffentlichen
python -m xposter list --status posted         # mit Link zum Post
```

Fehlgeschlagene Posts bekommen den Status `failed` mit Fehlermeldung und können nach Behebung
erneut freigegeben werden.

## Kosten im Blick

Nur Posten (ohne Mitlesen) bei 3 Posts/Tag: ca. 1 $ pro Monat. Teuer wird erst das Lesen fremder
Posts (ca. 5 $ je 1.000), das dieses Werkzeug bewusst nicht tut.
