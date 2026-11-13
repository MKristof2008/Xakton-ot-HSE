import { apiBaseUrl, requestTimeoutMs } from '../config';
import type { Deal, Listing, Offer, OfferCheck, SignalResult, Stats, Trust } from '../types';
import { ApiError } from './errors';
import {
  isRecord,
  parseCheckResult,
  parseDeal,
  parseListing,
  parseListingList,
  parseOffer,
  parseSignal,
  parseStats,
  parseTrust,
} from './validate';

/**
 * Низкоуровневый HTTP-клиент. Все ошибки приводятся к ApiError с понятным кодом.
 */

async function parseErrorBody(response: Response): Promise<ApiError> {
  let code = `HTTP_${response.status}`;
  let message = '';
  let isJson = false;
  try {
    const body: unknown = await response.json();
    isJson = true;
    if (isRecord(body) && isRecord(body.error)) {
      if (typeof body.error.code === 'string') code = body.error.code;
      if (typeof body.error.message === 'string') message = body.error.message;
    }
  } catch {
    // тело не JSON — остаётся HTTP-код
  }

  // Не-JSON ответ на 5xx обычно отдаёт прокси или шлюз: backend не отвечает.
  if (!isJson && response.status >= 500) {
    return new ApiError('NETWORK', 'Сервер не отвечает', response.status);
  }

  if (code.startsWith('HTTP_')) {
    if (response.status === 404) code = 'NOT_FOUND';
    else if (response.status === 413) code = 'TOO_LARGE';
    else if (response.status === 415) code = 'UNSUPPORTED_TYPE';
    else if (response.status === 400) code = 'BAD_INPUT';
    else if (response.status >= 500) code = 'INTERNAL';
  }
  return new ApiError(code, message || `HTTP ${response.status}`, response.status);
}

async function request(path: string, init: RequestInit, signal?: AbortSignal): Promise<unknown> {
  const controller = new AbortController();
  let timedOut = false;
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort, { once: true });
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, requestTimeoutMs);

  try {
    let response: Response;
    try {
      response = await fetch(`${apiBaseUrl}${path}`, { ...init, signal: controller.signal });
    } catch (error) {
      if (signal?.aborted) throw new ApiError('ABORTED');
      if (timedOut) throw new ApiError('NETWORK', 'Сервер не ответил вовремя');
      throw new ApiError('NETWORK', error instanceof Error ? error.message : undefined);
    }

    if (!response.ok) throw await parseErrorBody(response);

    if (response.status === 204) return null;
    try {
      return await response.json();
    } catch {
      throw new ApiError('CONTRACT', 'ответ не является JSON');
    }
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }
}

/* ---------- listings ---------- */

export async function getListings(signal?: AbortSignal): Promise<Listing[]> {
  return parseListingList(await request('/listings', { method: 'GET' }, signal));
}

export async function getListing(id: string, signal?: AbortSignal): Promise<Listing> {
  return parseListing(await request(`/listings/${encodeURIComponent(id)}`, { method: 'GET' }, signal));
}

export async function buyListing(id: string, signal?: AbortSignal): Promise<Deal> {
  return parseDeal(
    await request(`/listings/${encodeURIComponent(id)}/buy`, { method: 'POST' }, signal),
  );
}

/**
 * Выставление лота по проверенной заявке.
 * В контракте отдельного маршрута нет: backend может создать лот
 * автоматически после проверки. Если маршрута нет — вернётся NOT_FOUND.
 */
export async function createListingForOffer(offerId: string, signal?: AbortSignal): Promise<Listing> {
  return parseListing(
    await request(
      '/listings',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ offer_id: offerId }),
      },
      signal,
    ),
  );
}

/* ---------- offers ---------- */

export interface OfferForm {
  file: File;
  caption: string;
  location: string;
  shotAt: string;
}

