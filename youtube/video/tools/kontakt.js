// Kontaktbogen: Standbilder mehrerer Szenen in ein Bild (zur Kontrolle).
// Aufruf: node tools/kontakt.js out.jpg szene:t szene:t ...
const { chromium } = require('playwright'); const path = require('path');
(async () => {
  const [out, ...specs] = process.argv.slice(2);
  const b = await chromium.launch(), bufs = [];
  for (const sp of specs) {
    const [name, t] = sp.split(':');
    const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
    p.on('pageerror', e => console.log('Fehler', name, e.message));
    await p.goto('file://' + path.resolve('szenen/' + name + '.html')); await p.evaluate(() => document.fonts.ready);
    await p.evaluate(t => render(t), +t);
    bufs.push((await p.screenshot({ type: 'jpeg', quality: 70 })).toString('base64')); await p.close();
  }
  const s = await b.newPage({ viewport: { width: 1920, height: Math.ceil(bufs.length / 2) * 540 } });
  await s.setContent('<body style="margin:0;display:grid;grid-template-columns:1fr 1fr;background:#000">' + bufs.map(x => `<img style="width:960px;height:540px;display:block" src="data:image/jpeg;base64,${x}">`).join(''));
  await s.screenshot({ path: out, type: 'jpeg', quality: 72 }); await b.close();
})();
