"""Baut das fertige Video aus den Szenen und deinen Sprachaufnahmen.
Aufruf: python3 tools/finale.py   → ausgabe/finale.mp4

Erwartet die Aufnahmen in youtube/video/ton/ als 01-*.m4a bis 11-*.m4a (auch .mp3/.wav/.ogg).
Jede Aufnahme gehört zu einem Abschnitt des Skripts. Ist eine Aufnahme länger als die
Szenen dieses Abschnitts, wird das letzte Bild des Abschnitts verlängert.
Die Musik wird passend zur neuen Länge neu erzeugt und unter der Stimme abgesenkt."""
import glob, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "..")
AUS = os.path.join(BASE, "ausgabe")
TON = os.environ.get("TON") or os.path.join(BASE, "ton")

# Abschnitt des Skripts → Szenen (Reihenfolge wie im Video)
ABSCHNITTE = [
    ("01", ["hook"]), ("02", ["regeln"]), ("03", ["timemachine"]), ("04", ["tag1"]),
    ("05", ["merck", "kdp", "nke"]), ("06", ["kosten"]), ("07", ["mrna", "ftnt"]),
    ("08", ["nxpi", "panw", "gis"]), ("09", ["cboe", "aapl", "bilanz"]), ("10", ["lehren"]),
    ("11", ["abstimmung"]),
]
VORLAUF = .5      # Sekunden Stille, bevor die Stimme im Abschnitt einsetzt
NACHLAUF = 1.0    # Sekunden nach der Stimme, bevor der nächste Abschnitt beginnt

def dauer(f):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", f]).strip())

def run(*a):
    subprocess.run(list(a), check=True)

def main():
    teile, stimmen, laengen, t = [], [], {}, 0.0
    tmp = os.path.join(AUS, "finale-tmp"); os.makedirs(tmp, exist_ok=True)
    for nr, szenen in ABSCHNITTE:
        dateien = sorted(glob.glob(os.path.join(TON, nr + "-*.*")))
        if not dateien:
            sys.exit(f"Aufnahme fehlt: ton/{nr}-....m4a")
        stimme = dateien[0]; v = dauer(stimme)
        s_len = [dauer(os.path.join(AUS, s + ".mp4")) for s in szenen]
        extra = max(0.0, VORLAUF + v + NACHLAUF - sum(s_len))
        for i, s in enumerate(szenen):
            src = os.path.join(AUS, s + ".mp4")
            if i == len(szenen) - 1 and extra > 0:      # letztes Bild verlängern
                dst = os.path.join(tmp, s + "-lang.mp4")
                run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", f"tpad=stop_mode=clone:stop_duration={extra:.2f}",
                    "-af", f"apad=pad_dur={extra:.2f}", "-c:v", "libx264", "-crf", "18", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", dst)
                src = dst; s_len[i] += extra
            teile.append(src); laengen[s] = s_len[i]
        stimmen.append((stimme, t + VORLAUF)); t += sum(s_len)

    # Bild und Effekte aneinanderhängen
    liste = os.path.join(tmp, "liste.txt")
    open(liste, "w").write("".join(f"file '{p}'\n" for p in teile))
    bild = os.path.join(tmp, "bild.mp4")
    run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", liste,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", bild)

    # Stimme: säubern, gleich laut machen, an die richtige Stelle legen
    inp, flt = [], []
    for i, (f, start) in enumerate(stimmen):
        inp += ["-i", f]
        flt.append(f"[{i}:a]aresample=48000,highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,"
                   f"loudnorm=I=-16:TP=-1.5,adelay={int(start * 1000)}|{int(start * 1000)}[v{i}]")
    flt.append("".join(f"[v{i}]" for i in range(len(stimmen))) + f"amix=inputs={len(stimmen)}:normalize=0[s]")
    stimme = os.path.join(tmp, "stimme.wav")
    run("ffmpeg", "-y", "-loglevel", "error", *inp, "-filter_complex", ";".join(flt), "-map", "[s]", "-ac", "2", stimme)

    # Musik passend zur neuen Länge
    json.dump(laengen, open(os.path.join(AUS, "szenen-laengen.json"), "w"))
    run("python3", os.path.join(HERE, "musik.py"), "--nur-musik")

    # Mischung: Stimme vorne, Effekte etwas leiser, Musik leise und unter der Stimme abgesenkt
    out = os.path.join(AUS, "finale.mp4")
    run("ffmpeg", "-y", "-loglevel", "error", "-i", bild, "-i", stimme, "-i", os.path.join(AUS, "musik.wav"), "-filter_complex",
        "[1:a]asplit=2[sv][sc];[2:a]volume=-15dB[m0];[m0][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[m];"
        "[0:a]volume=-5dB[fx];[sv][fx][m]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.95[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out)
    print("fertig:", out, f"({dauer(out) / 60:.1f} Minuten)")

if __name__ == "__main__":
    main()
