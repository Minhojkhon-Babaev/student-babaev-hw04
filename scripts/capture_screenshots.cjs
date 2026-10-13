// Optional screenshot helper. Requires Node.js, Playwright and Google Chrome.
// Run: NODE_PATH=/path/to/node_modules node scripts/capture_screenshots.cjs
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

(async () => {
  const directory = path.resolve(__dirname, '../evidence/screenshots');
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 });
  for (const filename of fs.readdirSync(directory).filter(name => name.endsWith('.html')).sort()) {
    await page.goto(pathToFileURL(path.join(directory, filename)).href);
    await page.screenshot({ path: path.join(directory, filename.replace(/\.html$/, '.png')), fullPage: true });
    console.log(`Captured ${filename.replace(/\.html$/, '.png')}`);
  }
  await browser.close();
})().catch(error => { console.error(error); process.exitCode = 1; });
