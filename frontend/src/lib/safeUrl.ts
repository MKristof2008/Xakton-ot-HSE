/** Разрешаем только http/https. Остальные схемы не превращаем в ссылку. */
export function safeHttpUrl(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  if (!trimmed) return null;
  try {
    const url = new URL(trimmed);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null;
  } catch {
    return null;
  }
}

/** Короткое читаемое представление ссылки для подписи. */
export function readableUrl(raw: string): string {
  return raw.replace(/^https?:\/\//, '').replace(/\/$/, '');
}
