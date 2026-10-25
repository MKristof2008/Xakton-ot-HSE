import type { Claim, OriginalSpan, TextSpan } from '../types';

export interface MessageSegment {
  start: number;
  end: number;
  claimId: string;
}

function resolveSpan(message: string, span: OriginalSpan | null | undefined): TextSpan | null {
  if (!span) return null;

  if (typeof span === 'string') {
    const needle = span.trim();
    if (!needle) return null;
    const start = message.indexOf(needle);
    if (start < 0) return null;
    return { start, end: start + needle.length };
  }

  const { start, end } = span;
  if (!Number.isInteger(start) || !Number.isInteger(end)) return null;
  if (start < 0 || end > message.length || end <= start) return null;
  return { start, end };
}

/**
 * Точные фрагменты сообщения для подсветки. Только дословное совпадение:
 * если backend прислал фрагмент, которого нет в тексте, он пропускается.
 * Пересекающиеся фрагменты отбрасываются, текст не ломается.
 */
export function buildSegments(message: string, claims: Claim[]): MessageSegment[] {
  const ordered: MessageSegment[] = [];

  for (const claim of claims) {
    const span = resolveSpan(message, claim.original_span);
    if (!span) continue;
    const overlaps = ordered.some((item) => span.start < item.end && span.end > item.start);
    if (overlaps) continue;
    ordered.push({ start: span.start, end: span.end, claimId: claim.id });
  }

  return ordered.sort((a, b) => a.start - b.start);
}
