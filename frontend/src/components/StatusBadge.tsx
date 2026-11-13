import type { Verdict } from '../types';
import { VERDICT_ICONS, VERDICT_LABELS } from '../lib/labels';

/** Вердикт сигнала проверки. */
export function StatusBadge({ verdict }: { verdict: Verdict }) {
  return (
    <span className={`verdict verdict--${verdict}`}>
      <span className="verdict__icon" aria-hidden="true">
        {VERDICT_ICONS[verdict]}
      </span>
      {VERDICT_LABELS[verdict]}
    </span>
  );
}