import type { Level } from '../types';
import { LEVEL_ICONS, LEVEL_LABELS, TRUST_LEVEL_HINT } from '../lib/labels';

interface TrustBadgeProps {
  score: number;
  level: Level;
  /** Компактный вид для карточек ленты. */
  compact?: boolean;
}

/** Бейдж доверия: score + уровень. Уровень различается иконкой, не только цветом. */
export function TrustBadge({ score, level, compact = false }: TrustBadgeProps) {
  return (
    <span
      className={`trust trust--${level}${compact ? ' trust--compact' : ''}`}
      title={TRUST_LEVEL_HINT[level]}
    >
      <span className="trust__icon" aria-hidden="true">
        {LEVEL_ICONS[level]}
      </span>
      <span className="trust__score">{score}</span>
      <span className="trust__level">{LEVEL_LABELS[level]}</span>
    </span>
  );
}