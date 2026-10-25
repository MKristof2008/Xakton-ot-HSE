import { useState } from 'react';

const COLLAPSE_THRESHOLD = 420;

export function MessageBlock({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = text.length > COLLAPSE_THRESHOLD;

  return (
    <section className="card card--message" aria-labelledby="message-title">
      <div className="card__head">
        <h2 className="section-title" id="message-title">
          Исходное сообщение
        </h2>
      </div>
      <p className={`message__text${isLong && !expanded ? ' message__text--clamped' : ''}`}>{text}</p>
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
