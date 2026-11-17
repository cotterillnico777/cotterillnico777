"""Schneidet Versprecher aus den Sprachaufnahmen und kürzt lange Pausen.
Aufruf: python3 tools/schnitt.py   → ton-geschnitten/*.wav (für: TON=ton-geschnitten python3 tools/finale.py)

Die Schnittstellen stammen aus einer Abschrift mit Wort-Zeitmarken. Jeder Schnitt wird
auf die leiseste Stelle in der Nähe gelegt und mit einer kurzen Blende versehen, damit
kein Knacken entsteht."""
import glob, os, subprocess, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TON = os.path.join(HERE, "..", "ton")
OUT = os.path.join(HERE, "..", "ton-geschnitten")
SR = 48000

# Datei-Nummer → Liste (von, bis) in Sekunden, die herausfallen. Kommentar = was geschnitten wird.
SCHNITTE = {
    "02": [(54.90, 56.16)],            # „10 Dollar pro Verlust pro Trade“ → „10 Dollar Verlust pro Trade“
    "06": [(16.70, 17.62),             # „ein Prozent schlechtere Ausführung“ → „schlechtere Ausführung“
           (39.36, 40.70)],            # doppeltes „wäre nach dieser Regel“
    "07": [(35.42, 36.90, .06)],       # „Das war kein Kandidat,“ (Versprecher: kein statt ein)
                                       # → „Am selben Tag noch Fortinet, der nur ganz knapp über der Kostengrenze lag …“
    "08": [(8.50, 13.30)],             # „1,83 $ vor Kosten, 1,17 $ danach“ (Versprecher: 1,83 statt 1,33)
    "09": [(17.66, 19.60),             # „nach Kosten 15 Cent Verlust“ (Versprecher: 15 statt 5 Cent)
           (58.30, 58.76)],            # „80 Cent von Prozent“ → „80 Prozent“
    "11": [(20.56, 21.20),             # „Mehr Chance auf mehr deutlich Risiko“ → „Mehr Chance, mehr Risiko“
           (21.38, 21.78, .05)],
}
PAUSE_MAX = 0.75      # längere Pausen werden auf diese Länge gekürzt
PAUSE_AB = 1.0        # … sofern sie länger als das sind

def load(f):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", f, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"])
    return np.frombuffer(raw, np.float32).copy()

def energy(x, win=int(.02 * SR)):
    n = len(x) // win
    return np.sqrt((x[:n * win].reshape(n, win) ** 2).mean(1) + 1e-12), win

def snap(x, t, rad=.15):
    """Verschiebt einen Schnittpunkt auf das leiseste 20-ms-Fenster in der Nähe."""
    e, win = energy(x); i = int(t * SR / win); r = int(rad * SR / win)
    lo, hi = max(0, i - r), min(len(e), i + r + 1)
    return (lo + int(np.argmin(e[lo:hi]))) * win + win // 2

def cut(x, spans, fade=int(.03 * SR)):
    pts = [(snap(x, s[0], *s[2:]), snap(x, s[1], *s[2:])) for s in sorted(spans)]
    parts, pos = [], 0
    for a, b in pts:
        if a > pos: parts.append(x[pos:a])
        pos = max(pos, b)
    parts.append(x[pos:])
    out = parts[0]
    for p in parts[1:]:                                   # weiche Übergänge
        f = min(fade, len(out), len(p))
        if f: out = np.concatenate([out[:-f], out[-f:] * np.linspace(1, 0, f) + p[:f] * np.linspace(0, 1, f), p[f:]])
        else: out = np.concatenate([out, p])
    return out

def shorten_pauses(x):
    e, win = energy(x); thr = max(np.percentile(e, 20) * 2.5, 10 ** (-48 / 20))
    quiet = e < thr; spans, i = [], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]: j += 1
            if (j - i) * win / SR > PAUSE_AB and i > 0 and j < len(quiet):
                keep = int(PAUSE_MAX * SR / win)
                spans.append(((i + keep // 2) * win / SR, (j - keep // 2) * win / SR))
            i = j
        else: i += 1
    return cut(x, spans) if spans else x

def main():
    os.makedirs(OUT, exist_ok=True)
    for f in sorted(glob.glob(os.path.join(TON, "*.*"))):
        nr = os.path.basename(f)[:2]
        if not nr.isdigit(): continue
        x = load(f); y = cut(x, SCHNITTE.get(nr, [])) if SCHNITTE.get(nr) else x
        y = shorten_pauses(y)
        dst = os.path.join(OUT, os.path.splitext(os.path.basename(f))[0] + ".wav")
        with wave.open(dst, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
        print(f"{os.path.basename(dst)}: {len(x) / SR:.1f} s → {len(y) / SR:.1f} s")

if __name__ == "__main__":
    main()
