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

  window.render = function (t) {
    background(t);
    // Titelkarte, die danach nach oben links schrumpft
    const ti = $("#title"), a = outBack(seg(t, .1, .7)), s = inOut(seg(t, 1.5, 2.3));
    ti.style.opacity = clamp(a);
    ti.style.transform = `translate(${-s * 600}px, ${-s * 448}px) scale(${(.7 + .3 * a) * (1 - .55 * s)})`;
    $("#frame").style.opacity = seg(t, 1.8, 2.4);
    grid.style.opacity = seg(t, 2, 2.6);
    orBox.style.opacity = seg(t, 2.6, 3.2);

    const k = shown(t);
    candles.forEach((g, i) => { const p = clamp(k - i); g.setAttribute("opacity", p * (C.dimAfter && i > iExit ? .32 : 1)); g.setAttribute("transform", `translate(0 ${(1 - p) * 18})`); });

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
  };
  // Ton-Stichworte für tools/sfx.py
  const stop = !C.exitSfx && C.result < 0, win = !C.exitSfx && C.result >= 0;
  window.SFX = [[.1, "whoosh"], [.1, "sub"], [1.5, "swish"], [C.tEntry, "pop"]]
    .concat((C.moments || []).map(m => [m.t, m.sfx || "alert"]))
    .concat([[Math.max(0, C.tExit - 1.1), "riser"], [C.tExit, C.exitSfx || (win ? "win" : "loss")]])
    .concat(win ? [[C.tExit + .3, "cash"]] : stop ? [[C.tExit + .25, "buzz"]] : []);
  // leises Ticken, während die Kerzen laufen
  let last = -1; for (let i = 0; i < n; i++) { const tt = tAt(i); if (tt - last >= .1) { window.SFX.push([tt, "candle"]); last = tt; } }
  if (C.day) dayDots(C.day);
  window.render(0);
})();
