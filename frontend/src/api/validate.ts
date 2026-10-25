import { CheckError } from './errors';
import type {
  CheckResponse,
  Claim,
  ClaimStatus,
  EvidenceItem,
  EvidenceRelation,
  OriginalSpan,
  SourceItem,
  TextSpan,
} from '../types';

const STATUSES: readonly ClaimStatus[] = ['supported', 'contradicted', 'context', 'insufficient'];
const RELATIONS: readonly EvidenceRelation[] = ['supports', 'contradicts', 'adds_context'];

function fail(message: string): never {
  throw new CheckError('contract', message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asRecord(value: unknown, field: string): Record<string, unknown> {
  if (!isRecord(value)) fail(`поле ${field} должно быть объектом`);
  return value;
}

function asString(value: unknown, field: string): string {
  if (typeof value !== 'string') fail(`поле ${field} должно быть строкой`);
  return value;
}

function asOptionalString(value: unknown, field: string): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'string') fail(`поле ${field} должно быть строкой или null`);
  return value;
}

function asStringArray(value: unknown, field: string): string[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) fail(`поле ${field} должно быть массивом`);
  return value.filter((item): item is string => typeof item === 'string');
}

function asSpan(value: unknown): TextSpan | null {
  if (!isRecord(value)) return null;
  const { start, end } = value;
  if (typeof start !== 'number' || typeof end !== 'number') return null;
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start) return null;
  return { start, end };
}

/** original_span приходит либо точной строкой (ML-пайплайн), либо позицией. */
function asOriginalSpan(value: unknown): OriginalSpan | null {
  if (typeof value === 'string') return value.trim() ? value : null;
  return asSpan(value);
}

function parseEvidence(raw: unknown, claimIndex: number, itemIndex: number): EvidenceItem {
  const field = `claims[${claimIndex}].evidence[${itemIndex}]`;
  const record = asRecord(raw, field);
  const relation = asString(record.relation, `${field}.relation`);
  if (!RELATIONS.includes(relation as EvidenceRelation)) {
    fail(`неизвестный тип связи: ${relation}`);
  }
  return {
    source_id: asString(record.source_id, `${field}.source_id`),
    quote: asOptionalString(record.quote, `${field}.quote`) ?? '',
    relation: relation as EvidenceRelation,
    explanation: asOptionalString(record.explanation, `${field}.explanation`) ?? '',
    original_span: asOriginalSpan(record.original_span),
  };
}

function parseClaim(raw: unknown, index: number): Claim {
  const field = `claims[${index}]`;
  const record = asRecord(raw, field);
  const status = asString(record.status, `${field}.status`);
  if (!STATUSES.includes(status as ClaimStatus)) fail(`неизвестный статус утверждения: ${status}`);

  const text = asString(record.text, `${field}.text`).trim();
  if (!text) fail(`поле ${field}.text пустое`);

  const evidenceRaw = record.evidence;
  if (evidenceRaw !== undefined && evidenceRaw !== null && !Array.isArray(evidenceRaw)) {
    fail(`поле ${field}.evidence должно быть массивом`);
  }
  const evidence = Array.isArray(evidenceRaw)
    ? evidenceRaw.map((item, itemIndex) => parseEvidence(item, index, itemIndex))
    : [];

  const id = typeof record.id === 'string' && record.id.trim() ? record.id : `c${index + 1}`;

  return {
    id,
    text,
    status: status as ClaimStatus,
    explanation: asOptionalString(record.explanation, `${field}.explanation`) ?? '',
    evidence,
    limitations: asStringArray(record.limitations, `${field}.limitations`),
    next_action: asOptionalString(record.next_action, `${field}.next_action`) ?? '',
    original_span: asOriginalSpan(record.original_span),
  };
}

function parseSource(raw: unknown, index: number): SourceItem {
  const field = `sources[${index}]`;
  const record = asRecord(raw, field);
  const url = asOptionalString(record.url, `${field}.url`);
  return {
    id: asString(record.id, `${field}.id`),
    title: asOptionalString(record.title, `${field}.title`) ?? '',
    url: url && url.trim() ? url.trim() : null,
    published_at: asOptionalString(record.published_at, `${field}.published_at`),
    retrieved_at: asOptionalString(record.retrieved_at, `${field}.retrieved_at`),
    content_kind: asOptionalString(record.content_kind, `${field}.content_kind`),
    origin: asOptionalString(record.origin, `${field}.origin`),
  };
}

/**
 * Минимальная runtime-проверка ответа. Некорректный ответ превращается
 * в CheckError('contract'), а не роняет приложение.
 */
export function parseCheckResponse(raw: unknown): CheckResponse {
  const root = asRecord(raw, 'response');

  if (!Array.isArray(root.claims)) fail('поле claims должно быть массивом');
  if (root.sources !== undefined && root.sources !== null && !Array.isArray(root.sources)) {
    fail('поле sources должно быть массивом');
  }

  const claims = root.claims.map((item, index) => parseClaim(item, index));
  const sources = Array.isArray(root.sources)
    ? root.sources.map((item, index) => parseSource(item, index))
    : [];

  return {
    claims,
    sources,
    share_text: asOptionalString(root.share_text, 'share_text') ?? '',
    uncheckable_reason: asOptionalString(root.uncheckable_reason, 'uncheckable_reason'),
  };
}
