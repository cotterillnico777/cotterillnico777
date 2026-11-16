// Erzeugt die Vorschaubilder (1280×720) aus vorschaubild/*.html.
const { chromium } = require('playwright'); const path = require('path');
(async () => { const b = await chromium.launch();
  for (const [f, v] of [['thumb', 'a'], ['thumb', 'b'], ['thumb2', 'c'], ['thumb2', 'd']]) { const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
    await p.goto('file://' + path.resolve(__dirname, `../vorschaubild/${f}.html`) + '?v=' + v); await p.evaluate(() => document.fonts.ready);
    await p.screenshot({ path: path.resolve(__dirname, `../vorschaubild/vorschaubild-${v}.jpg`), type: 'jpeg', quality: 92 }); }
  await b.close(); })();
