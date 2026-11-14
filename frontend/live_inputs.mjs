// Живая проверка всех входов через настоящий API.
// Запуск: node live_inputs.mjs
// Проверяем текст, ссылку, скриншот, видео и три тарифа по глубине разбора.
const API = 'http://127.0.0.1:8000';

async function reg(email) {
  const r = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password: 'demo-pass-12345', name: 'Тест' }),
  });
  return r.json();
}

async function upgrade(token, plan) {
  return fetch(`${API}/api/upgrade`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Token': token },
    body: JSON.stringify({ plan }),
  }).then(r => r.json());
}

function png() {
  return Buffer.from(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6300010000050001',
    'hex',
  );
}

// Минимальный MP4 с атомом ©too — детекторы читают метаданные контейнера.
function mp4(tool = 'Generated with Sora') {
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

async function check(token, body, isForm = false) {
  return fetch(`${API}/api/check`, {
    method: 'POST',
    headers: isForm ? { 'X-Token': token } : { 'Content-Type': 'application/json', 'X-Token': token },
    body: isForm ? body : JSON.stringify(body),
  });
}

function summary(label, res, data) {
  const claim = (data.claims || [])[0] || {};
  console.log(
    `${label.padEnd(22)} ${res.status} | вердикт: ${String(data.verdict || data.error?.code).padEnd(10)}` +
      ` | сигн.: ${claim.status || '—'}` +
      ` | объясн.: ${(claim.explanation || data.explanation || '').length} симв.` +
      ` | что делать: ${claim.action ? 'да' : 'нет'}` +
      ` | пересылка: ${claim.resend ? 'да' : 'нет'}`,
  );
  if (data.error) console.log(`   ошибка: ${data.error.message}`);
}

const base = Date.now();
const free = await reg(`free${base}@example.com`);
const plusUser = await reg(`plus${base}@example.com`);
const maxUser = await reg(`max${base}@example.com`);
await upgrade(plusUser.token, 'pro');
await upgrade(maxUser.token, 'team');
console.log(`аккаунты: free=${free.token.slice(0, 6)} plus=${plusUser.token.slice(0, 6)} max=${maxUser.token.slice(0, 6)}\n`);

const TEXT = 'СРОЧНО! ЦБ запретил снятие наличных с 1 марта 2026 года. Перешлите всем!';

for (const [label, user] of [['ТЕКСТ free', free], ['ТЕКСТ pro', plusUser], ['ТЕКСТ team', maxUser]]) {
  const res = await check(user.token, { text: TEXT });
  summary(label, res, await res.json());
}

// Ссылка: страница недоступна → честный отказ просить текст.
{
  const res = await check(maxUser.token, { url: 'https://example.invalid/news/1' });
  summary('ССЫЛКА (нет сети)', res, await res.json());
}

// Фото.
{
  const form = new FormData();
  form.append('image', new Blob([png()], { type: 'image/png' }), 'shot.png');
  const res = await check(maxUser.token, form, true);
  summary('ФОТО team', res, await res.json());
}

// Видео с маркером генератора.
{
  const form = new FormData();
  form.append('video', new Blob([mp4()], { type: 'video/mp4' }), 'clip.mp4');
  const res = await check(maxUser.token, form, true);
  summary('ВИДЕО team', res, await res.json());
}

// Без токена — должно быть 401.
{
  const res = await fetch(`${API}/api/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: TEXT }),
  });
  summary('БЕЗ ТОКЕНА', res, await res.json());
}
