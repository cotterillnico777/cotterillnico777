// Generische Trade-Szene: echte 5-Minuten-Kerzen, die Kerze für Kerze ablaufen.
// Erwartet window.TRADE (Konfiguration) und window.KERZEN (aus daten/kerzen.js).
(function () {
  const C = window.TRADE, bars = window.KERZEN[C.key];
  const NS = "http://www.w3.org/2000/svg";
  const mk = (tag, a, p, txt) => { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); if (txt != null) e.textContent = txt; p.appendChild(e); return e; };
  const idx = hhmm => bars.findIndex(b => b[0] === hhmm);
  const iEntry = idx(C.entryBar), iExit = idx(C.exitBar);

  // Zeichenfläche
  const svg = document.getElementById("chart"), W = 1680, H = 640, L = 20, R = 210, T = 20, B = 50;
  const lo = C.yMin, hi = C.yMax, n = bars.length, cw = (W - L - R) / n;
  const X = i => L + i * cw + cw / 2, Y = v => T + (hi - v) * (H - T - B) / (hi - lo);

  const grid = mk("g", {}, svg);
  for (let v = Math.ceil(lo / C.yStep) * C.yStep; v <= hi; v += C.yStep) {
    mk("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), stroke: "var(--line)", "stroke-width": 2 }, grid);
    mk("text", { x: W - R + 150, y: Y(v) + 9, "text-anchor": "end", "font-size": 24, fill: "var(--muted)" }, grid, de(v, C.yDec || 0));
  }
  ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00"].forEach(h => { const i = idx(h); if (i >= 0) mk("text", { x: X(i), y: H - 12, "text-anchor": "middle", "font-size": 24, fill: "var(--muted)" }, grid, h); });

  // Eröffnungsspanne (erste drei Kerzen)
  const or = bars.slice(0, 3), orHi = Math.max(...or.map(b => b[2])), orLo = Math.min(...or.map(b => b[3]));
  const orBox = mk("g", {}, svg);
  mk("rect", { x: L, y: Y(orHi), width: 3 * cw, height: Y(orLo) - Y(orHi), fill: "var(--accent)", "fill-opacity": .14, stroke: "var(--accent)", "stroke-width": 2, "stroke-dasharray": "6 6" }, orBox);
  const orEdge = (C.side || 1) > 0 ? orHi : orLo;
  mk("line", { x1: L, x2: W - R, y1: Y(orEdge), y2: Y(orEdge), stroke: "var(--accent)", "stroke-width": 2, "stroke-dasharray": "4 10", "stroke-opacity": .6 }, orBox);
  mk("text", { x: L, y: Y(orLo) + 32, "font-size": 22, fill: "var(--accent)" }, orBox, "Spanne 9:30–9:45");

  // Kerzen
  const cg = mk("g", {}, svg);
  const candles = bars.map((b, i) => {
    const [, o, h, l, c] = b, up = c >= o, col = up ? "var(--gain)" : "var(--loss)", g = mk("g", { opacity: 0 }, cg);
    mk("line", { x1: X(i), x2: X(i), y1: Y(h), y2: Y(l), stroke: col, "stroke-width": 3 }, g);
    mk("rect", { x: X(i) - cw * .34, y: Y(Math.max(o, c)), width: cw * .68, height: Math.max(2, Math.abs(Y(o) - Y(c))), fill: col, rx: 1.5 }, g);
    return g;
  });

  // Plan-Linien: Einstieg, Stop, Ziel
  const plan = mk("g", { opacity: 0 }, svg);
  const lineAt = (v, col, label, dash) => {
    const g = mk("g", {}, plan);
    const ln = mk("line", { x1: X(iEntry), x2: W - R, y1: Y(v), y2: Y(v), stroke: col, "stroke-width": 4, "stroke-dasharray": dash || "" }, g);
    mk("rect", { x: W - R + 6, y: Y(v) - 22, width: 196, height: 44, rx: 8, fill: col }, g);
    mk("text", { x: W - R + 104, y: Y(v) + 9, "text-anchor": "middle", "font-size": 24, "font-weight": 600, fill: "#0b1622" }, g, label);
    return ln;
  };
  const planLines = [lineAt(C.target, "var(--gain)", "Ziel " + de(C.target)), lineAt(C.entry, "var(--ink)", "Kauf " + de(C.entry), "10 8"), lineAt(C.stop, "var(--loss)", "Stop " + de(C.stop))];
  const entryDot = mk("circle", { cx: X(iEntry), cy: Y(C.entry), r: 13, fill: "var(--ink)", stroke: "var(--bg)", "stroke-width": 4, opacity: 0 }, svg);

  // Zeitplan: wie viele Kerzen sind bei Zeit t sichtbar?
  const tl = C.timeline; // [[t, kerzenAnzahl], ...]
  function shown(t) {
    if (t <= tl[0][0]) return tl[0][1];
    for (let k = 1; k < tl.length; k++) if (t <= tl[k][0]) { const [t0, c0] = tl[k - 1], [t1, c1] = tl[k]; return c0 + (c1 - c0) * inOut(seg(t, t0, t1)); }
    return tl[tl.length - 1][1];
  }

  // Zeitpunkt, zu dem Kerze i erscheint (für Momente ohne feste Zeit)
  const tAt = i => { for (let t = 0; t < 60; t += .02) if (shown(t) >= i + 1) return t + .05; return 0; };
  (C.moments || []).forEach(m => { if (m.t == null) m.t = tAt(idx(m.bar)) + (m.delay || 0); });
  if (C.tEntry == null) C.tEntry = tAt(iEntry) + .1;
  if (C.tExit == null) C.tExit = tAt(iExit) + .1;
  // Untertitel dürfen an Ereignisse gebunden sein: ["entry"|"exit"|"m0"…, Versatz, Dauer, Text]
  const key = k => k === "entry" ? C.tEntry : k === "exit" ? C.tExit : C.moments[+k.slice(1)].t;
  C.captions = C.captions.map(c => typeof c[0] === "string" ? [key(c[0]) + c[1], key(c[0]) + c[1] + c[2], c[3]] : c);
  // Momente (Tiefpunkt, Ziel o. Ä.) mit Markierung im Chart
  const marks = (C.moments || []).map(m => { const i = idx(m.bar); return { ...m, i, dot: mk("circle", { cx: X(i), cy: Y(m.price), r: 16, fill: "none", stroke: m.color, "stroke-width": 5, opacity: 0 }, svg) }; });

  // ---- Spannung: Showdown-Pause vor der Entscheidung und Kontostand danach ----
  const D = C.showdown ? 2.4 : 0, F = Math.min(C.tExit - .3, tAt(iExit - 1) - .04);   // Pause, bevor die Ausstiegskerze erscheint
  const stage = $("#stage");
  const css = document.createElement("style"); css.textContent = `
    #vig{position:absolute;inset:0;pointer-events:none;opacity:0;background:radial-gradient(ellipse at 50% 50%,transparent 35%,rgba(0,0,0,.82) 100%)}
    #sd{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);text-align:center;opacity:0;white-space:nowrap;pointer-events:none;background:rgba(7,13,24,.82);border:5px solid var(--cost);border-radius:30px;padding:30px 70px 10px}
    #sd .q{font:800 120px/1 var(--display);color:#fff;text-shadow:0 6px 0 rgba(0,0,0,.6),0 0 40px rgba(0,0,0,.9)}
    #sd .n{font:800 220px/1 var(--display);color:var(--cost);text-shadow:0 0 50px rgba(255,178,63,.5),0 6px 0 rgba(0,0,0,.6)}
    #konto{position:absolute;left:50%;top:44%;transform:translate(-50%,-50%);opacity:0;text-align:center;padding:28px 56px;border-radius:26px;
      background:rgba(11,22,34,.94);border:5px solid var(--line);white-space:nowrap}
    #konto .k{font:600 30px var(--mono);color:var(--muted);letter-spacing:.1em}
    #konto .v{font:600 120px/1.05 var(--mono)} #konto .d{font:800 44px var(--display)}`;
  document.head.appendChild(css);
  stage.insertAdjacentHTML("beforeend", `<div id="vig"></div><div id="sd"><div class="q">${C.showdown || ""}</div><div class="n"></div></div>`);
  if (C.konto != null) {
    const hid = C.konto === "?", dv = hid ? 0 : C.konto - 1000;
    stage.insertAdjacentHTML("beforeend", `<div id="konto"><div class="k">KONTOSTAND NACH KOSTEN</div>
      <div class="v" style="color:${hid ? "var(--cost)" : dv >= 0 ? "var(--gain)" : "var(--loss)"}">${hid ? "?.???,?? $" : de(C.konto) + " $"}</div>
      <div class="d" style="color:${hid ? "var(--ink)" : dv >= 0 ? "var(--gain)" : "var(--loss)"}">${hid ? "Das zeigt erst die Auflösung" : (dv >= 0 ? "+" : "−") + de(Math.abs(dv)) + " $ seit Start"}</div>
      ${C.prog != null && C.outcome ? `<div style="font:600 30px var(--mono);color:var(--muted);margin-top:12px">Prognose: ${C.prog >= .12 ? "STARK" : C.prog >= .05 ? "SOLIDE" : "KNAPP"} → Ergebnis: ${C.outcome}</div>` : ""}</div>`);
  }
  // Zoom-Mittelpunkt: letzte Kerze vor der Pause
  let zx = "70%", zy = "50%";
  const zoomOrigin = () => { const iF = Math.max(0, Math.min(n - 1, iExit - 1)), pt = svg.createSVGPoint(); pt.x = X(iF); pt.y = Y(bars[iF][4]);
    const sp = pt.matrixTransform(svg.getScreenCTM()), r = $("#chartwrap").getBoundingClientRect();
    zx = (sp.x - r.left) + "px"; zy = (sp.y - r.top) + "px"; };
  zoomOrigin();
  window.META = { freeze: D ? [F, D] : null };

  // ---- Konto-Lebensbalken (oben Mitte) ----
  const css2 = document.createElement("style"); css2.textContent = `
    #hp{position:absolute;left:50%;top:26px;width:640px;margin-left:-320px;opacity:0}
    #hp .lab{display:flex;justify-content:space-between;font:600 22px var(--mono);color:var(--muted);letter-spacing:.08em;margin-bottom:6px}
    #hp .lab b{font:600 30px var(--mono);color:var(--ink)}
    #hp .bar{position:relative;height:26px;border-radius:13px;background:#0a1422;border:3px solid var(--line);overflow:hidden}
    #hp .fill{position:absolute;top:0;bottom:0}
    #hp .mid{position:absolute;left:50%;top:-6px;bottom:-6px;width:4px;margin-left:-2px;background:var(--ink)}
    #hp.low .bar{border-color:var(--loss);box-shadow:0 0 22px rgba(255,90,90,.55)}
    #redvig{position:absolute;inset:0;pointer-events:none;opacity:0;box-shadow:inset 0 0 220px 40px rgba(255,40,40,.55)}
    #prog{position:absolute;left:50%;top:150px;width:760px;margin-left:-380px;opacity:0;padding:18px 30px;border-radius:20px;background:rgba(9,15,27,.94);border:4px solid var(--accent)}
    #prog .k{font:600 24px var(--mono);color:var(--accent);letter-spacing:.1em}
    #prog .row{display:flex;justify-content:space-between;align-items:baseline;margin-top:6px}
    #prog .v{font:800 64px/1 var(--display)} #prog .w{font:800 46px var(--display)}
    #prog .g{position:relative;height:16px;border-radius:8px;margin-top:14px;background:linear-gradient(90deg,var(--loss),#33415a 30%,var(--cost) 55%,var(--gain))}
    #prog .nd{position:absolute;top:-10px;width:8px;height:36px;margin-left:-4px;border-radius:4px;background:#fff;box-shadow:0 0 14px #fff}
    #prog .pp{font:600 26px var(--mono);color:var(--muted);margin-top:10px}
    #slow{position:absolute;left:50%;top:150px;transform:translateX(-50%);opacity:0;text-align:center;white-space:nowrap}
    #slow .t{display:inline-block;font:800 40px var(--mono);letter-spacing:.3em;color:#0b1622;background:var(--cost);padding:6px 18px;border-radius:8px}
    #slow .l{font:600 34px var(--body);color:var(--ink);margin-top:14px;text-shadow:0 3px 0 rgba(0,0,0,.6)}
    #slow .d{font:600 150px/1 var(--mono);color:var(--cost);text-shadow:0 0 40px rgba(255,178,63,.5),0 6px 0 rgba(0,0,0,.6)}`;
  document.head.appendChild(css2);
  const HPL = 990, HPH = 1010, hpx = v => clamp((v - HPL) / (HPH - HPL)) * 100;
  if (C.kontoVor != null) stage.insertAdjacentHTML("beforeend", `<div id="redvig"></div><div id="hp"><div class="lab"><span>KONTO</span><b></b><span>START 1.000 $</span></div>
    <div class="bar"><div class="fill"></div><div class="mid"></div></div></div>`);
  const progWort = e => e >= .12 ? "STARK" : e >= .05 ? "SOLIDE" : "KNAPP";
  const progFarbe = e => e >= .12 ? "var(--gain)" : e >= .05 ? "var(--cost)" : "var(--loss)";
  if (C.prog != null) stage.insertAdjacentHTML("beforeend", `<div id="prog"><div class="k">CLAUDES PROGNOSE${C.progBrutto ? " (VOR KOSTEN)" : " (NACH KOSTEN)"}</div>
    <div class="row"><span class="v" style="color:${progFarbe(C.prog)}">+${de(C.prog, 3)} R</span><span class="w" style="color:${progFarbe(C.prog)}">${progWort(C.prog)}</span></div>
    <div class="g"><div class="nd"></div></div>${C.progPct ? `<div class="pp">Ziel zuerst ${C.progPct[0]} · Stop zuerst ${C.progPct[1]}</div>` : ""}</div>`);
  const S = C.slow ? { ...C.slow, i: idx(C.slow.bar) } : null;
  if (S) stage.insertAdjacentHTML("beforeend", `<div id="slow"><div class="t">ZEITLUPE</div><div class="l">${S.label}</div><div class="d"></div></div>`);
  const originFor = (i, price) => { const pt = svg.createSVGPoint(); pt.x = X(i); pt.y = Y(price);
    const sp = pt.matrixTransform(svg.getScreenCTM()), r = $("#chartwrap").getBoundingClientRect(); return `${sp.x - r.left}px ${sp.y - r.top}px`; };
  const slowOrigin = S ? originFor(S.i, S.level) : "";
  if (S) { S.t0 = tAt(S.i - 1); S.t1 = tAt(S.i); }

  window.render = function (t) {
    background(t);
    const real = t;
    if (D && t > F) t = t < F + D ? F : t - D;
    const fr = D ? seg(real, F, F + .35) * (1 - seg(real, F + D - .25, F + D)) : 0;
    // Titelkarte, die danach nach oben links schrumpft
    const ti = $("#title"), a = outBack(seg(t, .1, .7)), s = inOut(seg(t, 1.5, 2.3));
    ti.style.opacity = clamp(a);
    ti.style.transform = `translate(${-s * 600}px, ${-s * 448}px) scale(${(.7 + .3 * a) * (1 - .55 * s)})`;
    $("#frame").style.opacity = seg(t, 1.8, 2.4);
    grid.style.opacity = seg(t, 2, 2.6);
    orBox.style.opacity = seg(t, 2.6, 3.2);

    const k = shown(t);
    candles.forEach((g, i) => { const p = clamp(k - i), y0 = Y(bars[i][1]);
      g.setAttribute("opacity", Math.min(1, p * 4) * (C.dimAfter && i > iExit ? .32 : 1));
      g.setAttribute("transform", `translate(0 ${y0}) scale(1 ${Math.max(.02, p)}) translate(0 ${-y0})`); });

    // Uhr: Zeit der letzten sichtbaren Kerze (Schlusszeit) in New York und bei uns
    const lastI = Math.max(0, Math.min(n - 1, Math.ceil(k) - 1));
    const [hh, mm] = bars[lastI][0].split(":").map(Number), endM = hh * 60 + mm + 5;
    const f = m => String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");
    $("#clock").innerHTML = `<b>${f(endM)}</b> New York · ${f(endM + 360)} bei uns`;
    $("#clock").style.opacity = seg(t, 2.4, 3);

    // Kauf
    const pe = seg(t, C.tEntry, C.tEntry + .5);
    plan.setAttribute("opacity", pe);
    planLines.forEach(l => { const x1 = X(iEntry); l.setAttribute("x2", x1 + (W - R - x1) * outCubic(pe)); });
    entryDot.setAttribute("opacity", pe); entryDot.setAttribute("r", 13 + 14 * (1 - outBack(pe)));
    const tag = $("#entrytag"), pt = outBack(seg(t, C.tEntry + .2, C.tEntry + .7));
    tag.style.opacity = clamp(pt) * (1 - seg(t, C.tEntry + 3, C.tEntry + 3.4)); tag.style.transform = `scale(${.6 + .4 * pt})`;

    // Live-Ergebnis
    const pnl = $("#pnl");
    if (k >= iEntry + 1) {
      const cur = bars[Math.min(n - 1, Math.max(iEntry, Math.floor(k) - 1))];
      let v = C.qty * (cur[4] - C.entry) * (C.side || 1);
      if (C.exitBar && Math.floor(k) - 1 >= iExit) v = C.result;
      pnl.textContent = (v >= 0 ? "+" : "−") + de(Math.abs(v)) + " $";
      pnl.style.color = v >= 0 ? "var(--gain)" : "var(--loss)";
      $("#pnlbox").style.opacity = seg(t, C.tEntry + .4, C.tEntry + .9);
    } else $("#pnlbox").style.opacity = 0;

    // Momente
    marks.forEach(m => {
      const p = outBack(seg(t, m.t, m.t + .45)), end = 1 - seg(t, m.t + m.hold, m.t + m.hold + .4);
      m.dot.setAttribute("opacity", clamp(p) * end); m.dot.setAttribute("r", 16 + 30 * (1 - clamp(p)));
      const el = document.getElementById(m.id); el.style.opacity = clamp(p) * end;
      el.style.transform = `scale(${.5 + .5 * p}) rotate(${m.rot || 0}deg)`;
      if (m.shake && t > m.t && t < m.t + .5) $("#chartwrap").style.transform = `translate(${Math.sin(t * 90) * 8 * (1 - seg(t, m.t, m.t + .5))}px,0)`;
    });
    if (!marks.some(m => m.shake && t > m.t && t < m.t + .5)) $("#chartwrap").style.transform = "";

    // Ziel / Stop: großer Stempel und Lichtblitz
    const ps = outBack(seg(t, C.tExit, C.tExit + .5));
    $("#stamp").style.opacity = clamp(ps) * (1 - seg(t, C.tExit + 3.2, C.tExit + 3.8)); $("#stamp").style.transform = `translate(-50%,-50%) scale(${2.2 - 1.2 * ps}) rotate(-4deg)`;
    $("#flash").style.opacity = t > C.tExit ? .5 * (1 - seg(t, C.tExit, C.tExit + .4)) : 0;
    captions(t, C.captions);
    // Showdown-Overlay
    if (D) {
      $("#vig").style.opacity = fr;
      const sd = $("#sd"); sd.style.opacity = fr;
      const k3 = Math.min(3, Math.max(1, 3 - Math.floor((real - F - .2) / .7)));
      sd.querySelector(".n").textContent = real > F ? k3 : "";
      const pul = 1 + .08 * Math.max(0, 1 - ((real - F - .2) % .7) / .25);
      sd.querySelector(".n").style.transform = `scale(${pul})`;
      $("#chartwrap").style.transformOrigin = `${zx} ${zy}`;
      if (fr > 0) $("#chartwrap").style.transform = `scale(${1 + .2 * inOut(fr)})`;
      if (fr > 0) $(".caption").style.opacity = 1 - fr;
    }
    // Konto-Lebensbalken
    if (C.kontoVor != null) {
      const hp = $("#hp"); hp.style.opacity = seg(t, 2.2, 2.8);
      const hid = C.konto === "?", tgt = hid ? C.kontoVor : C.konto, m = inOut(seg(t, C.tExit + .2, C.tExit + 1.4));
      const v = C.kontoVor + (tgt - C.kontoVor) * m, glitch = hid && t > C.tExit + .3;
      const f = hp.querySelector(".fill"), a = hpx(1000), b = hpx(v);
      f.style.left = Math.min(a, b) + "%"; f.style.width = Math.abs(b - a) + "%";
      f.style.background = glitch ? "var(--cost)" : v >= 1000 ? "var(--gain)" : "var(--loss)";
      if (glitch) { const j = Math.floor(t * 14) % 5; f.style.left = (20 + j * 9) + "%"; f.style.width = (8 + (j * 7) % 25) + "%"; }
      hp.querySelector("b").textContent = glitch ? "?.???,?? $" : de(v) + " $";
      hp.querySelector("b").style.color = glitch ? "var(--cost)" : v >= 1000 ? "var(--gain)" : "var(--loss)";
      const low = !glitch && v < 1000; hp.classList.toggle("low", low);
      const blink = low && t > C.tExit + .2 && t < C.tExit + 4 ? .5 + .5 * Math.sin(t * 14) : 0;
      $("#redvig").style.opacity = blink * .9;
    }
    // Claudes Prognose beim Einstieg
    if (C.prog != null) {
      const pp = outBack(seg(t, C.tEntry + .7, C.tEntry + 1.2)), po = (1 - seg(t, C.tEntry + 4.6, C.tEntry + 5)) * (S ? 1 - seg(t, S.t0 - .4, S.t0) : 1);
      $("#prog").style.opacity = clamp(pp) * po; $("#prog").style.transform = `scale(${.7 + .3 * pp})`;
      const nv = clamp((C.prog + .1) / .4), sw = inOut(seg(t, C.tEntry + 1, C.tEntry + 2.2));
      $("#prog .nd").style.left = (nv * sw * 100 + Math.sin(t * 25) * 1.5 * (1 - sw) * (sw > 0)) + "%";
      if (pp > 0 && po > 0) $("#entrytag").style.opacity = 0;
    }
    // Zeitlupe bei Beinahe-Treffern
    if (S) {
      const on = seg(t, S.t0, S.t0 + .3) * (1 - seg(t, S.t1 + .6, S.t1 + 1));
      $("#slow").style.opacity = on; $("#vig").style.opacity = Math.max(+$("#vig").style.opacity || 0, on * .9);
      if (on > 0) { $("#chartwrap").style.transformOrigin = slowOrigin; $("#chartwrap").style.transform = `scale(${1 + .28 * inOut(on)})`;
        $("#chartwrap").style.filter = `saturate(${1 - .5 * on})`; $(".caption").style.opacity = 1 - on; }
      else $("#chartwrap").style.filter = "";
      const p = clamp(k - S.i), [, o, h, l] = bars[S.i], ext = S.up ? o + (h - o) * p : o - (o - l) * p;
      const dist = Math.max(0, S.up ? S.level - ext : ext - S.level);
      $("#slow .d").textContent = de(t < S.t0 ? Math.abs(S.level - o) : dist) + " $";
    }
    // Kontostand nach dem Trade
    if (C.konto != null) { const kp = outBack(seg(t, C.tExit + 3.6, C.tExit + 4.1)), ko = 1 - seg(t, C.tExit + 7, C.tExit + 7.4);
      $("#konto").style.opacity = clamp(kp) * ko; $("#konto").style.transform = `translate(-50%,-50%) scale(${.6 + .4 * kp})`;
      if (kp > 0) $(".caption").style.opacity = Math.min(+$(".caption").style.opacity || 0, 1 - clamp(kp) * ko); }
  };
  // Ton-Stichworte für tools/sfx.py
  const stop = !C.exitSfx && C.result < 0, win = !C.exitSfx && C.result >= 0;
  let sfx = [[.1, "whoosh"], [.1, "sub"], [1.5, "swish"], [C.tEntry, "pop"]]
    .concat((C.moments || []).map(m => [m.t, m.sfx || "alert"]))
    .concat([[C.tExit, C.exitSfx || (win ? "win" : "loss")]])
    .concat(win ? [[C.tExit + .3, "cash"]] : stop ? [[C.tExit + .25, "buzz"]] : []);
  if (C.konto != null) sfx.push([C.tExit + 3.6, C.konto === "?" ? "alert" : "pop"]);
  // leises Ticken, während die Kerzen laufen
  let last = -1; for (let i = 0; i < n; i++) { const tt = tAt(i); if (tt - last >= .1 && tt < F) { sfx.push([tt, "candle"]); last = tt; } }
  if (C.prog != null) sfx.push([C.tEntry + .7, "scan"], [C.tEntry + 2.2, "lock"]);
  if (C.kontoVor != null && C.konto !== "?" && C.konto < 1000 && C.kontoVor >= 1000) sfx.push([C.tExit + .4, "alarm"]);
  if (C.konto === "?") sfx.push([C.tExit + .3, "glitch"]);
  if (S) { const t0 = tAt(S.i - 1); sfx = sfx.filter(([tt, s]) => !(s === "candle" && tt > t0 && tt < tAt(S.i) + .5));
    sfx.push([t0, "slowdown"], [t0 + .2, "drone"], [t0 + .5, "heartslow"], [t0 + 1.6, "heartslow"], [tAt(S.i) + .1, "alert"]); }
  sfx = sfx.map(([t0, s]) => [D && t0 > F ? t0 + D : t0, s]);           // alles nach der Pause verschiebt sich
  if (D) sfx.push([F, "sub"], [F + .1, "heart"], [F + .9, "heart"], [F + 1.6, "heart"], [F + .2, "tick"], [F + .9, "tick"], [F + 1.6, "tick"], [F + D - 1.05, "riser"]);
  else sfx.push([Math.max(0, C.tExit - 1.1), "riser"]);
  window.SFX = sfx;
  for (let i = 0; i < n; i++) if (tAt(i) >= F && tAt(i) < C.tExit + 1) { const tt = tAt(i) + D; if (!sfx.some(x => Math.abs(x[0] - tt) < .09)) sfx.push([tt, "candle"]); }
  if (C.day) dayDots(C.day);
  window.render(0);
})();
