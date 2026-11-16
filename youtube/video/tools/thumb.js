// Erzeugt die Vorschaubilder (1280×720) aus vorschaubild/thumb.html.
const { chromium } = require('playwright'); const path = require('path');
(async () => { const b = await chromium.launch();
  for (const v of ['a', 'b']) { const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
    await p.goto('file://' + path.resolve(__dirname, '../vorschaubild/thumb.html') + '?v=' + v); await p.evaluate(() => document.fonts.ready);
    await p.screenshot({ path: path.resolve(__dirname, `../vorschaubild/vorschaubild-${v}.jpg`), type: 'jpeg', quality: 92 }); }
  await b.close(); })();
