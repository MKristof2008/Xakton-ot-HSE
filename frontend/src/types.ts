/**
 * Типы обмена с backend «Свидетель».
 * Источник истины — docs/CONTRACT.md и contracts/check_result.schema.json.
 */

/* ---------- CheckResult (контракт ML) ---------- */

export type CheckStatus = 'queued' | 'running' | 'done' | 'failed';

export type InputType = 'image' | 'text' | 'url';

export type Stage = 'provenance' | 'artifacts' | 'sources' | 'context';

export type Verdict = 'supports_real' | 'supports_fake' | 'neutral' | 'unavailable';

export type Level = 'confirmed' | 'likely_real' | 'fog' | 'doubtful' | 'likely_fake';

export interface CheckInput {
  type: InputType;
  sha256: string;
  preview_url: string | null;
  extracted_text: string | null;
}

export interface Overlay {
  type: 'heatmap' | 'boxes' | 'regions';
  url: string;
}

export interface SignalResult {
  id: string;
  name: string;
  stage: Stage;
  verdict: Verdict;
  /** 0…1 — насколько сигнал указывает на подлинность */
  strength: number;
  /** 0…1 — насколько сигналу можно доверять */
  reliability: number;
  summary: string;
  details: Record<string, unknown>;
  overlays?: Overlay[];
}

export interface DebateThesis {
  text: string;
  signal_ids?: string[];
}

export interface Debate {
  for_real: DebateThesis[];
  for_fake: DebateThesis[];
}

export interface ProvenanceEntry {
  date: string | null;
  where: string;
  note: string;
}

export interface NextStep {
  kind: 'verify' | 'ask_source' | 'hold' | 'share';
  title: string;
  why: string;
}

export interface Trust {
  score: number;
  uncertainty: number;
  coverage: number;
  level: Level;
  conflict: boolean;
}

export interface CheckResult {
  id: string;
  status: CheckStatus;
  input: CheckInput;
  trust: Trust;
  signals: SignalResult[];
  debate: Debate;
  provenance: ProvenanceEntry[];
  next_steps: NextStep[];
  limits: string[];
  duration_ms: number;
}

/** Backend добавляет к проверке связку с заявкой. */
export interface OfferCheck extends CheckResult {
  offer_id: string;
}

/* ---------- Offer ---------- */

export type OfferStatus = 'checking' | 'listed' | 'rejected' | 'sold';

export interface Author {
  id: string;
  display_name: string;
  payout: number;
}

export interface OfferFile {
  name: string;
  size: number;
  mime: string;
  sha256: string;
  preview_url: string | null;
}

export interface Offer {
  id: string;
  status: OfferStatus;
  created_at: string;
  author: Author;
  file: OfferFile;
  caption: string;
  location: string;
  shot_at: string | null;
}

/* ---------- Listing ---------- */

export type ListingState = 'available' | 'reserved' | 'sold';

export interface ListingFacts {
  origin: string;
  shot_at: string | null;
  geo: string;
  unique: boolean;
  similar_in_archive: number;
}

export interface Listing {
  id: string;
  offer_id: string;
  check_id: string;
  title: string;
  price_rub: number;
  currency: string;
  state: ListingState;
  created_at: string;
  expires_at: string;
  trust: Trust;
  facts: ListingFacts;
  why_price: string[];
  preview_url: string | null;
}

/** Ответ GET /api/listings — backend может отдать массив или объект со списком. */
export interface ListingsResponse {
  items: Listing[];
}

/* ---------- Deal ---------- */

export type DealStatus = 'paid' | 'delivered' | 'refunded';

export interface DealBuyer {
  id: string;
  name: string;
}

export interface Deal {
  id: string;
  listing_id: string;
  buyer: DealBuyer;
  amount_rub: number;
  commission_rub: number;
  author_payout_rub: number;
  status: DealStatus;
  created_at: string;
}

/* ---------- Stats ---------- */

export interface Stats {
  offers: number;
  listings: number;
  sold: number;
  turnover_rub: number;
  commission_rub: number;
}

/* ---------- SSE ---------- */

/** Прогресс проверки: сигналы приходят по одному. */
export type OfferEvent =
  | { kind: 'status'; status: OfferStatus; message?: string }
  | { kind: 'signal'; signal: SignalResult }
  | { kind: 'trust'; trust: Trust }
  | { kind: 'done'; check: OfferCheck }
  | { kind: 'error'; code: string; message: string };

/* ---------- Ошибки API ---------- */

export type ApiErrorCode =
  | 'BAD_INPUT'
  | 'TOO_LARGE'
  | 'UNSUPPORTED_TYPE'
  | 'NOT_FOUND'
  | 'ALREADY_SOLD'
  | 'CHECK_FAILED'
  | 'INTERNAL'
  | 'NETWORK'
  | 'CONTRACT'
  | 'SERVER'
  | 'ABORTED';

export interface ApiErrorBody {
  error: { code: string; message: string };
}