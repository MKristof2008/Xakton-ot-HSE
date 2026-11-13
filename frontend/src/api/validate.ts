import type {

  Deal,
  DealStatus,
  Level,
  Listing,
  ListingFacts,
  ListingState,
  Offer,
  OfferCheck,
  OfferFile,
  OfferStatus,
  SignalResult,
  Stats,
  Stage,
  Trust,
  Verdict,
} from '../types';
import { ApiError } from './errors';

const LEVELS: readonly Level[] = ['confirmed', 'likely_real', 'fog', 'doubtful', 'likely_fake'];
const VERDICTS: readonly Verdict[] = ['supports_real', 'supports_fake', 'neutral', 'unavailable'];
const STAGES: readonly Stage[] = ['provenance', 'artifacts', 'sources', 'context'];
const LISTING_STATES: readonly ListingState[] = ['available', 'reserved', 'sold'];
const OFFER_STATUSES: readonly OfferStatus[] = ['checking', 'listed', 'rejected', 'sold'];
const DEAL_STATUSES: readonly DealStatus[] = ['paid', 'delivered', 'refunded'];

function fail(message: string): never {
  throw new ApiError('CONTRACT', message);
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asRecord(value: unknown, field: string): Record<string, unknown> {
  if (!isRecord(value)) fail(`поле ${field} должно быть объектом`);
  return value;
}

function str(value: unknown, field: string, fallback = ''): string {
  if (value === undefined || value === null) return fallback;
  if (typeof value !== 'string') fail(`поле ${field} должно быть строкой`);
  return value;
}

function strOrNull(value: unknown, field: string): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'string') fail(`поле ${field} должно быть строкой или null`);
  return value;
}

function num(value: unknown, field: string, fallback = 0): number {
  if (value === undefined || value === null) return fallback;
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(`поле ${field} должно быть числом`);
  return value;
}

function bool(value: unknown, field: string, fallback = false): boolean {
  if (value === undefined || value === null) return fallback;
  if (typeof value !== 'boolean') fail(`поле ${field} должно быть логическим`);
  return value;
}

function int(value: unknown, field: string, fallback = 0): number {
  return Math.round(num(value, field, fallback));
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], field: string, fallback: T): T {
  if (value === undefined || value === null) return fallback;
  if (typeof value !== 'string' || !(allowed as readonly string[]).includes(value)) {
    fail(`поле ${field} имеет неизвестное значение: ${String(value)}`);
  }
  return value as T;
}

function strArray(value: unknown, field: string): string[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) fail(`поле ${field} должно быть массивом`);
  return value.filter((item): item is string => typeof item === 'string');
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/* ---------- Trust ---------- */

export function parseTrust(raw: unknown, field = 'trust'): Trust {
  const record = asRecord(raw, field);
  return {
    score: Math.min(100, Math.max(0, int(record.score, `${field}.score`))),
    uncertainty: clamp01(num(record.uncertainty, `${field}.uncertainty`, 1)),
    coverage: clamp01(num(record.coverage, `${field}.coverage`, 0)),
    level: oneOf(record.level, LEVELS, `${field}.level`, 'fog'),
    conflict: bool(record.conflict, `${field}.conflict`),
  };
}

/* ---------- Signal ---------- */

export function parseSignal(raw: unknown, index: number): SignalResult {
  const field = `signals[${index}]`;
  const record = asRecord(raw, field);
  const id = str(record.id, `${field}.id`);
  if (!id) fail(`поле ${field}.id пустое`);
  return {
    id,
    name: str(record.name, `${field}.name`, id),
    stage: oneOf(record.stage, STAGES, `${field}.stage`, 'context'),
    verdict: oneOf(record.verdict, VERDICTS, `${field}.verdict`, 'unavailable'),
    strength: clamp01(num(record.strength, `${field}.strength`)),
    reliability: clamp01(num(record.reliability, `${field}.reliability`)),
    summary: str(record.summary, `${field}.summary`),
    details: isRecord(record.details) ? record.details : {},
  };
}

export function parseSignalList(raw: unknown): SignalResult[] {
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) fail('поле signals должно быть массивом');
  return raw.map((item, index) => parseSignal(item, index));
}

/* ---------- CheckResult ---------- */

export function parseCheckResult(raw: unknown): OfferCheck {
  const record = asRecord(raw, 'check');
  const input = asRecord(record.input, 'check.input');
  return {
    id: str(record.id, 'check.id') || fail('поле check.id пустое'),
    status: oneOf(record.status, ['queued', 'running', 'done', 'failed'] as const, 'check.status', 'done'),
    input: {
      type: oneOf(input.type, ['image', 'text', 'url'] as const, 'check.input.type', 'image'),
      sha256: str(input.sha256, 'check.input.sha256'),
      preview_url: strOrNull(input.preview_url, 'check.input.preview_url'),
      extracted_text: strOrNull(input.extracted_text, 'check.input.extracted_text'),
    },
    offer_id: str(record.offer_id, 'check.offer_id'),
    trust: parseTrust(record.trust ?? {}, 'check.trust'),
    signals: parseSignalList(record.signals),
    debate: {
      for_real: parseTheses(record.debate, 'for_real'),
      for_fake: parseTheses(record.debate, 'for_fake'),
    },
    provenance: [],
    next_steps: [],
    limits: strArray(record.limits, 'check.limits'),
    duration_ms: int(record.duration_ms, 'check.duration_ms'),
  };
}

