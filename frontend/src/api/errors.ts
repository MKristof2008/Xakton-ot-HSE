import type { ApiErrorCode } from '../types';

export class ApiError extends Error {
  readonly code: ApiErrorCode | string;
  readonly status: number | undefined;

  constructor(code: ApiErrorCode | string, message?: string, status?: number) {
    super(message ?? code);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

const MESSAGES: Record<string, string> = {
  NETWORK: 'Сервер недоступен. Проверьте, что backend запущен.',
  CONTRACT: 'Сервер ответил в неожиданном формате.',
  SERVER: 'Сервер вернул ошибку.',
  ABORTED: 'Запрос отменён.',
  BAD_INPUT: 'Проверьте поля формы и попробуйте ещё раз.',
  TOO_LARGE: 'Файл больше 15 МБ. Уменьшите его и загрузите снова.',
  UNSUPPORTED_TYPE: 'Такой формат не поддерживается. Нужен JPEG, PNG или WebP.',
  NOT_FOUND: 'Такой записи нет — возможно, она уже удалена.',
  ALREADY_SOLD: 'Лот уже продан другому покупателю.',
  CHECK_FAILED: 'Проверка не удалась. Попробуйте загрузить файл ещё раз.',
  INTERNAL: 'Внутренняя ошибка сервера. Попробуйте позже.',
};

export function messageForCode(code: string, fallback?: string): string {
  return MESSAGES[code] ?? (fallback?.trim() ? fallback : 'Что-то пошло не так. Попробуйте ещё раз.');
}

/** Понятный текст ошибки для интерфейса. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return messageForCode(error.code, error.message !== error.code ? error.message : undefined);
  }
  if (error instanceof DOMException && error.name === 'AbortError') {
    return MESSAGES.ABORTED;
  }
  return MESSAGES.NETWORK;
}