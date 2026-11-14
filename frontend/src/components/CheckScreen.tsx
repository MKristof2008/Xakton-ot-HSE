import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, getMe, runCheck } from '../api/client';
import type { CheckResponse, Me } from '../types';
import { maxTextLength } from '../config';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { EXAMPLES } from '../lib/examples';
import { VerdictCard } from './VerdictCard';
import { VerdictSkeleton } from './VerdictSkeleton';

interface Props {
  me: Me | null;
  onMe: (me: Me) => void;
}

/** Минимальная выдержка скелетона: вердикт должен ощущаться как решение системы. */
const MIN_SKELETON_MS = 620;

/** Ссылка из мессенджера: «поделиться» вставляет адрес в буфер. */
const LINK_RE = /^https?:\/\/\S+$/i;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** sessionStorage может быть недоступен (приватный режим) — не роняем экран. */
function readPreset(): string | null {
  try {
    return sessionStorage.getItem('preset_text');
  } catch {
    return null;
  }
}

function clearPreset(): void {
  try {
    sessionStorage.removeItem('preset_text');
  } catch {
    /* нечего чистить */
  }
}

export function CheckScreen({ me, onMe }: Props) {
  // ?q=... кладётся в sessionStorage до рендера — забираем его ровно один раз.
  const [preset] = useState(readPreset);
  const [text, setText] = useState(() => preset ?? '');
  // Отдельное поле для ссылки: человек жмёт «поделиться» и вставляет адрес,
  // не задумываясь, что это не текст сообщения.
  const [link, setLink] = useState('');
  const [result, setResult] = useState<CheckResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const reduced = useReducedMotion();
  const resultRef = useRef<HTMLDivElement>(null);

  const submit = useCallback(
    async (raw?: string) => {
      const value = (raw ?? text).trim();
      // Ссылку можно проверить и без текста — бэкенд вытащит его со страницы.
      const onlyUrl = !value && LINK_RE.test(link.trim());
      if (!onlyUrl && value.length < 8) {
        setError(
          link.trim()
            ? 'Ссылка должна начинаться с http:// или https://'
            : 'Нужно хотя бы 8 символов или ссылка — иначе проверять нечего.',
        );
        return;
      }

      setBusy(true);
      setError(null);
      setResult(null);

      try {
        const [data] = await Promise.all([
          runCheck(value, onlyUrl ? link.trim() : null),
          reduced ? Promise.resolve() : delay(MIN_SKELETON_MS),
        ]);
        setResult(data);
        if (typeof data.quota_left === 'number') {
          // Бэкенд отдаёт quota_left только на free — обновляем счётчик, не трогая тариф.
          onMe({ ...(me ?? { id: '', plan: 'free' }), quota_left: data.quota_left });
        }
      } catch (err) {
        if (err instanceof ApiError) {
          setError(err.code === 'QUOTA_EXCEEDED' ? err.message : `Ошибка: ${err.message}`);
        } else {
          setError('Не удалось проверить. Попробуйте ещё раз.');
        }
      } finally {
        setBusy(false);
      }
    },
    [text, link, me, onMe, reduced],
  );

  // ?q=... сразу запускает проверку — так удобно делиться вердиктом.
  useEffect(() => {
    if (!preset) return;
    clearPreset();
    void submit(preset);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Вердикт появился — мягко подводим его в кадр на телефоне.
  useEffect(() => {
    if (!result || !resultRef.current) return;
    const box = resultRef.current.getBoundingClientRect();
    if (box.top > window.innerHeight - 80) {
      resultRef.current.scrollIntoView({
        behavior: reduced ? 'auto' : 'smooth',
        block: 'nearest',
      });
    }
  }, [result, reduced]);

  /** После подписки перепроверяем тот же текст, чтобы разбор раскрылся без перезагрузки. */
  const handleUpgraded = useCallback(async () => {
    try {
      onMe(await getMe());
    } catch {
      /* тариф обновится при следующем запросе */
    }
    const trimmed = text.trim();
    const onlyUrl = !trimmed && LINK_RE.test(link.trim());
    if (!onlyUrl && trimmed.length < 8) return;

    setBusy(true);
    setResult(null);
    try {
      setResult(await runCheck(trimmed, onlyUrl ? link.trim() : null));
    } catch {
      setError('Подписка включена, но разбор не загрузился. Проверьте текст ещё раз.');
    } finally {
      setBusy(false);
    }
  }, [text, link, onMe]);

  const chars = text.length;
  const nearLimit = chars > maxTextLength * 0.9;

  return (
    <div className="view">
      <section className="hero">
        <span className="eyebrow">Проверка новостей</span>
        <h1 className="hero__title">
          Фейк или правда — <em>за одну проверку</em>
        </h1>
        <p className="hero__lead">
          Вставьте сообщение из чата, поста или пересылки. Мы сверим его с курируемой базой
          фактов и покажем, откуда взялась новость.
        </p>
      </section>

      <section className="panel" aria-labelledby="check-form-title">
        <h2 className="visually-hidden" id="check-form-title">
          Проверить сообщение
        </h2>
        {/* Ссылка из мессенджера — отдельное поле: главред спрашивал
            именно про этот сценарий дважды. Текст можно не вставлять. */}
        <div className="field">
          <label className="field__label" htmlFor="check-link">
            <span>Ссылка на новость</span>
            <span className="field__hint">необязательно</span>
          </label>
          <input
            id="check-link"
            className="input"
            type="url"
            inputMode="url"
            autoComplete="off"
            spellCheck={false}
            value={link}
            placeholder="https://t.me/… или адрес сайта"
            onChange={(e) => {
              setLink(e.target.value);
              setError(null);
            }}
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="check-text">
            <span>Текст сообщения</span>
            <span className="field__hint">до {maxTextLength} символов</span>
          </label>
          <textarea
            id="check-text"
            className="textarea"
            rows={5}
            maxLength={maxTextLength}
            value={text}
            aria-describedby="check-counter"
            placeholder="Например: СРОЧНО! ЦБ запретил наличные с 1 марта!"
            onChange={(e) => {
              setText(e.target.value);
              setError(null);
            }}
          />
          <div className="form__foot">
            <span
              className={`counter${nearLimit ? ' counter--near' : ''}`}
              id="check-counter"
            >
              {chars} / {maxTextLength}
            </span>
            <button
              className="btn btn--primary"
              type="button"
              onClick={() => void submit()}
              disabled={busy}
              aria-busy={busy}
            >
              {busy ? (
                <>
                  <span className="btn__spinner" aria-hidden="true" />
                  Проверяем…
                </>
              ) : (
                <>
                  Проверить
                  <span className="btn__arrow" aria-hidden="true">
                    →
                  </span>
                </>
              )}
            </button>
          </div>
        </div>

        <div className="chips" role="group" aria-label="Примеры сообщений">
          <span className="chips__label">Примеры</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="chip"
              title={example}
              onClick={() => {
                setText(example);
                setError(null);
                setResult(null);
              }}
            >
              {example.slice(0, 42)}…
            </button>
          ))}
        </div>
      </section>

      {error && (
        <p className="alert alert--bad" role="alert">
          <span aria-hidden="true">!</span>
          {error}
        </p>
      )}

      <div ref={resultRef} aria-live="polite" aria-atomic="false">
        {busy && <VerdictSkeleton />}
        {!busy && result && (
          <VerdictCard
            key={result.id}
            result={result}
            onUpgraded={() => void handleUpgraded()}
          />
        )}
      </div>

      {!busy && !result && !error && (
        <p className="hint">
          Бесплатно — вердикт и уровень доверия. По подписке — разбор по каждому сигналу
          и ссылки на первоисточники.
        </p>
      )}
    </div>
  );
}