function parseTheses(raw: unknown, key: 'for_real' | 'for_fake'): { text: string }[] {
  if (!isRecord(raw)) return [];
  const list = raw[key];
  if (!Array.isArray(list)) return [];
  return list
    .map((item) => (isRecord(item) ? { text: str(item.text, 'debate.text') } : null))
    .filter((item): item is { text: string } => item !== null && item.text !== '');
}

/* ---------- Listing ---------- */

function parseFacts(raw: unknown): ListingFacts {
  const record = isRecord(raw) ? raw : {};
  return {
    origin: str(record.origin, 'facts.origin'),
    shot_at: strOrNull(record.shot_at, 'facts.shot_at'),
    geo: str(record.geo, 'facts.geo'),
    unique: bool(record.unique, 'facts.unique'),
    similar_in_archive: int(record.similar_in_archive, 'facts.similar_in_archive'),
  };
}

export function parseListing(raw: unknown, index = 0): Listing {
  const field = `listings[${index}]`;
  const record = asRecord(raw, field);
  const id = str(record.id, `${field}.id`);
  if (!id) fail(`поле ${field}.id пустое`);
  return {
    id,
    offer_id: str(record.offer_id, `${field}.offer_id`),
    check_id: str(record.check_id, `${field}.check_id`),
    title: str(record.title, `${field}.title`, 'Без названия'),
    price_rub: int(record.price_rub, `${field}.price_rub`),
    currency: str(record.currency, `${field}.currency`, 'RUB'),
    state: oneOf(record.state, LISTING_STATES, `${field}.state`, 'available'),
    created_at: str(record.created_at, `${field}.created_at`),
    expires_at: str(record.expires_at, `${field}.expires_at`),
    trust: parseTrust(record.trust ?? {}, `${field}.trust`),
    facts: parseFacts(record.facts),
    why_price: strArray(record.why_price, `${field}.why_price`),
    preview_url: strOrNull(record.preview_url, `${field}.preview_url`),
  };
}

export function parseListingList(raw: unknown): Listing[] {
  const items = Array.isArray(raw) ? raw : isRecord(raw) && Array.isArray(raw.items) ? raw.items : null;
  if (!items) fail('список лотов должен быть массивом или { items: [] }');
  return items.map((item, index) => parseListing(item, index));
}

/* ---------- Offer ---------- */

function parseOfferFile(raw: unknown): OfferFile {
  const record = isRecord(raw) ? raw : {};
  return {
    name: str(record.name, 'offer.file.name'),
    size: int(record.size, 'offer.file.size'),
    mime: str(record.mime, 'offer.file.mime'),
    sha256: str(record.sha256, 'offer.file.sha256'),
    preview_url: strOrNull(record.preview_url, 'offer.file.preview_url'),
  };
}

export function parseOffer(raw: unknown): Offer {
  const record = asRecord(raw, 'offer');
  const id = str(record.id, 'offer.id');
  if (!id) fail('поле offer.id пустое');
  const author = isRecord(record.author) ? record.author : {};
  return {
    id,
    status: oneOf(record.status, OFFER_STATUSES, 'offer.status', 'checking'),
    created_at: str(record.created_at, 'offer.created_at'),
    author: {
      id: str(author.id, 'offer.author.id'),
      display_name: str(author.display_name, 'offer.author.display_name', 'Аноним'),
      payout: int(author.payout, 'offer.author.payout'),
    },
    file: parseOfferFile(record.file),
    caption: str(record.caption, 'offer.caption'),
    location: str(record.location, 'offer.location'),
    shot_at: strOrNull(record.shot_at, 'offer.shot_at'),
  };
}

/* ---------- Deal ---------- */

export function parseDeal(raw: unknown): Deal {
  const record = asRecord(raw, 'deal');
  const id = str(record.id, 'deal.id');
  if (!id) fail('поле deal.id пустое');
  const buyer = isRecord(record.buyer) ? record.buyer : {};
  return {
    id,
    listing_id: str(record.listing_id, 'deal.listing_id'),
    buyer: {
      id: str(buyer.id, 'deal.buyer.id'),
      name: str(buyer.name, 'deal.buyer.name', 'Редакция'),
    },
    amount_rub: int(record.amount_rub, 'deal.amount_rub'),
    commission_rub: int(record.commission_rub, 'deal.commission_rub'),
    author_payout_rub: int(record.author_payout_rub, 'deal.author_payout_rub'),
    status: oneOf(record.status, DEAL_STATUSES, 'deal.status', 'paid'),
    created_at: str(record.created_at, 'deal.created_at'),
  };
}

/* ---------- Stats ---------- */

export function parseStats(raw: unknown): Stats {
  const record = asRecord(raw, 'stats');
  return {
    offers: int(record.offers, 'stats.offers'),
    listings: int(record.listings, 'stats.listings'),
    sold: int(record.sold, 'stats.sold'),
    turnover_rub: int(record.turnover_rub, 'stats.turnover_rub'),
    commission_rub: int(record.commission_rub, 'stats.commission_rub'),
  };
}

/* ---------- Check с offer_id ---------- */

export function withOfferId(check: OfferCheck, offerId: string): OfferCheck {
  return { ...check, offer_id: check.offer_id || offerId };
}