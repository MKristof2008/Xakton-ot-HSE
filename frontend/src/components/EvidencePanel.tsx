import { useEffect, useState } from 'react';
import type { Claim, SourceItem } from '../types';
import { RELATION_LABELS } from '../lib/labels';
import { QuoteCompare } from './QuoteCompare';
import { SourceBlock } from './SourceBlock';
import { StatusBadge } from './StatusBadge';

interface EvidencePanelProps {
  claim: Claim | null;
  sources: SourceItem[];
}

export function EvidencePanel({ claim, sources }: EvidencePanelProps) {
  const [index, setIndex] = useState(0);
  const claimId = claim?.id ?? null;

  useEffect(() => {
    setIndex(0);
  }, [claimId]);

  if (!claim) return null;

  const sourceById = new Map(sources.map((source) => [source.id, source]));
  const active = claim.evidence[Math.min(index, Math.max(claim.evidence.length - 1, 0))] ?? null;
  const activeSource = active ? sourceById.get(active.source_id) ?? null : null;

  return (
    <section className="card card--evidence" aria-labelledby="evidence-title">
      <div className="card__head">
        <div className="card__headline">
          <h2 className="section-title" id="evidence-title">
            Основания
          </h2>
          <StatusBadge status={claim.status} />
        </div>
        {claim.explanation && <p className="evidence__claim">{claim.explanation}</p>}
      </div>

      {claim.evidence.length === 0 ? (
        <>
          <div className="empty">
            <p className="empty__title">Доказательства не найдены</p>
            <p className="empty__text">
              Во время проверки не нашлось материалов, которые подтверждают или опровергают это
              утверждение. Это не значит, что утверждение неверно.
            </p>
          </div>
          <QuoteCompare claimText={claim.text} quote={null} />
        </>
      ) : (
        <>
          {claim.evidence.length > 1 && (
            <div className="evidence__tabs" role="tablist" aria-label="Доказательства утверждения">
              {claim.evidence.map((item, itemIndex) => (
                <button
                  key={`${item.source_id}-${itemIndex}`}
                  type="button"
                  role="tab"
                  aria-selected={itemIndex === index}
                  className={`tab${itemIndex === index ? ' is-active' : ''}`}
                  onClick={() => setIndex(itemIndex)}
                >
                  {`Доказательство ${itemIndex + 1}`}
                </button>
              ))}
            </div>
          )}

          <div className="fade-swap" key={`${claim.id}-${index}`}>
            <div className="compare__head">
              <p className={`relation relation--${active?.relation ?? 'adds_context'}`}>
                {active ? RELATION_LABELS[active.relation] : ''}
              </p>
              <p className="compare__hint">
                {activeSource?.title ? activeSource.title : 'Источник недоступен'}
              </p>
            </div>
            <QuoteCompare claimText={claim.text} quote={active?.quote ?? null} />
            {active?.explanation && <p className="evidence__explanation">{active.explanation}</p>}
            <SourceBlock source={activeSource} />
          </div>
        </>
      )}

      {claim.limitations.length > 0 && (
        <div className="limits">
          <h3 className="limits__title">Ограничения проверки</h3>
          <ul className="limits__list">
            {claim.limitations.map((limitation, itemIndex) => (
              <li key={itemIndex}>{limitation}</li>
            ))}
          </ul>
        </div>
      )}

      {claim.next_action && (
        <div className="next-step">
          <h3 className="limits__title">Следующий шаг</h3>
          <p className="next-step__text">{claim.next_action}</p>
        </div>
      )}
    </section>
  );
}
