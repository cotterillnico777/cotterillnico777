"""Erzeugt eine eigene Hintergrundmusik (keine fremden Samples, keine Lizenzfragen)
passend zur Szenenfolge des Videos und mischt sie unter das Probevideo.
Aufruf: python3 tools/musik.py            → ausgabe/musik.wav und ausgabe/probevideo-musik.mp4

Stil: ruhiger Elektro-Beat, 100 BPM, a-Moll (Am – F – C – G).
Die Energie wechselt mit den Szenen: Spannung im Hook, Beat bei den Trades,
Stille vor der Auflösung, Höhepunkt bei der Abstimmung."""
import os, subprocess, wave
import numpy as np

SR = 48000
BPM = 100
BEAT = 60 / BPM
BAR = 4 * BEAT
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "ausgabe")
rng = np.random.default_rng(3)

# Szenenfolge (muss zu tools/alles.sh passen) und Energie je Szene:
# 0 = nur Fläche, 1 = Fläche + Bass, 2 = + Arpeggio + Hi-Hats, 3 = voller Beat
SZENEN = [("hook", 24, 1), ("regeln", 29, 2), ("timemachine", 22, 2), ("tag1", 22, 1),
          ("merck", 24, 3), ("kdp", 22, 3), ("nke", 18, 3), ("kosten", 30, 1),
          ("mrna", 22, 3), ("ftnt", 18, 2), ("nxpi", 18, 3), ("panw", 20, 3), ("gis", 20, 3),
          ("cboe", 18, 2), ("aapl", 17, 2), ("bilanz", 31.5, 3), ("lehren", 27, 1), ("abstimmung", 28, 3)]

def hz(n):  # MIDI-Note → Frequenz
    return 440 * 2 ** ((n - 69) / 12)

# Akkorde je Takt: Am, F, C, G (Grundton, Terz, Quinte)
CHORDS = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]

def smooth_noise(n, k):
    x = rng.standard_normal(n + k)
    return np.convolve(x, np.ones(k) / k, mode="valid")[:n]

def kick():
    t = np.arange(int(.45 * SR)) / SR
    f = 48 + 110 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) * .95

def hat(open_=False):
    t = np.arange(int((.18 if open_ else .05) * SR)) / SR
    n = rng.standard_normal(len(t)); n = n - smooth_noise(len(t), 6)   # grob Hochpass
    return .18 * n * np.exp(-t * (18 if open_ else 70))

def clap():
    t = np.arange(int(.25 * SR)) / SR
    n = smooth_noise(len(t), 3) - smooth_noise(len(t), 30)
    e = np.exp(-t * 22) + .5 * np.exp(-((t - .012) * 400) ** 2)
    return .55 * n / np.abs(n).max() * e

def pluck(f, sec=.28, bright=3):
    t = np.arange(int(sec * SR)) / SR
    y = sum(np.sin(2 * np.pi * f * k * t) / k ** 1.3 * np.exp(-t * (9 + 4 * k)) for k in range(1, bright + 1))
    return y * np.minimum(1, t * 400)

def bass_note(f, sec):
    t = np.arange(int(sec * SR)) / SR
    y = np.sin(2 * np.pi * f * t) + .35 * np.sin(2 * np.pi * 2 * f * t) + .12 * np.sin(2 * np.pi * 3 * f * t)
    return .55 * y * np.minimum(1, t * 200) * np.exp(-t * 2.2)

def pad_chord(notes, sec):
    t = np.arange(int(sec * SR)) / SR
    y = np.zeros_like(t)
    for n in notes:
        for det in (-.12, 0, .12):                       # leicht verstimmt = breiter Klang
            f = hz(n + det)
            for k, a in ((1, 1), (2, .35), (3, .15), (4, .07)):
                y += a * np.sin(2 * np.pi * f * k * t + rng.uniform(0, 6.28))
    env = np.minimum(1, t / .6) * np.minimum(1, (sec - t) / .6)
    return .055 * y * env

