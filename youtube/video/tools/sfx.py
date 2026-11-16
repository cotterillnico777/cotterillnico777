"""Erzeugt Soundeffekte synthetisch (keine fremden Samples, keine Lizenzfragen)
und mischt sie zu den Zeitpunkten einer Szene.
Aufruf: python3 tools/sfx.py cues.json DAUER_SEKUNDEN out.wav
cues.json: [[zeit, "name"], ...]; Namen: whoosh, swish, pop, alert, win, loss, flat, tick, riser, candle, heart, cash, buzz, sub"""
import json, sys, wave
import numpy as np

SR = 48000
rng = np.random.default_rng(7)

def t_(sec): return np.arange(int(sec * SR)) / SR

def lowpass(x, cutoff):
    """Einpoliger Tiefpass; cutoff darf ein Array (zeitabhängig) sein."""
    cutoff = np.broadcast_to(cutoff, x.shape)
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x); acc = 0.0
    for i in range(len(x)):
        acc = (1 - a[i]) * x[i] + a[i] * acc
        y[i] = acc
    return y

def env(n, attack, release):
    e = np.ones(n); a = int(attack * SR); r = int(release * SR)
    if a: e[:a] = np.linspace(0, 1, a) ** 2
    if r: e[-r:] *= np.linspace(1, 0, r) ** 2
    return e

def whoosh(sec=.7, f0=300, f1=4000):
    t = t_(sec); n = rng.standard_normal(len(t))
    sweep = f0 * (f1 / f0) ** (np.sin(np.pi * t / sec))     # hoch und wieder runter
    y = lowpass(n, sweep) - lowpass(n, sweep * .25)            # grob ein Bandpass
    return .9 * y / np.abs(y).max() * np.sin(np.pi * t / sec) ** 1.5

def pop():
    t = t_(.18); f = 900 * np.exp(-t * 18) + 280
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 26)
    return .8 * y

def tick():
    t = t_(.05); return .35 * np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 120)

def alert():
    out = np.zeros(int(.5 * SR))
    for k, f in enumerate((740, 554)):
        t = t_(.16); b = np.sin(2 * np.pi * f * t) + .3 * np.sin(2 * np.pi * 2 * f * t)
        s = int(k * .17 * SR); out[s:s + len(t)] += .45 * b * env(len(t), .005, .08)
    return out

def impact(sec=.9, f=55):
    t = t_(sec)
    body = np.sin(2 * np.pi * f * t * (1 + .6 * np.exp(-t * 12))) * np.exp(-t * 5)
    hit = lowpass(rng.standard_normal(len(t)), 1800) * np.exp(-t * 40)
    return .9 * body + .7 * hit / max(1e-9, np.abs(hit).max())

def bell(freq, sec=1.8):
    t = t_(sec); y = np.zeros_like(t)
    for ratio, amp, dec in ((1, 1, 2.2), (2.76, .45, 3.5), (5.4, .25, 5), (8.9, .12, 7)):
        y += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t * dec)
    return y * env(len(t), .002, .05)

def win():
    out = np.zeros(int(2.2 * SR)); imp = impact(); out[:len(imp)] += imp
    for k, f in enumerate((1046.5, 1318.5, 1568.0)):        # C6, E6, G6 nacheinander
        b = bell(f); s = int((.04 + k * .07) * SR); out[s:s + len(b)] += .22 * b
    return out

def loss():
    out = np.zeros(int(1.4 * SR)); imp = impact(1.1, 45); out[:len(imp)] += imp
    t = t_(1.0); f = 220 * np.exp(-t * .9)
    saw = 2 * ((np.cumsum(f) / SR) % 1) - 1
    d = lowpass(saw, 900) * env(len(t), .01, .5) * .6
    s = int(.03 * SR); out[s:s + len(d)] += d
    return out

def flat():
    out = np.zeros(int(1.6 * SR)); imp = .45 * impact(.5, 70); out[:len(imp)] += imp
    b = bell(659.3, 1.4); s = int(.03 * SR); out[s:s + len(b)] += .25 * b
    return out

def riser(sec=1.1):
    t = t_(sec); n = rng.standard_normal(len(t))
    y = lowpass(n, 300 * (20 ** (t / sec)))
    tone = np.sin(2 * np.pi * np.cumsum(180 * (6 ** (t / sec))) / SR)
    return (.5 * y / np.abs(y).max() + .25 * tone) * (t / sec) ** 2

def candle():
    t = t_(.03); return .1 * np.sin(2 * np.pi * 1500 * t) * np.exp(-t * 160)

def heart():
    out = np.zeros(int(.6 * SR))
    for k, a in ((0, 1.0), (.22, .7)):
        t = t_(.2); b = np.sin(2 * np.pi * 58 * t * (1 + .5 * np.exp(-t * 30))) * np.exp(-t * 22)
        s = int(k * SR); out[s:s + len(b)] += a * b
    return .9 * out

def cash():
    out = np.zeros(int(1.2 * SR))
    for k, f in enumerate((2093.0, 2637.0, 3136.0)):
        b = bell(f, .9); s = int(k * .06 * SR); out[s:s + len(b)] += .16 * b
    t = t_(.12); ch = lowpass(rng.standard_normal(len(t)), 9000) - lowpass(rng.standard_normal(len(t)), 3000)
    out[:len(t)] += .12 * ch * np.exp(-t * 40)
    return out

def buzz():
    t = t_(.28); sq = np.sign(np.sin(2 * np.pi * 98 * t))
    return .35 * lowpass(sq, 700) * env(len(t), .005, .08)

def sub():
    t = t_(.7); f = 95 * (35 / 95) ** (t / .7)
    return .8 * np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), .01, .4)

LIB = {"riser": riser, "candle": candle, "heart": heart, "cash": cash, "buzz": buzz, "sub": sub, "flat": flat, "whoosh": lambda: whoosh(), "swish": lambda: .6 * whoosh(.35, 800, 6000), "pop": pop,
       "alert": alert, "win": win, "loss": loss, "tick": tick}

def main(cues_path, dur, out_path):
    cues = json.load(open(cues_path)); dur = float(dur)
    mix = np.zeros(int(dur * SR) + SR)
    cache = {}
    for t0, name in cues:
        if name not in cache: cache[name] = LIB[name]()
        s = cache[name]; i = int(t0 * SR); mix[i:i + len(s)] += s[:len(mix) - i]
    mix = mix[:int(dur * SR)]
    peak = np.abs(mix).max() or 1
    mix = np.tanh(mix / peak * 1.2) * .7                       # sanft begrenzen, ca. −3 dB
    st = np.stack([mix, mix], 1)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st * 32767).astype("<i2").tobytes())

if __name__ == "__main__":
    main(*sys.argv[1:4])
