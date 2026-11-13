import type { SignalResult } from '../types';
import { STAGE_LABELS } from '../lib/labels';
import { formatPercent } from '../lib/format';
import { StatusBadge } from './StatusBadge';

interface SignalCardProps {
  signal: SignalResult;
  index: number;
  /** Анимация появления: сигнал только что пришёл. */
  fresh?: boolean;
}

/**
 * Карточка одного сигнала проверки: имя, вердикт, сила, надёжность, пояснение.
 * Показывает только то, что прислал backend — ничего не додумывает.
 */
export function SignalCard({ signal, index, fresh = false }: SignalCardProps) {
  return (
    <article
      className={`signal${fresh ? ' signal--fresh' : ''}`}
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
    >
      <header className="signal__head">
        <div className="signal__title">
          <span className="signal__stage">{STAGE_LABELS[signal.stage]}</span>
          <h3 className="signal__name">{signal.name}</h3>
        </div>
        <StatusBadge verdict={signal.verdict} />
      </header>

      <div className="signal__meters">
        <Meter label="Сила" value={signal.strength} />
        <Meter label="Надёжность" value={signal.reliability} />
      </div>

      {signal.summary && <p className="signal__summary">{signal.summary}</p>}
    </article>
  );
}

function Meter({ label, value }: { label: string; value: number }) {
  const percent = Math.round(Math.min(1, Math.max(0, value)) * 100);
  return (
    <div className="meter">
      <div className="meter__row">
        <span className="meter__label">{label}</span>
        <span className="meter__value">{formatPercent(value)}</span>
      </div>
      <div
        className="meter__track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <span className="meter__fill" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}