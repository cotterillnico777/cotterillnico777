# Wettbot – Value-Betting für Fußball (Fokus Champions League)

Ein Bot, der **Value-Wetten** sucht: Wetten, bei denen die beste verfügbare Quote
höher ist, als sie nach unserer Wahrscheinlichkeitsschätzung sein müsste.
Er tippt nicht „wer gewinnt“, sondern rechnet, **wo der Preis falsch ist** – und
setzt dann kontrolliert (Viertel-Kelly mit harten Limits).

> **Ergebnis des Rendite-Backtests (siehe unten):** Mit echten historischen Quoten
> aus 16 Ligen ist **kein dauerhafter Gewinn nachweisbar**. Die beste Einstellung
> lag zwei Jahre lang bei +1,6 % ROI – statistisch nicht von Null unterscheidbar.
> Die ursprüngliche, modellgetriebene Einstellung hätte 86 % der Bankroll verloren.
>
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
          │      p = Markt (Modell nur Veto) ┘
          │                         │
          └──► Veto: Modell muss Wette ebenfalls positiv sehen
               und darf nicht > 12 Pkt. vom Markt abweichen
                         │
          EV = p × beste Quote − 1  ≥ 2 % ?
          beste Quote ≤ 110 % des Buchmacher-Medians?
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

**Warum nur Veto?** Der Markt kennt Verletzungen, Aufstellungen und Rotation –
das Modell nicht. Im Rendite-Backtest hat *jedes* Modellgewicht > 0 die Rendite
verschlechtert (siehe unten). Übrig bleibt **Line-Shopping**: die faire
Wahrscheinlichkeit kommt aus dem margenbereinigten Markt, gewettet wird nur, wo
ein einzelner Buchmacher klar mehr zahlt – und auch das Modell nicht widerspricht.

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
git clone https://github.com/xgabora/Club-Football-Match-Data-2000-2025 /tmp/odds
python -m wettbot roi-backtest --matches /tmp/odds/data/Matches.csv   # Rendite-Test
python -m wettbot ranking --top 30           # Teamstärken
```

Alle Grenzwerte sind per Option änderbar, z. B. `--min-edge 0.05`,
`--kelly-fraction 0.2`, `--max-price-ratio 1.05`, `--max-disagreement 0.10`.

### Ablauf an einem CL-Abend

1. Nachmittags: `picks --api --date <heute> --save` → Wetten + Einsätze.
2. Kurz vor Anpfiff: Quote beim genannten Buchmacher prüfen. Ist sie gefallen,
   den Befehl erneut laufen lassen – fällt die Wette raus, **nicht** setzen.
3. Schlussquote in `data/ledger.csv` (Spalte `schlussquote`) eintragen.
4. Ergebnisse in `data/results_manual.csv` anhängen, `settle` ausführen.

## Ist der Bot profitabel? Was die Daten sagen

### 1. Prognosegüte (CL, Walk-Forward 2024/25 – heute, 423 Spiele)

| Markt | Modell (Log-Loss) | Basisrate |
|---|---|---|
| 1X2 | **0,888** | 0,996 |
| Über/Unter 2,5 | 0,633 | 0,641 |
| Beide treffen | 0,675 | 0,686 |

Das Modell hat echte Vorhersagekraft – aber Buchmacher sind besser.

### 2. Rendite mit echten Quoten (`roi-backtest`)

16 Ligen (Top-5 + 2. Ligen, NL, PT, BE, TR, GR, SCO), Okt. 2024 – Sep. 2026,
~16 000 Spiele. Markt = bet365 margenbereinigt, Wettquote = Höchstquote aus ~17
Büchern. Modell wöchentlich neu trainiert, sieht nie die Zukunft. Daten:
[xgabora/Club-Football-Match-Data-2000-2025](https://github.com/xgabora/Club-Football-Match-Data-2000-2025).

| Einstellung | Wetten | ROI (flach) | 95 %-Intervall | 1 000 € werden zu |
|---|---|---|---|---|
| ursprünglich (35 % Modell, EV ≥ 3 %) | 3 740 | **−9,3 %** | −14 % … −5 % | **139 €** |
| nur Modell | 14 678 | −7,1 % | −9 % … −5 % | – |
| **aktuell** (Markt + Modell-Veto, EV ≥ 2 %, Quote ≤ 110 % Median) | 204 | **+1,6 %** | −15 % … +17 % | 1 016 € (Tief 965 €) |

Out-of-sample-Prüfung: Regeln auf 2024/25 gewählt, auf 2025/26 – 2026/27
getestet. Die auf dem Training beste modellgetriebene Regel (+9,6 %) fiel im
Test auf −9,4 % – klassische Überanpassung. Nur die marktbasierte Variante war in
beiden Zeiträumen leicht positiv (+0,3 % / +2,0 %).

**Fazit:** Der Bot verliert in dieser Form kaum Geld und meidet die Fehler, die
typische Tipp-Bots ruinieren – ein nachgewiesener Gewinn ist das nicht. Echte
Vorteile im Fußball brauchen Informationen, die der Markt noch nicht hat
(schnelle Aufstellungs-/Verletzungsnews), oder Zugang zu scharfen Quoten
(Pinnacle, Wettbörsen) als Referenz – beides fehlt in den frei verfügbaren Daten.

Hinweis: Die Höchstquoten im Datensatz sind nicht immer wirklich wettbar
(veraltete Linien, Kontolimits). Wetten mit Höchstquote > 110 % des Marktes
verloren 19 % – deshalb der Filter.

### 3. Selbst nachprüfen: Closing Line Value

Liegt die genommene Quote im Schnitt über der Schlussquote (`report` → `clv` > 0),
ist ein Vorteil wahrscheinlich – das ist nach ~100 Wetten aussagekräftiger als der
Kontostand. Bei negativem CLV: aufhören.

## Grenzen

* Keine Verletzungs-/Aufstellungsdaten → deshalb Markt als Basis und Modell nur als Veto.
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
| `wettbot/backtest.py` | Walk-Forward-Backtest der Prognosegüte |
| `wettbot/roi.py` | Rendite-Backtest mit historischen Quoten |
| `data/results_manual.csv` | CL 2026/27 Ergebnisse (manuell) |
| `data/odds/` | Quoten-Snapshots |
| `reports/` | Tagesberichte |
