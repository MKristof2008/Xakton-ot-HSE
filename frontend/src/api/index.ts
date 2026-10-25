import { apiMode } from '../config';
import type { CheckResponse } from '../types';
import { requestDemoCheck } from './demo';
import { requestLiveCheck } from './client';

/**
 * Единственная точка переключения demo/live.
 * Компоненты получают данные одного и того же формата и не знают об источнике.
 */
export function requestCheck(text: string, signal: AbortSignal): Promise<CheckResponse> {
  return apiMode === 'live' ? requestLiveCheck(text, signal) : requestDemoCheck(text, signal);
}

export { CheckError, GENERIC_ERROR_MESSAGE, errorHint, toCheckError } from './errors';
export type { CheckErrorKind } from './errors';
