import { maxTextLength } from '../config';
import { EXAMPLES } from '../fixtures/examples';
import type { Example } from '../fixtures/examples';
import { GENERIC_ERROR_MESSAGE, errorHint } from '../api';
import type { CheckErrorKind } from '../api';

interface InputScreenProps {
  text: string;
  onTextChange: (value: string) => void;
  onSubmit: () => void;
  onClear: () => void;
  onPickExample: (example: Example) => void;
  validationError: string | null;
  apiErrorKind: CheckErrorKind | null;
  isLoading: boolean;
  onRetry: () => void;
}

export function InputScreen({
  text,
  onTextChange,
  onSubmit,
  onClear,
  onPickExample,
  validationError,
  apiErrorKind,
  isLoading,
  onRetry,
}: InputScreenProps) {
  const isOverLimit = text.length > maxTextLength;
  const describedBy = ['message-hint', 'message-counter', validationError ? 'message-error' : '']
    .filter(Boolean)
    .join(' ');

  return (
    <div className="screen screen--input">
      <div className="hero">
        <h1 className="hero__title">Прежде чем переслать — проверь основание</h1>
        <p className="hero__subtitle">
          Разберём сообщение на утверждения и покажем, что удалось подтвердить источниками.
        </p>
      </div>

      {apiErrorKind && (
        <div className="alert" role="alert">
          <div className="alert__body">
            <p className="alert__title">{GENERIC_ERROR_MESSAGE}</p>
            <p className="alert__text">{errorHint(apiErrorKind)}</p>
          </div>
          <button type="button" className="btn btn--ghost" onClick={onRetry}>
            Попробовать снова
          </button>
        </div>
      )}

      <form
        className="card card--input"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit();
        }}
      >
        <div className="field">
          <label className="field__label" htmlFor="message">
            Сообщение
          </label>
          <p className="field__hint" id="message-hint">
            Вставьте текст, который собираетесь переслать. Проверим до трёх утверждений.
          </p>
          <textarea
            id="message"
            className="field__textarea"
            value={text}
            rows={8}
            disabled={isLoading}
            placeholder="Например: «С 1 ноября библиотека переходит на круглосуточный режим»"
            aria-describedby={describedBy}
            aria-invalid={Boolean(validationError) || isOverLimit}
            onChange={(event) => onTextChange(event.target.value)}
          />
          <div className="field__meta">
            <span className={`field__counter${isOverLimit ? ' is-over' : ''}`} id="message-counter">
              {text.length} / {maxTextLength}
            </span>
            <span className="field__safety">Не вставляйте пароли и персональные данные</span>
          </div>
          {validationError && (
            <p className="field__error" id="message-error" role="alert">
              {validationError}
            </p>
          )}
        </div>

        <div className="actions">
          <button type="submit" className="btn btn--primary" disabled={isLoading}>
            {isLoading ? 'Проверяем…' : 'Проверить сообщение'}
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={onClear}
            disabled={isLoading || (!text && !validationError)}
          >
            Очистить
          </button>
        </div>

        {isLoading && (
          <p className="loading" role="status">
            <span className="spinner" aria-hidden="true" />
            Сопоставляем утверждения с доступными материалами
          </p>
        )}
      </form>

      <section className="examples" aria-labelledby="examples-title">
        <div className="examples__head">
          <h2 className="section-title" id="examples-title">
            Учебные примеры
          </h2>
          <p className="section-hint">
            Организации и события вымышлены. Нажатие заполняет поле — проверка не запускается автоматически.
          </p>
        </div>
        <ul className="examples__list">
          {EXAMPLES.map((example) => (
            <li key={example.id}>
              <button
                type="button"
                className="example"
                onClick={() => onPickExample(example)}
                disabled={isLoading}
              >
                <span className="example__title">{example.title}</span>
                <span className="example__hint">{example.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
