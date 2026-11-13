const rubFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });

/** 4200 → «4 200 ₽». */
export function formatRub(value: number): string {
  return `${rubFormatter.format(Math.round(value))} ₽`;
}

/** 0.84 → «84%». */
export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** «2 часа назад», «3 дня назад». */
export function formatAgo(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return null;
  const minutes = Math.max(0, Math.round((Date.now() - time) / 60_000));
  if (minutes < 2) return 'только что';
  if (minutes < 60) return `${minutes} ${plural(minutes, ['минуту', 'минуты', 'минут'])} назад`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ${plural(hours, ['час', 'часа', 'часов'])} назад`;
  const days = Math.round(hours / 24);
  return `${days} ${plural(days, ['день', 'дня', 'дней'])} назад`;
}

/** «15 000 байт» → «14.6 КБ» / «1.8 МБ». */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}

export function plural(count: number, forms: [string, string, string]): string {
  const abs = Math.abs(count) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}