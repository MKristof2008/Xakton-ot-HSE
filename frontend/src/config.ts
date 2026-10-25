/**
 * Конфигурация фронтенда. Значения читаются из переменных окружения Vite
 * и имеют безопасные значения по умолчанию.
 */

export type ApiMode = 'live' | 'demo';

function readInt(raw: string | undefined, fallback: number, min: number, max: number): number {
  const parsed = Number((raw ?? '').trim());
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback;
  return Math.min(max, Math.max(min, Math.floor(parsed)));
}

const rawMode = (import.meta.env.VITE_API_MODE ?? '').trim().toLowerCase();

/** live включается только явным значением VITE_API_MODE=live */
export const apiMode: ApiMode = rawMode === 'live' ? 'live' : 'demo';

export const isDemoMode = apiMode === 'demo';

/**
 * Маршрут проверки. В dev-режиме проксируется на backend (см. vite.config.ts).
 * Backend отдаёт /api/verify-text; если маршрут вернётся к /api/check — задайте VITE_API_URL.
 */
export const apiUrl = (import.meta.env.VITE_API_URL ?? '').trim() || '/api/verify-text';

/** Лимит длины сообщения. Согласовать с backend. */
export const maxTextLength = readInt(import.meta.env.VITE_MAX_TEXT_LENGTH, 4000, 200, 20000);

/** Таймаут запроса проверки. */
export const requestTimeoutMs = readInt(import.meta.env.VITE_API_TIMEOUT_MS, 20000, 3000, 120000);
