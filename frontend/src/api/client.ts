import { apiBaseUrl } from '../config';
import type {
  CheckResponse,
  Payment,
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
export async function register(
  email: string,
  password: string,
  name = '',
): Promise<Me> {
  const user = await request<Me & { token: string }>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, name }),
  });
  writeToken(user.token);
  return user;
}

export async function login(email: string, password: string): Promise<Me> {
  const user = await request<Me & { token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  writeToken(user.token);
  return user;
}

export async function logout(): Promise<void> {
  try {
    await request('/auth/logout', { method: 'POST' });
  } catch {
    /* сервер недоступен — токен всё равно убираем локально */
  }
  clearToken();
}

export function clearToken(): void {
  try {
    localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* приватный режим */
  }
}

/** Есть ли сохранённая сессия. Без неё интерфейс показывает вход. */
export function hasSession(): boolean {
  return Boolean(readToken());
}

export async function getMe(): Promise<Me> {
  return request<Me>('/me');
}

export async function runCheck(text: string): Promise<CheckResponse> {
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
  await request('/upgrade', { method: 'POST', body: JSON.stringify({ plan }) });
}

export async function createPayment(
  plan: string,
  method: 'card' | 'sbp' | 'invoice' = 'card',
): Promise<Payment> {
  return request<Payment>('/payments', {
    method: 'POST',
    body: JSON.stringify({ plan, method }),
  });
}

export async function confirmPayment(paymentId: string): Promise<void> {
  await request('/payments/confirm', {
    method: 'POST',
    body: JSON.stringify({ payment_id: paymentId }),
  });
}
