import { useState } from 'react';
import { copyText } from '../lib/clipboard';

type CopyState = 'idle' | 'copied' | 'manual';

export function ShareBlock({ text }: { text: string }) {
  const [state, setState] = useState<CopyState>('idle');

  const handleCopy = async () => {
    const copied = await copyText(text);
    setState(copied ? 'copied' : 'manual');
  };

  return (
    <section className="card card--share" aria-labelledby="share-title">
      <div className="card__head">
        <h2 className="section-title" id="share-title">
          Что написать в чат
        </h2>
        <p className="section-hint">
          Короткое уточнение, которое можно отправить в чат вместо исходного сообщения.
        </p>
      </div>
      <p className="share__text">{text}</p>
      <div className="share__actions">
        <button
          type="button"
          className={`btn btn--primary${state === 'copied' ? ' btn--copied' : ''}`}
          onClick={() => void handleCopy()}
        >
          {state === 'copied' ? (
            <>
              <span className="btn__icon" aria-hidden="true">
                ✓
              </span>
              Скопировано
            </>
          ) : (
            'Скопировать уточнение'
          )}
        </button>
        <span className="share__state" role="status" aria-live="polite">
          {state === 'copied' ? 'Текст уточнения в буфере обмена' : ''}
        </span>
      </div>
      {state === 'manual' && (
        <p className="share__hint">
          Браузер не дал доступ к буферу обмена. Выделите текст выше и скопируйте вручную.
        </p>
      )}
    </section>
  );
}
