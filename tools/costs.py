"""Kostenmodell: Gebühren, Spread und Slippage für jeden Trade.

    python3 tools/costs.py ev SYM ENTRY RISK EV_SIM [EV_HIST]
        Erwartungswert nach Kosten (in R), Entscheidung JA/NEIN
    python3 tools/costs.py trade SYM QTY ENTRY EXIT [long|short] [HOURS_OVER_FUNDING]
        Kosten in $ und Netto-Ergebnis eines Trades

Annahmen (vorsichtig, alle Orders als Market/Stop-Market, also Taker):
- US-Aktien (Alpaca): keine Provision. Je Seite 0,03 % für halben Spread und
  Slippage. Beim Verkauf SEC-Gebühr (0,00278 %) und FINRA-TAF (0,0166 Cent
  pro Aktie, max. 8,30 $).
- Krypto (Bitget USDT-M Perpetual-Futures, 1x Hebel): Taker-Gebühr 0,06 % je
  Seite. Spread und Slippage je Seite 0,02 % (BTC, ETH) bzw. 0,05 % (übrige
  Coins). Funding um 16:00 UTC (11:00 Uhr New York im Winter): pauschal
  0,01 % als Kosten, weil ein Trade nach 9:45 Uhr meist darüber hinaus läuft.
Kosten in R = Kosten pro Einheit / Risiko pro Einheit. Getradet wird nur,
wenn der Erwartungswert der Simulation NACH Kosten positiv ist.
"""
import sys

CRYPTO_MAJORS = {"BTC-USD", "ETH-USD"}
TAKER = 0.0006
FUNDING = 0.0001
STOCK_SLIP = 0.0003
SEC_FEE = 0.0000278
TAF_PER_SHARE, TAF_MAX = 0.000166, 8.30


def is_crypto(sym):
    return sym.upper().endswith("-USD")


def side_pct(sym):
    """Anteil vom Kurs, den eine Seite (Einstieg oder Ausstieg) kostet."""
    if is_crypto(sym):
        return TAKER + (0.0002 if sym.upper() in CRYPTO_MAJORS else 0.0005)
    return STOCK_SLIP


def round_trip_per_unit(sym, entry, exit_=None, qty=1, short=False):
    """Kosten pro Einheit für Ein- und Ausstieg (Dollar)."""
    exit_ = entry if exit_ is None else exit_
    c = side_pct(sym) * (entry + exit_)
    if is_crypto(sym):
        c += FUNDING * entry
    else:
        sell_px = entry if short else exit_
        c += SEC_FEE * sell_px + min(TAF_PER_SHARE, TAF_MAX / max(qty, 1))
    return c


def cost_r(sym, entry, risk):
    return round_trip_per_unit(sym, entry) / risk


def cmd_ev(sym, entry, risk, ev_sim, ev_hist=None):
    entry, risk, ev_sim = float(entry), float(risk), float(ev_sim)
    c = cost_r(sym, entry, risk)
    net = ev_sim - c
    line = "%s Kosten %.3f R (%.3f %% vom Kurs) | EV Sim %+.3f -> netto %+.3f" % (
        sym, c, 100 * round_trip_per_unit(sym, entry) / entry, ev_sim, net)
    if ev_hist is not None:
        line += " | Rückblick %+.3f -> netto %+.3f" % (float(ev_hist), float(ev_hist) - c)
    print(line + " | " + ("JA" if net > 0 else "NEIN"))


def trade(sym, qty, entry, exit_, side="long", funding=True):
    qty, entry, exit_ = float(qty), float(entry), float(exit_)
    short = side == "short"
    gross = qty * (exit_ - entry) * (-1 if short else 1)
    per = side_pct(sym) * (entry + exit_)
    cost = qty * per
    if is_crypto(sym):
        if funding:
            cost += qty * FUNDING * entry
    else:
        sell_px = entry if short else exit_
        cost += qty * SEC_FEE * sell_px + min(qty * TAF_PER_SHARE, TAF_MAX)
    return round(gross, 2), round(cost, 2), round(gross - cost, 2)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "ev":
        cmd_ev(*a[1:])
    elif a and a[0] == "trade":
        side = a[5] if len(a) > 5 else "long"
        fund = (float(a[6]) > 0) if len(a) > 6 else True
        g, c, n = trade(a[1], a[2], a[3], a[4], side, fund)
        print("%s brutto %+.2f $ | Kosten %.2f $ | netto %+.2f $" % (a[1], g, c, n))
    else:
        print(__doc__)
