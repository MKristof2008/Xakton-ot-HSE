import { apiUrl, requestTimeoutMs } from '../config';
import type { CheckRequest, CheckResponse } from '../types';
import { CheckError } from './errors';
import { parseCheckResponse } from './validate';

/**
 * Backend сейчас отвечает в формате /api/verify-text:
 * { reply, claims: [{ claim_id, text, status, explanation, limitations, next_action }] }.
 * Приводим его к формату CheckResponse до строгой проверки.
 * Компоненты об этом формате не знают.
 */
function normalizeLivePayload(raw: unknown): unknown {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return raw;
  const root: Record<string, unknown> = { ...(raw as Record<string, unknown>) };

  if (root.share_text === undefined && typeof root.reply === 'string') {
    root.share_text = root.reply;
  }

  if (Array.isArray(root.claims)) {
    root.claims = root.claims.map((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) return item;
      const claim: Record<string, unknown> = { ...(item as Record<string, unknown>) };
      if (claim.id === undefined && typeof claim.claim_id === 'string') {
        claim.id = claim.claim_id;
      }
      delete claim.claim_id;
      return claim;
    });
  }

  delete root.reply;
  return root;
}

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

    return parseCheckResponse(normalizeLivePayload(raw));
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', onOuterAbort);
  }
}
