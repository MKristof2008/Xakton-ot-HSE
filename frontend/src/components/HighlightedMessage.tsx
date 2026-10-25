import { useState } from 'react';
import type { ReactNode } from 'react';
import type { Claim } from '../types';
import { buildSegments } from '../lib/spans';
import { STATUS_LABELS } from '../lib/labels';

interface HighlightedMessageProps {
  text: string;
  claims: Claim[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  registerPhrase: (id: string, element: HTMLElement | null) => void;
}

const COLLAPSE_THRESHOLD = 420;

/**
 * Исходное сообщение как лист бумаги: проверяемые фрагменты подчёркнуты
 * маркером и связаны с карточками. Если backend не прислал original_span,
 * показываем обычный текст — ничего не угадываем.
 */
export function HighlightedMessage({
  text,
  claims,
  selectedId,
  onSelect,
  registerPhrase,
}: HighlightedMessageProps) {
  const [expanded, setExpanded] = useState(false);
  const segments = buildSegments(text, claims);
  const claimById = new Map(claims.map((claim) => [claim.id, claim]));
  const isLong = text.length > COLLAPSE_THRESHOLD;
  const isClamped = isLong && !expanded;

  const nodes: ReactNode[] = [];
  let cursor = 0;

  for (const segment of segments) {
    if (segment.start > cursor) nodes.push(text.slice(cursor, segment.start));
    const claim = claimById.get(segment.claimId);
    const isSelected = segment.claimId === selectedId;
    nodes.push(
      <button
        key={segment.claimId}
        type="button"
        className={`phrase phrase--${claim?.status ?? 'insufficient'}${isSelected ? ' is-selected' : ''}`}
        aria-pressed={isSelected}
        title={claim ? STATUS_LABELS[claim.status] : undefined}
        onClick={() => onSelect(segment.claimId)}
        ref={(element) => {
          registerPhrase(segment.claimId, element);
        }}
      >
        <span className="phrase__text">{text.slice(segment.start, segment.end)}</span>
      </button>,
    );
    cursor = segment.end;
  }
  nodes.push(text.slice(cursor));

  return (
    <section className="card card--paper" aria-labelledby="message-title">
      <div className="card__head">
        <h2 className="section-title" id="message-title">
          Исходное сообщение
        </h2>
        <p className="section-hint">
          {segments.length > 0
            ? 'Подчёркнутые фрагменты связаны с карточками разбора.'
            : 'Разбор открыт в карточках справа.'}
        </p>
      </div>
      <div className={`paper${isClamped ? ' paper--clamped' : ''}`}>
        <p className="paper__text">{nodes}</p>
      </div>
      {isLong && (
        <button
          type="button"
          className="link-button"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? 'Свернуть' : 'Показать полностью'}
        </button>
      )}
    </section>
  );
}
