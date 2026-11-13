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

/** live включается только явным значением VITE_API_MODE=live. */
export const apiMode: ApiMode = rawMode === 'live' ? 'live' : 'demo';

export const isDemoMode = apiMode === 'demo';

/** База API. В dev проксируется на backend (см. vite.config.ts). */
export const apiBaseUrl = (import.meta.env.VITE_API_URL ?? '').trim().replace(/\/$/, '') || '/api';

/** Таймаут обычного запроса. */
export const requestTimeoutMs = readInt(import.meta.env.VITE_API_TIMEOUT_MS, 20000, 3000, 120000);

/** Лимит размера файла — 15 МБ, как в контракте. */
export const maxFileBytes = 15 * 1024 * 1024;

export const maxFileSizeLabel = '15 МБ';

/** Разрешённые типы файлов. */
export const allowedMimeTypes: readonly string[] = ['image/jpeg', 'image/png', 'image/webp'];

/** Комиссия платформы, доля. */
export const commissionRate = 0.2;