import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

// Запись демо для презентации: три разных материала — фото, видео и ссылка.
// Видео пишется через встроенную запись Playwright, кадры сохраняются отдельно.
const API = 'http://127.0.0.1:8000';
const OUT = 'C:/Users/mvinn/Desktop/Xakton HSE/repo/docs/demo';
const TMP = 'C:/Users/mvinn/AppData/Local/Temp';
fs.mkdirSync(OUT, { recursive: true });

// --- аккаунт и тариф «Макс», чтобы в кадре был полный разбор ---
const email = `demo${Date.now()}@example.com`;
const reg = await fetch(`${API}/api/auth/register`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password: 'demo-pass-12345', name: 'Демо' }),
}).then(r => r.json());
await fetch(`${API}/api/upgrade`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-Token': reg.token },
  body: JSON.stringify({ plan: 'team' }),
});
console.log('аккаунт готов:', email);

// --- материалы ---
const pngPath = `${TMP}/demo-photo.png`;
const jpgPath = `${TMP}/demo-photo-edited.jpg`;
const mp4Path = `${TMP}/demo-video.mp4`;

fs.writeFileSync(pngPath, Buffer.from(
  '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6300010000050001',
  'hex',
));

function mp4(tool) {
  const raw = Buffer.from(tool, 'utf8');
  const body = Buffer.concat([Buffer.from([0, raw.length, 0, 0]), raw]);
  const hdr = Buffer.alloc(8);
  hdr.writeUInt32BE(body.length + 8, 0);
  hdr.write('\xa9too', 4, 'latin1');
  const ftypBody = Buffer.concat([
    Buffer.from('isom', 'latin1'),
    Buffer.from([0, 0, 2, 0]),
    Buffer.from('isomiso2', 'latin1'),
  ]);
  const ftypHdr = Buffer.alloc(8);
  ftypHdr.writeUInt32BE(ftypBody.length + 8, 0);
  ftypHdr.write('ftyp', 4, 'latin1');
  return Buffer.concat([ftypHdr, ftypBody, hdr, body]);
}
fs.writeFileSync(mp4Path, mp4('Generated with Sora'));
fs.copyFileSync(pngPath, jpgPath);

const browser = await chromium.launch({
  headless: false,
  slowMo: 260,
  args: ['--start-maximized'],
});
const ctx = await browser.newContext({
  viewport: null,
  recordVideo: { dir: TMP, size: { width: 1600, height: 900 } },
});
await ctx.addInitScript(t => {
  try { localStorage.setItem('provereno_token', t); } catch {}
}, reg.token);
const page = await ctx.newPage();

const shots = [];
async function shot(name) {
  const file = path.join(OUT, name);
  await page.screenshot({ path: file });
  shots.push(file);
  console.log('скриншот:', name);
}

async function waitResult(label) {
  for (let i = 0; i < 30; i++) {
    await page.waitForTimeout(1000);
    const text = await page.locator('body').innerText();
    if (/ПОЧЕМУ ТАКОЙ ВЕРДИКТ|Почему такой вердикт|ГРАНИЦЫ ПРОВЕРКИ|ЧТО ПРОВЕРЯЛИ/i.test(text)) return text;
  }
  return await page.locator('body').innerText();
}

await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' });
await page.waitForTimeout(1200);
await shot('01-home.png');

// ---------- 1. ФОТО ----------
console.log('\n=== 1. ФОТО ===');
await page.getByRole('tab', { name: 'Скриншот' }).click();
await page.waitForTimeout(700);
await page.locator('#check-image').setInputFiles(pngPath);
await page.waitForTimeout(900);
await shot('02-photo-upload.png');
await page.locator('.btn--primary').click();
let text = await waitResult('фото');
await page.waitForTimeout(1500);
await shot('03-photo-verdict.png');
console.log(text.slice(0, 700));

// ---------- 2. ВИДЕО ----------
console.log('\n=== 2. ВИДЕО ===');
await page.getByRole('tab', { name: 'Видео' }).click();
await page.waitForTimeout(700);
await page.locator('#check-video').setInputFiles(mp4Path);
await page.waitForTimeout(900);
await shot('04-video-upload.png');
await page.locator('.btn--primary').click();
text = await waitResult('видео');
await page.waitForTimeout(1500);
await shot('05-video-verdict.png');
console.log(text.slice(0, 700));

// ---------- 3. ССЫЛКА + ТЕКСТ ----------
console.log('\n=== 3. ССЫЛКА ===');
await page.getByRole('tab', { name: 'Текст' }).click();
await page.waitForTimeout(600);
await page.locator('#check-link').fill('https://www.cbr.ru/press/pr/');
await page.locator('#check-text').fill(
  'СРОЧНО! ЦБ запретил снятие наличных с 1 марта 2026 года. Перешлите всем!',
);
await page.waitForTimeout(900);
await shot('06-link-input.png');
await page.locator('.btn--primary').click();
text = await waitResult('ссылка');
await page.waitForTimeout(2000);
await shot('07-link-verdict.png');
console.log(text.slice(0, 900));

// Прокрутка к рубрике — главный кадр презентации.
const reasoning = page.getByText('Почему такой вердикт');
if (await reasoning.count()) {
  await reasoning.first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(1400);
  await shot('08-reasoning.png');
}

await page.waitForTimeout(1500);
const videoPath = await page.video().path();
await ctx.close();
await browser.close();

// Переносим запись в docs/demo
const finalVideo = path.join(OUT, 'demo-walkthrough.webm');
fs.copyFileSync(videoPath, finalVideo);
console.log('\nВИДЕО:', finalVideo, Math.round(fs.statSync(finalVideo).size / 1024), 'КБ');
console.log('скриншотов:', shots.length);
