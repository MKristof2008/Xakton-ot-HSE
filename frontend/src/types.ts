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
  limits: string;
  features: string[];
  recommended?: boolean;
}

export interface PricingResponse {
  plans: PlanInfo[];
  note: string;
}

export interface Me {
  id: string;
  plan: Plan;
  quota_left?: number;
  quota_per_day?: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string };
}
