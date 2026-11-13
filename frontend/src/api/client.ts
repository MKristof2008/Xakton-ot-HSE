import { apiBaseUrl } from '../config';
import type {
  CheckResponse,
  Me,
  PricingResponse,
  Stats,
  TopResponse,
} from '../types';

const TOKEN_KEY = 'provereno_token';

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

function readToken(): string | null {
  // ?token= нужен только для демо-скриншотов и проверки тарифа в браузере.
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('token');
    if (fromUrl) {
      localStorage.setItem(TOKEN_KEY, fromUrl);
      return fromUrl;
    }
  } catch {
    /* ignore */
  }
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeToken(token: string): void {
  try {
    localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* приватный режим — просто работаем без сохранения */
  }
}

export function currentToken(): string | null {
  return readToken();
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = readToken();
  if (token) headers.set('X-Token', token);
  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers });
  } catch {
    throw new ApiError('NETWORK', 'Сервер недоступен. Проверьте, что он запущен.', 0);
  }

  if (!response.ok) {
    let code = `HTTP_${response.status}`;
    let message = 'Запрос не выполнен';
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } };
      if (body?.error?.code) code = body.error.code;
      if (body?.error?.message) message = body.error.message;
    } catch {
      /* тело не JSON */
    }
    throw new ApiError(code, message, response.status);
  }
  return (await response.json()) as T;
}

/** Гостевой пользователь: создаётся один раз и живёт в localStorage. */
export async function ensureUser(): Promise<void> {
  if (readToken()) return;
  const user = await request<{ id: string; token: string }>('/users', { method: 'POST' });
  writeToken(user.token);
}

export async function getMe(): Promise<Me> {
  return request<Me>('/me');
}

export async function runCheck(text: string): Promise<CheckResponse> {
  await ensureUser();
  return request<CheckResponse>('/check', {
    method: 'POST',
    body: JSON.stringify({ text }),
  });
}

export async function getTop(hours = 48): Promise<TopResponse> {
  return request<TopResponse>(`/top?hours=${hours}`);
}

export async function getStats(): Promise<Stats> {
  return request<Stats>('/stats');
}

export async function getPricing(): Promise<PricingResponse> {
  return request<PricingResponse>('/pricing');
}

export async function upgrade(plan = 'pro'): Promise<void> {
  await ensureUser();
  await request('/upgrade', { method: 'POST', body: JSON.stringify({ plan }) });
}
