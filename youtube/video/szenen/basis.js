// Hilfen für zeitgesteuerte Szenen: alles hängt nur von t ab.
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const seg = (t, a, b) => clamp((t - a) / (b - a));            // 0..1 zwischen a und b
const outCubic = p => 1 - Math.pow(1 - p, 3);
const outBack = p => { const c = 1.9; return 1 + (c + 1) * Math.pow(p - 1, 3) + c * Math.pow(p - 1, 2); };
const inOut = p => p < .5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
const de = (v, d = 2) => v.toLocaleString('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d });
const $ = s => document.querySelector(s);

// Hintergrund bewegt sich langsam, damit nie ein Standbild entsteht.
function background(t) {
  const st = document.documentElement.style;
  st.setProperty('--go', (t * 18 % 80) + 'px');
  st.setProperty('--gx', (30 + 10 * Math.sin(t * .3)) + '%');
  st.setProperty('--gy', (30 + 8 * Math.cos(t * .25)) + '%');
}

// Untertitel: Liste [start, ende, text]; mit kleinem Einblenden.
function captions(t, list) {
  const el = $('.caption'); const c = list.find(([a, b]) => t >= a && t < b);
  if (!c) { el.style.opacity = 0; return; }
  el.innerHTML = c[2];
  const p = Math.min(seg(t, c[0], c[0] + .18), 1 - seg(t, c[1] - .12, c[1]));
  el.style.opacity = p; el.style.transform = `translateX(-50%) translateY(${(1 - p) * 14}px)`;
}
