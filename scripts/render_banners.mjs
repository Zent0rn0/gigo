// Рисует PNG-баннеры бота из docs/brand/banners/banner.html.
// Нужен Playwright с Chromium: npx -y playwright@1 install chromium (один раз), затем node scripts/render_banners.mjs
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const src = 'file://' + path.join(root, 'docs/brand/banners/banner.html');
const out = path.join(root, 'backend/gigo/bot/banners');

const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
const page = await browser.newPage({ viewport: { width: 1280, height: 640 } });
await page.goto(src);
const keys = await page.evaluate(() => window.BANNER_KEYS);
for (const key of keys) {
  await page.goto(`${src}#${key}`);
  await page.reload();
  await page.screenshot({ path: path.join(out, `${key}.png`), clip: { x: 0, y: 0, width: 1280, height: 640 } });
  console.log(key);
}
await browser.close();
