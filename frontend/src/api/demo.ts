import { CheckError } from './errors';
import { DEMO_FIXTURES, DEMO_UNKNOWN_TEXT } from '../fixtures/demoResponses';
import { findExampleByText } from '../fixtures/examples';
import type { CheckResponse } from '../types';

const DEMO_DELAY_MS = 700;

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new CheckError('aborted'));
      return;
    }
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(timer);
      reject(new CheckError('aborted'));
    }
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

function cloneResponse(response: CheckResponse): CheckResponse {
  return JSON.parse(JSON.stringify(response)) as CheckResponse;
}

/**
 * Демонстрационный источник данных: те же типы и формат, что у live API.
 * Подбор fixture идёт по тексту учебного примера.
 */
export async function requestDemoCheck(text: string, signal: AbortSignal): Promise<CheckResponse> {
  await wait(DEMO_DELAY_MS, signal);
  const example = findExampleByText(text);
  const fixture = example ? DEMO_FIXTURES[example.id] : DEMO_UNKNOWN_TEXT;
  return cloneResponse(fixture);
}
