/** Типы ответов API «Ревизор». Отражают backend/main.py один в один. */

export type Level = 'confirmed' | 'likely_real' | 'fog' | 'doubtful' | 'likely_fake';

export type Plan = 'free' | 'pro' | 'team';

export type Verdict = 'правда' | 'фейк' | 'непонятно';

export interface Signal {
  id: string;
  name: string;
  stage: string;
  verdict: 'supports_real' | 'supports_fake' | 'neutral' | 'unavailable';
  strength: number;
  reliability: number;
  summary: string;
  details: Record<string, unknown>;
}

export interface DebateThesis {
  text: string;
  signal_ids: string[];
}

export interface ProvenanceEntry {
  date: string | null;
  where: string;
  note: string;
}

export interface NextStep {
  kind: string;
  title: string;
  why: string;
}

/** Ответ проверки. В free-тарифе разборных полей нет — это не баг, а тариф. */
export interface CheckResponse {
  id: string;
  verdict: Verdict;
  level: Level;
  level_label: string;
  score: number;
  uncertainty: number;
  plan: Plan;
  upgrade_hint?: string;
  quota_left?: number | null;
  signals?: Signal[];
  debate?: { for_real: DebateThesis[]; for_fake: DebateThesis[] };
  provenance?: ProvenanceEntry[];
  next_steps?: NextStep[];
  limits?: string[];
  duration_ms?: number;
  /** Постоянная ссылка на публичный паспорт утверждения. */
  passport?: string;
  /** Разобранные утверждения — только в pro-тарифе. */
  claims?: ClaimFinding[];
  sources_used?: number;
  /** Объяснение по фото или видео: от модели или от детекторов. */
  explanation?: string;
  explanation_source?: 'model' | 'detectors';
  model_verdict?: 'real' | 'fake' | 'unclear';
}

export interface ClaimFinding {
  text: string;
  status: 'supported' | 'contradicted' | 'context' | 'insufficient';
  explanation: string;
  quote: string;
  source_title: string;
  source_url: string;
  trusted: boolean;
  limitations: string[];
}

export interface TopItem {
  text_hash: string;
  sample_text: string;
  checks_count: number;
  last_at: string;
  verdict: Verdict;
  score: number;
  level: Level;
  level_label: string;
  verdict_variants: number;
  pinned: boolean;
  /** Сколько проверок за последний час и минуту — «живость» новости. */
  last_hour?: number;
  last_minute?: number;
}

export interface TopResponse {
  window_hours: number;
  items: TopItem[];
}

/** Лента проверенного: что разобрали и с каким итогом. */
export interface FeedItem {
  text_hash: string;
  sample_text: string;
  checks_count: number;
  last_at: string;
  verdict: Verdict;
  score: number;
  level: Level;
  level_label: string;
  passport: string;
}

export interface FeedResponse {
  window_hours: number;
  items: FeedItem[];
  verified: number;
  refuted: number;
  unclear: number;
}

/** Корпоративный ключ: сам ключ приходит только при выпуске. */
export interface ApiKey {
  id: string;
  key?: string;
  prefix: string;
  label: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyUsage {
  days: number;
  checks: number;
}

export interface FeedbackStats {
  days: number;
  total: number;
  ok: number;
  wrong: number;
  accuracy: number | null;
  by_level: Record<string, { total: number; ok: number; wrong: number }>;
}

export interface Stats {
  checks: number;
  unique_claims: number;
  fake: number;
  real: number;
  fog: number;
  pro_users: number;
}

export interface PlanInfo {
  id: Plan;
  name: string;
  price_rub: number;
  price_year_rub?: number;
  limits: string;
  features: string[];
  recommended?: boolean;
}

export interface Me {
  id: string;
  plan: Plan;
  quota_left?: number;
  quota_per_day?: number;
}

export interface Payment {
  id: string;
  plan: string;
  amount_rub: number;
  status: 'pending' | 'paid' | 'failed';
  method: 'card' | 'sbp' | 'invoice';
  created_at: string;
  confirmed_at?: string | null;
  plan_name?: string;
  days?: number;
}

export interface PricingResponse {
  plans: PlanInfo[];
  note: string;
  trial?: { days: number; note: string };
  demo_warning?: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string };
}
