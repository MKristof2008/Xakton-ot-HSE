export type CheckErrorKind = 'network' | 'timeout' | 'server' | 'contract' | 'aborted';

export class CheckError extends Error {
  readonly kind: CheckErrorKind;
  readonly status: number | undefined;

  constructor(kind: CheckErrorKind, message?: string, status?: number) {
    super(message ?? kind);
    this.name = 'CheckError';
    this.kind = kind;
    this.status = status;
  }
}

export const GENERIC_ERROR_MESSAGE = 'Не удалось завершить проверку. Попробуйте ещё раз.';

/** Пояснение под общей фразой об ошибке. Не подменяет её. */
export function errorHint(kind: CheckErrorKind): string {
  switch (kind) {
    case 'network':
      return 'Похоже, пропала связь с сервером.';
    case 'timeout':
      return 'Сервер не ответил вовремя.';
    case 'server':
      return 'Сервер вернул ошибку.';
    case 'contract':
      return 'Ответ сервера пришёл в неожиданном формате.';
    case 'aborted':
      return 'Запрос был отменён.';
  }
}

export function toCheckError(error: unknown): CheckError {
  if (error instanceof CheckError) return error;
  if (error instanceof DOMException && error.name === 'AbortError') {
    return new CheckError('aborted');
  }
  return new CheckError('network', error instanceof Error ? error.message : undefined);
}