def main():
    total = sum(d for _, d, _ in SZENEN)
    N = int(total * SR) + SR * 3
    pad, bass, arp, drums = (np.zeros(N) for _ in range(4))
    duck = np.ones(N)

    # Energie-Kurve (pro Sample), weich überblendet an den Szenengrenzen
    energy = np.zeros(N); pos = 0
    for name, d, e in SZENEN:
        energy[int(pos * SR):int((pos + d) * SR)] = e; pos += d
    energy = np.convolve(energy, np.ones(SR // 2) / (SR // 2), mode="same")

    # Sonderstellen: Stille vor der Auflösung, Schlussakkord
    starts = {}; pos = 0
    for name, d, _ in SZENEN:
        starts[name] = pos; pos += d
    reveal = starts["bilanz"] + 4.0                       # Ziffern landen bei 1.000,80 $
    stille = (starts["bilanz"] + .2, reveal)

    def add(buf, i, x, a=1.0):
        if i >= N: return
        n = min(len(x), N - i); buf[i:i + n] += x[:n] * a
    # Klänge einmal vorberechnen
    PAD = [pad_chord([n - 12 for n in ch] + [ch[0]], BAR + .6) for ch in CHORDS]
    BASS = [bass_note(hz(ch[0] - 24), BEAT / 2 * .95) for ch in CHORDS]
    PL = {}
    K, C, H0, H1 = kick(), clap(), hat(), hat(True)
    D = np.exp(-np.arange(int(.25 * SR)) / SR * 14)
    bars = int(total / BAR) + 1
    for b in range(bars):
        t0 = b * BAR; ci = b % 4; ch = CHORDS[ci]
        add(pad, int(t0 * SR), PAD[ci])
        for s in range(8):                                # Bass in Achteln
            add(bass, int((t0 + s * BEAT / 2) * SR), BASS[ci], 1 if s % 2 == 0 else .6)
        seq = [ch[0], ch[1], ch[2], ch[0] + 12, ch[2], ch[1], ch[2], ch[0] + 12]
        for s in range(16):                               # Arpeggio in Sechzehnteln
            n = seq[s % 8] + 12
            if n not in PL: PL[n] = pluck(hz(n))
            add(arp, int((t0 + s * BEAT / 4) * SR), PL[n], .16 if s % 4 == 0 else .1)
        for q in range(4):                                # Schlagzeug
            ts = t0 + q * BEAT; i = int(ts * SR)
            on = energy[min(i, N - 1)] >= 2.5
            if on:
                add(drums, i, K)
                n = min(len(D), N - i)
                if n > 0: duck[i:i + n] = np.minimum(duck[i:i + n], 1 - .45 * D[:n])
                if q in (1, 3): add(drums, i, C, .8)
            for h in range(2):
                add(drums, int((ts + h * BEAT / 2) * SR), H1 if (h == 1 and q == 3) else H0, 1 if h else .6)

    g = lambda lo, hi: np.clip((energy - lo) / (hi - lo), 0, 1)
    mix = pad * (.8 + .2 * g(0, 1)) + bass * g(.5, 1.2) * duck + arp * g(1.5, 2) * duck + drums * g(1.8, 2.6)

    # Stille vor der Auflösung, dann Einschlag
    i1, i2 = int(stille[0] * SR), int(stille[1] * SR)
    fade = np.ones(N); fade[i1:i2] = np.linspace(.35, .0, i2 - i1); mix *= fade
    mix[i2:] *= np.minimum(1, (np.arange(N - i2) / SR) / .05)

    # Schluss: ausklingen lassen
    tN = int(total * SR); out = int(3 * SR)
    mix[tN - out:tN] *= np.linspace(1, 0, out) ** 1.5; mix = mix[:tN]

    mix = mix / np.abs(mix).max() * .9
    st = np.stack([mix, mix], 1)
    st[:, 0] += .02 * np.roll(arp[:tN], 240); st[:, 1] += .02 * np.roll(arp[:tN], -240)   # etwas Breite
    os.makedirs(OUT, exist_ok=True)
    wav = os.path.join(OUT, "musik.wav")
    with wave.open(wav, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(st, -1, 1) * 32767).astype("<i2").tobytes())

    # Unter das Probevideo mischen: Musik leise (−12 dB, ohne Stimme), Effekte bleiben vorne
    src = os.path.join(OUT, "probevideo.mp4"); dst = os.path.join(OUT, "probevideo-musik.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-i", wav, "-filter_complex",
                    "[1:a]volume=-12dB[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", dst], check=True)
    print("fertig:", dst)

if __name__ == "__main__":
    main()