export async function createOffer(form: OfferForm, signal?: AbortSignal): Promise<Offer> {
  const body = new FormData();
  body.append('file', form.file, form.file.name);
  body.append('caption', form.caption);
  body.append('location', form.location);
  if (form.shotAt) body.append('shot_at', form.shotAt);
  return parseOffer(await request('/offers', { method: 'POST', body }, signal));
}

export async function getOfferCheck(id: string, signal?: AbortSignal): Promise<OfferCheck> {
  const raw = await request(`/offers/${encodeURIComponent(id)}/check`, { method: 'GET' }, signal);
  const check = parseCheckResult(raw);
  return { ...check, offer_id: check.offer_id || id };
}

/* ---------- stats ---------- */

export async function getStats(signal?: AbortSignal): Promise<Stats> {
  return parseStats(await request('/stats', { method: 'GET' }, signal));
}

/* ---------- SSE ---------- */

export type ProgressHandler = {
  onStatus?: (status: string, message: string) => void;
  onSignal: (signal: SignalResult) => void;
  onTrust?: (trust: Trust) => void;
  /** Backend сам создаёт лот и присылает его id в событии status. */
  onListing?: (listingId: string) => void;
  onDone?: (check: OfferCheck) => void;
  onError?: (message: string) => void;
};

interface RawEvent {
  event: string;
  data: string;
}

/** Разбор потока SSE вручную: fetch + ReadableStream, без EventSource (нужны заголовки). */
export async function streamOfferEvents(
  offerId: string,
  handlers: ProgressHandler,
  signal: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/offers/${encodeURIComponent(offerId)}/events`, {
      method: 'GET',
      headers: { Accept: 'text/event-stream' },
      signal,
    });
  } catch {
    if (signal.aborted) return;
    throw new ApiError('NETWORK');
  }

  if (!response.ok) throw await parseErrorBody(response);
  if (!response.body) throw new ApiError('CONTRACT', 'поток событий пуст');

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  const separator = /\r?\n\r?\n/;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let match = separator.exec(buffer);
      while (match) {
        const chunk = buffer.slice(0, match.index);
        buffer = buffer.slice(match.index + match[0].length);
        const event = parseEventChunk(chunk);
        if (event) dispatchEvent(event, handlers);
        match = separator.exec(buffer);
      }
    }
  } catch (error) {
    if (signal.aborted) return;
    if (error instanceof ApiError) throw error;
    throw new ApiError('NETWORK');
  }
}

function parseEventChunk(chunk: string): RawEvent | null {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of chunk.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue;
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
  }
  return dataLines.length ? { event, data: dataLines.join('\n') } : null;
}

function dispatchEvent(event: RawEvent, handlers: ProgressHandler): void {
  let payload: unknown;
  try {
    payload = JSON.parse(event.data);
  } catch {
    return;
  }
  const record = isRecord(payload) ? payload : {};

  const kind = typeof record.kind === 'string' ? record.kind : event.event;
  switch (kind) {
    case 'status':
      handlers.onStatus?.(
        typeof record.status === 'string' ? record.status : '',
        typeof record.message === 'string' ? record.message : '',
      );
      if (typeof record.listing_id === 'string' && record.listing_id) {
        handlers.onListing?.(record.listing_id);
      }
      break;
    case 'signal':
      try {
        handlers.onSignal(parseSignal(record.signal ?? record, 0));
      } catch {
        // битый сигнал пропускаем, не роняя прогресс
      }
      break;
    case 'trust':
      try {
        handlers.onTrust?.(parseTrust(record.trust ?? record));
      } catch {
        /* ignore */
      }
      break;
    case 'done':
      try {
        handlers.onDone?.(parseCheckResult(record.check ?? record));
      } catch (error) {
        handlers.onError?.(error instanceof Error ? error.message : 'некорректный итог проверки');
      }
      break;
    case 'error':
      handlers.onError?.(typeof record.message === 'string' ? record.message : 'проверка прервалась');
      break;
    default:
      break;
  }
}