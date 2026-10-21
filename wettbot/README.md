# Wettbot – Value-Betting für Fußball (Fokus Champions League)

Ein Bot, der **Value-Wetten** sucht: Wetten, bei denen die beste verfügbare Quote
höher ist, als sie nach unserer Wahrscheinlichkeitsschätzung sein müsste.
Er tippt nicht „wer gewinnt“, sondern rechnet, **wo der Preis falsch ist** – und
setzt dann kontrolliert (Viertel-Kelly mit harten Limits).

> **Ehrlicher Hinweis vorweg:** Kein Wettbot kann Gewinn garantieren.
> Buchmacher haben 3–8 % Marge eingebaut; die Mehrheit aller Wettenden verliert
> langfristig. Dieser Bot ist so gebaut, dass er nur bei messbarem Vorteil wettet,
> lieber gar nicht als schlecht wettet und dass man **nachprüfen** kann, ob er
> wirklich einen Vorteil hat (Journal + Closing Line Value). Setze nur Geld, dessen
> Verlust du verkraften kannst. Hilfe bei Spielsucht: BZgA 0800 1 37 27 00
> (kostenlos, anonym) · www.check-dein-spiel.de

## So funktioniert er

```
Ergebnisse (openfootball)        Quoten (CSV oder The Odds API)
          │                                  │
          ▼                                  ▼
 Dixon-Coles-Modell              margenbereinigte Marktwahrscheinlichkeit
 (Teams + Ligastärke,            (Power-Methode, Mittel über Buchmacher)
  Zeitgewichtung)                            │
          │                                  │
          └──── p = 35 % Modell + 65 % Markt ┘
                         │
          EV = p × beste Quote − 1  ≥ 3 % ?
          Modell & Markt nicht > 12 Pkt. uneinig?
                         │
          Einsatz = ¼-Kelly, max. 2 %/Wette, 3 %/Spiel, 10 %/Tag
                         │
                 Journal → Abrechnung → ROI & CLV
```

**Modell** (`wettbot/model.py`): Hierarchisches Poisson-/Dixon-Coles-Modell.
Jedes Team hat Angriff/Abwehr relativ zu seiner Liga; jede Liga hat einen
Stärke-Offset, der über Europapokalspiele geschätzt wird (so wird z. B. Premier
League gegen Eredivisie vergleichbar). Ältere Spiele zählen weniger, Teams mit
wenig Daten werden zum Ligamittel gezogen, Länder ohne Ligadaten (Norwegen,
Ukraine, …) zu einem gemeinsamen Kleinligen-Mittel. Eigenes Torniveau für
Europapokalspiele. Daten: ~12 500 Spiele aus 17 Ligen + CL/EL/ECL seit 2022.

**Warum Mischung mit dem Markt?** Der Markt kennt Verletzungen, Aufstellungen
und Rotation – das Modell nicht. Ein reines Statistikmodell, das blind gegen den
Markt wettet, verliert in Top-Wettbewerben fast immer. Value entsteht hier aus
(1) **Line-Shopping** – immer die beste Quote mehrerer Buchmacher nehmen – und
(2) der unabhängigen Modellmeinung als Zünglein an der Waage. Weicht das Modell
stark ab, ist das ein **Warnsignal** (fehlende Information), kein Value.

## Schnellstart

```bash
cd wettbot
pip install -r requirements.txt
python -m wettbot fetch                      # Ergebnisdaten laden

# Variante A: Quoten-CSV (siehe data/odds/2026-10-21.csv)
python -m wettbot picks --odds data/odds/2026-10-21.csv --bankroll 500 --report reports/heute.md

# Variante B: Live-Quoten von ~40 Buchmachern (kostenloser Key, 500 Abrufe/Monat)
export ODDS_API_KEY=...                       # https://the-odds-api.com
python -m wettbot picks --api --date 2026-11-04 --bankroll 500 --save

python -m wettbot settle                     # nach dem Spieltag: abrechnen
python -m wettbot report                     # Bilanz: Gewinn, ROI, CLV
python -m wettbot backtest                   # Prognosegüte prüfen
python -m wettbot ranking --top 30           # Teamstärken
```

Alle Grenzwerte sind per Option änderbar, z. B. `--min-edge 0.05`,
`--kelly-fraction 0.2`, `--model-weight 0.3`, `--max-disagreement 0.10`.

### Ablauf an einem CL-Abend

1. Nachmittags: `picks --api --date <heute> --save` → Wetten + Einsätze.
2. Kurz vor Anpfiff: Quote beim genannten Buchmacher prüfen. Ist sie gefallen,
   den Befehl erneut laufen lassen – fällt die Wette raus, **nicht** setzen.
3. Schlussquote in `data/ledger.csv` (Spalte `schlussquote`) eintragen.
4. Ergebnisse in `data/results_manual.csv` anhängen, `settle` ausführen.

## Ist der Bot profitabel? So prüfst du es

* **Backtest** (Walk-Forward, CL 2024/25 – heute, 420+ Spiele, Modell sieht nie
  die Zukunft): 1X2-Log-Loss ≈ 0,896 gegenüber 0,996 für die Basisrate.
  Das Modell hat also echte Vorhersagekraft – für den Markt reicht das allein
  aber nicht. Eine **Rendite**-Simulation braucht historische Quoten; die waren in
  der Entwicklungsumgebung nicht abrufbar.
* **Closing Line Value**: Liegt die genommene Quote im Schnitt über der
  Schlussquote (`report` → `clv` > 0), hast du einen echten Vorteil. Das ist nach
  ~100 Wetten aussagekräftiger als der Kontostand nach 100 Wetten.
* **Erwartung realistisch halten**: Selbst gute Value-Bettor erzielen 2–5 % ROI
  auf den Umsatz, mit langen Durststrecken. Bei ¼-Kelly und ~2 % Einsatz pro
  Wette schwankt die Bankroll trotzdem deutlich.

## Grenzen

* Keine Verletzungs-/Aufstellungsdaten → genau dafür die Marktmischung und der
  Abweichungs-Filter.
* openfootball wird mit Verzögerung aktualisiert; aktuelle CL-Ergebnisse stehen
  in `data/results_manual.csv` und sollten nach jedem Spieltag ergänzt werden.
* Kontolimits: Buchmacher beschränken erfolgreiche Kunden. Line-Shopping über
  mehrere Konten ist Teil der Strategie.
* Wetten ist in Deutschland nur bei Anbietern mit deutscher Lizenz (GGL-Whitelist)
  legal; dort gilt u. a. ein Einzahlungslimit von 1 000 €/Monat.

## Dateien

| Pfad | Inhalt |
|---|---|
| `wettbot/data.py` | Download & Parsing (football.json, Football.TXT) |
| `wettbot/names.py` | Teamnamen vereinheitlichen |
| `wettbot/model.py` | Dixon-Coles-Modell |
| `wettbot/markets.py` | Märkte (1X2, Über/Unter, BTTS), Margenbereinigung |
| `wettbot/value.py` | Value-Erkennung, Kelly, Limits |
| `wettbot/ledger.py` | Journal, Abrechnung, ROI, CLV |
| `wettbot/backtest.py` | Walk-Forward-Backtest |
| `data/results_manual.csv` | CL 2026/27 Ergebnisse (manuell) |
| `data/odds/` | Quoten-Snapshots |
| `reports/` | Tagesberichte |
