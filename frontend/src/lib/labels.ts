import type { ClaimStatus, EvidenceRelation } from '../types';

/** Подписи статусов утверждений. */
export const STATUS_LABELS: Record<ClaimStatus, string> = {
  supported: 'Подтверждается источниками',
  contradicted: 'Противоречит источникам',
  context: 'Нужно уточнение',
  insufficient: 'Недостаточно данных',
};

/** Иконка статуса: статус различается не только цветом. */
export const STATUS_ICONS: Record<ClaimStatus, string> = {
  supported: '✓',
  contradicted: '✕',
  context: '!',
  insufficient: '?',
};

export const RELATION_LABELS: Record<EvidenceRelation, string> = {
  supports: 'Подтверждает',
  contradicts: 'Противоречит',
  adds_context: 'Добавляет контекст',
};
