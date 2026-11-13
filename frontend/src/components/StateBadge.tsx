import type { ListingState } from '../types';
import { LISTING_STATE_LABELS } from '../lib/labels';

/** Статус лота: в продаже / продан / зарезервирован. */
export function StateBadge({ state }: { state: ListingState }) {
  return <span className={`state state--${state}`}>{LISTING_STATE_LABELS[state]}</span>;
}