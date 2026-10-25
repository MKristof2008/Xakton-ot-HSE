import { useCallback, useRef, useState } from 'react';
import { requestCheck, toCheckError } from '../api';
import type { CheckError } from '../api';
import type { CheckResponse } from '../types';

export type Phase =
  | { kind: 'idle' }
  | { kind: 'loading'; text: string }
  | { kind: 'result'; text: string; data: CheckResponse }
  | { kind: 'error'; text: string; error: CheckError };

export interface CheckMessageApi {
  phase: Phase;
  isLoading: boolean;
  run: (text: string) => Promise<void>;
  reset: () => void;
}

/**
 * Управление одной проверкой. Ответ устаревшего запроса не перезаписывает
 * новый: каждый запуск получает номер, предыдущий запрос отменяется.
 */
export function useCheckMessage(): CheckMessageApi {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const runIdRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const cancelCurrent = useCallback(() => {
    runIdRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const run = useCallback(async (text: string) => {
    runIdRef.current += 1;
    const runId = runIdRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setPhase({ kind: 'loading', text });

    try {
      const data = await requestCheck(text, controller.signal);
      if (runId !== runIdRef.current) return;
      setPhase({ kind: 'result', text, data });
    } catch (error) {
      if (runId !== runIdRef.current) return;
      const checkError = toCheckError(error);
      if (checkError.kind === 'aborted') return;
      setPhase({ kind: 'error', text, error: checkError });
    }
  }, []);

  const reset = useCallback(() => {
    cancelCurrent();
    setPhase({ kind: 'idle' });
  }, [cancelCurrent]);

  return { phase, isLoading: phase.kind === 'loading', run, reset };
}
