import type { ClaimStatus } from '../types';
import { STATUS_ICONS, STATUS_LABELS } from '../lib/labels';

export function StatusBadge({ status }: { status: ClaimStatus }) {
  return (
    <span className={`status status--${status}`}>
      <span className="status__icon" aria-hidden="true">
        {STATUS_ICONS[status]}
      </span>
      {STATUS_LABELS[status]}
    </span>
  );
}
