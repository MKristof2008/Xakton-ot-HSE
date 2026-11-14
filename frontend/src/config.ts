/**
 * Конфигурация фронтенда. В dev запросы идут через прокси Vite на backend.
 */

/** База API. В dev проксируется на backend (см. vite.config.ts). */
export const apiBaseUrl = (import.meta.env.VITE_API_URL ?? '').trim().replace(/\/$/, '') || '/api';

/** Лимит длины проверяемого текста — согласован с backend. */
export const maxTextLength = 4000;
