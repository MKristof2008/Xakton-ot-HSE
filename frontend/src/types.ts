/** Контракт ответа POST /api/check. */

export type ClaimStatus = 'supported' | 'contradicted' | 'context' | 'insufficient';

export type EvidenceRelation = 'supports' | 'contradicts' | 'adds_context';

/** Позиция фрагмента в исходном сообщении (опционально, присылает backend). */
export interface TextSpan {
  start: number;
  end: number;
}

/**
 * Фрагмент исходного сообщения: либо точная строка (так отдаёт ML-пайплайн),
 * либо позиция в тексте. Если фрагмент не найден дословно — не подсвечиваем.
 */
export type OriginalSpan = TextSpan | string;

export interface EvidenceItem {
  source_id: string;
  quote: string;
  relation: EvidenceRelation;
  explanation: string;
  original_span?: OriginalSpan | null;
}

export interface Claim {
  id: string;
  text: string;
  status: ClaimStatus;
  explanation: string;
  evidence: EvidenceItem[];
  limitations: string[];
  next_action: string;
  original_span?: OriginalSpan | null;
}

export interface SourceItem {
  id: string;
  title: string;
  url: string | null;
  published_at: string | null;
  retrieved_at: string | null;
  content_kind: string | null;
  origin: string | null;
}

export interface CheckResponse {
  claims: Claim[];
  sources: SourceItem[];
  share_text: string;
  uncheckable_reason: string | null;
}

export interface CheckRequest {
  text: string;
}
