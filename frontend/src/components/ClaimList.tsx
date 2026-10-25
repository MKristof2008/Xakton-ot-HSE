import type { CSSProperties } from 'react';
import type { Claim } from '../types';
import { evidenceCountLabel } from '../lib/plural';
import { StatusBadge } from './StatusBadge';

interface ClaimListProps {
  claims: Claim[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  registerCard: (id: string, element: HTMLElement | null) => void;
}

export function ClaimList({ claims, selectedId, onSelect, registerCard }: ClaimListProps) {
  return (
    <section className="card card--claims" aria-labelledby="claims-title">
      <div className="card__head">
        <h2 className="section-title" id="claims-title">
          Утверждения
        </h2>
        <p className="section-hint">Выберите утверждение, чтобы открыть доказательства.</p>
      </div>
      <ol className="claims">
        {claims.map((claim, index) => {
          const isSelected = claim.id === selectedId;
          return (
            <li key={claim.id} style={{ '--i': index } as CSSProperties}>
              <button
                type="button"
                className={`claim claim--${claim.status}${isSelected ? ' is-selected' : ''}`}
                aria-pressed={isSelected}
                onClick={() => onSelect(claim.id)}
                ref={(element) => {
                  registerCard(claim.id, element);
                }}
              >
                <span className="claim__top">
                  <span className="claim__number">{String(index + 1).padStart(2, '0')}</span>
                  <StatusBadge status={claim.status} />
                </span>
                <span className="claim__text">{claim.text}</span>
                {claim.explanation && <span className="claim__explanation">{claim.explanation}</span>}
                <span className="claim__meta">
                  {claim.evidence.length > 0
                    ? evidenceCountLabel(claim.evidence.length)
                    : 'Доказательств нет'}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
