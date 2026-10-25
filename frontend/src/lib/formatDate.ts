const dateFormatter = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});

const dateTimeFormatter = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

/**
 * Даты приходят строками. Если формат не распознан, показываем исходное
 * значение как текст, а не выдумываем дату.
 */
export function formatDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const time = Date.parse(trimmed);
  if (Number.isNaN(time)) return trimmed;
  const date = new Date(time);
  const hasTime = /[T\s]\d{1,2}:\d{2}/.test(trimmed);
  return hasTime ? dateTimeFormatter.format(date) : dateFormatter.format(date);
}
