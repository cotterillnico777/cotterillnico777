// Rendert eine Szene Bild für Bild zu MP4 (1920×1080, 30 fps).
// Aufruf: node tools/render.js szenen/xyz.html SEKUNDEN out.mp4 [ton.m4a]
// Die Szene stellt window.render(t) bereit (t in Sekunden) und zeichnet den
// Zustand zu diesem Zeitpunkt. So ist jedes Bild exakt, ohne Ruckler.
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');

(async () => {
  const [scene, secs, out, audio] = process.argv.slice(2);
  const fps = 30, frames = Math.round(parseFloat(secs) * fps);
  const args = ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-'];
  if (audio) args.push('-i', audio, '-c:a', 'aac', '-b:a', '192k', '-shortest');
  args.push('-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', String(fps), out);
  const ff = spawn('ffmpeg', args, { stdio: ['pipe', 'inherit', 'inherit'] });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  page.on('pageerror', e => console.error('Fehler in der Szene:', e.message));
  await page.goto('file://' + path.resolve(scene));
  await page.evaluate(() => document.fonts.ready);
  for (let i = 0; i < frames; i++) {
    await page.evaluate(t => window.render(t), i / fps);
    const buf = await page.screenshot({ type: 'jpeg', quality: 92 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 90 === 0) process.stdout.write(`\r${scene}: ${i}/${frames}`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close();
  console.log(`\r${scene}: fertig → ${out}`);
})();
