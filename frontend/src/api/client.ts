import { apiUrl, requestTimeoutMs } from '../config';
import type { CheckRequest, CheckResponse } from '../types';
import { CheckError } from './errors';
import { parseCheckResponse } from './validate';

/**
 * Запрос к реальному backend.
 * Отмена пользователем и таймаут различаются, чтобы интерфейс показал
 * корректную причину сбоя.
 */
export async function requestLiveCheck(text: string, signal: AbortSignal): Promise<CheckResponse> {
  const controller = new AbortController();
  let timedOut = false;

  const onOuterAbort = () => controller.abort();
  signal.addEventListener('abort', onOuterAbort, { once: true });
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, requestTimeoutMs);

  const body: CheckRequest = { text };

  try {
    let response: Response;
    try {
      response = await fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (error) {
      if (timedOut) throw new CheckError('timeout');
      if (signal.aborted) throw new CheckError('aborted');
      throw new CheckError('network', error instanceof Error ? error.message : undefined);
    }

    if (!response.ok) {
      throw new CheckError('server', `HTTP ${response.status}`, response.status);
    }

    let raw: unknown;
    try {
      raw = await response.json();
    } catch {
      throw new CheckError('contract', 'ответ не является JSON');
    }

    return parseCheckResponse(raw);
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', onOuterAbort);
  }
}
