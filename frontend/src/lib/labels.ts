import type { DealStatus, Level, ListingState, OfferStatus, Verdict } from '../types';

export const LEVEL_LABELS: Record<Level, string> = {
  confirmed: 'Подтверждено',
  likely_real: 'Скорее подлинное',
  fog: 'Туман',
  doubtful: 'Сомнительно',
  likely_fake: 'Скорее фейк',
};

export const LEVEL_ICONS: Record<Level, string> = {
  confirmed: '✓',
  likely_real: '↑',
  fog: '?',
  doubtful: '!',
  likely_fake: '✕',
};

export const VERDICT_LABELS: Record<Verdict, string> = {
  supports_real: 'За подлинность',
  supports_fake: 'За подделку',
  neutral: 'Нейтрально',
  unavailable: 'Недоступно',
};

export const VERDICT_ICONS: Record<Verdict, string> = {
  supports_real: '✓',
  supports_fake: '✕',
  neutral: '·',
  unavailable: '—',
};

export const STAGE_LABELS = {
  provenance: 'Происхождение',
  artifacts: 'Артефакты',
  sources: 'Источники',
  context: 'Контекст',
} as const;

export const LISTING_STATE_LABELS: Record<ListingState, string> = {
  available: 'В продаже',
  reserved: 'Зарезервирован',
  sold: 'Продан',
};

export const OFFER_STATUS_LABELS: Record<OfferStatus, string> = {
  checking: 'Проверяется',
  listed: 'Выставлен',
  rejected: 'Отклонён',
  sold: 'Продан',
};

export const DEAL_STATUS_LABELS: Record<DealStatus, string> = {
  paid: 'Оплачено',
  delivered: 'Доставлено',
  refunded: 'Возврат',
};

export const TRUST_LEVEL_HINT: Record<Level, string> = {
  confirmed: 'Все проверки сошлись, материал можно брать в работу.',
  likely_real: 'Скорее подлинное: часть сигналов недоступна или слабая.',
  fog: 'Мало данных: доверять без дополнительной проверки нельзя.',
  doubtful: 'Сигналы противоречат друг другу. Нужна ручная проверка.',
  likely_fake: 'Есть признаки подделки — покупать не стоит.',
};