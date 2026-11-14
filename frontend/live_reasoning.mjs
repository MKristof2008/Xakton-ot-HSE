// Живая проверка рубрики: приходит ли объяснение вердикта в ответе.
// Запуск: node live_reasoning.mjs
const API = 'http://127.0.0.1:8000';

const reg = await fetch(`${API}/api/auth/register`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: `rubric${Date.now()}@example.com`,
    password: 'demo-pass-12345',
    name: 'Тест',
  }),
}).then(r => r.json());

await fetch(`${API}/api/upgrade`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-Token': reg.token },
  body: JSON.stringify({ plan: 'team' }),
});

const cases = [
  'СРОЧНО! ЦБ запретил снятие наличных с 1 марта 2026 года. Перешлите всем!',
  'МРОТ с 1 января 2025 года составляет 22 440 рубля в месяц.',
  'Вчера в Казани открыли новый мост через реку.',
];

for (const text of cases) {
  const res = await fetch(`${API}/api/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Token': reg.token },
    body: JSON.stringify({ text }),
  });
  const data = await res.json();
  const r = data.reasoning || {};
  console.log(`\n=== ${text.slice(0, 60)}…`);
  console.log(`вердикт: ${data.verdict} | балл: ${data.score}/100 | уверенность рубрики: ${r.confidence}`);
  console.log(`тема: ${data.tag?.title} (${data.tag?.key}) зацепки: ${(data.tag?.hits || []).join(', ')}`);
  console.log(`итог рубрики: ${r.summary}`);
  for (const c of r.criteria || []) {
    console.log(`  · ${c.title}: ${c.points}/${c.max_points} — ${c.reason}`);
  }
  if (r.rules_applied?.length) console.log(`  правила: ${r.rules_applied.join('; ')}`);
}
