import { useCallback, useEffect, useRef, useState } from 'react';
import type { Listing, Offer, OfferCheck, SignalResult, Trust } from '../types';
import { createListing, describeError, fetchCheck, fetchListing, fetchListings, streamCheck } from '../api';
import { formatRub } from '../lib/format';
import { SignalCard } from './SignalCard';
import { TrustBadge } from './TrustBadge';

interface CheckingScreenProps {
  offer: Offer;
  previewUrl: string | null;
  /** Лот готов — открываем его карточку. */
  onListed: (listingId: string) => void;
  onRestart: () => void;
}

type Phase = 'streaming' | 'done' | 'failed';

/**
 * Экран проверки: сигналы приходят по SSE и появляются по мере готовности.
 * Backend сам создаёт лот в конце проверки — мы показываем настоящие цену
 * и why_price из лота, ничего не досчитывая на клиенте.
 */
export function CheckingScreen({ offer, previewUrl, onListed, onRestart }: CheckingScreenProps) {
  const offerId = offer.id;
  const [signals, setSignals] = useState<SignalResult[]>([]);
  const [trust, setTrust] = useState<Trust | null>(null);
  const [finalCheck, setFinalCheck] = useState<OfferCheck | null>(null);
  const [listing, setListing] = useState<Listing | null>(null);
  const [rejectReason, setRejectReason] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>('streaming');
  const [statusText, setStatusText] = useState('Ставим заявку в очередь');
  const [error, setError] = useState<string | null>(null);
  const [freshId, setFreshId] = useState<string | null>(null);
  const attemptRef = useRef(0);

  const run = useCallback(
    (signal: AbortSignal) => {
      const attempt = ++attemptRef.current;

      const applyFinal = async (check: OfferCheck) => {
        setSignals(check.signals);
        setTrust(check.trust);
        setFinalCheck(check);
        if (check.status === 'failed') {
          setPhase('failed');
          setError('Проверка не удалась на стороне сервера.');
          return;
        }
        setPhase('done');
        // Лот backend создаёт сам: ищем его по заявке.
        try {
          const all = await fetchListings(signal);
          if (attempt !== attemptRef.current || signal.aborted) return;
          const found = all.find((item) => item.offer_id === offerId);
          if (found) setListing(found);
        } catch {
          // Лента недоступна — не страшно, покажем то, что уже есть.
        }
      };

      void (async () => {
        try {
          const result = await streamCheck(
            offerId,
            {
              onStatus: (status, message) => {
                if (message) setStatusText(message);
                if (status === 'rejected' && message) setRejectReason(message);
              },
              onListing: (listingId) => {
                if (attempt !== attemptRef.current) return;
                void fetchListing(listingId, signal)
                  .then((found) => {
                    if (attempt === attemptRef.current) setListing(found);
                  })
                  .catch(() => undefined);
              },
              onSignal: (item) => {
                if (attempt !== attemptRef.current) return;
                setSignals((prev) => (prev.some((s) => s.id === item.id) ? prev : [...prev, item]));
                setFreshId(item.id);
              },
              onTrust: (value) => setTrust(value),
              onDone: (check) => {
                if (attempt !== attemptRef.current) return;
                void applyFinal(check);
              },
              onError: (message) => {
                if (attempt !== attemptRef.current) return;
                setError(message);
              },
            },
            signal,
          );
          if (attempt !== attemptRef.current || signal.aborted) return;
          if (result) await applyFinal(result);
          else await recover();
        } catch (caught) {
          if (signal.aborted || attempt !== attemptRef.current) return;
          await recover(caught);
        }

        async function recover(cause?: unknown) {
          // поток закрылся раньше итога — пробуем обычный запрос
          try {
            const check = await fetchCheck(offerId, signal);
            if (attempt !== attemptRef.current || signal.aborted) return;
            await applyFinal(check);
          } catch (fallbackError) {
            if (attempt !== attemptRef.current || signal.aborted) return;
            setPhase('failed');
            setError(describeError(cause ?? fallbackError));
          }
        }
      })();
    },
    [offerId],
  );

  useEffect(() => {
    const controller = new AbortController();
    run(controller.signal);
    return () => {
      attemptRef.current += 1;
      controller.abort();
    };
  }, [run]);

  const progress = phase === 'streaming' ? Math.min(95, signals.length * 14) : 100;

  return (
    <div className="screen screen--checking">
      <div className="screen__head">
        <p className="eyebrow">проверка заявки</p>
        <h1 className="screen__title">
          {phase === 'streaming' && 'Проверяем кадр'}
          {phase === 'done' && (listing ? 'Проверка завершена' : 'Материал не выставлен')}
          {phase === 'failed' && 'Проверка не удалась'}
        </h1>
        <p className="screen__lead">
          {phase === 'streaming'
            ? 'Каждый сигнал появляется, как только его посчитали. Здесь только то, что вернул сервер.'
            : phase === 'done'
              ? listing
                ? 'Проверка сошлась, лот создан. Ниже — итог и объяснение цены.'
                : 'Сервер не стал выставлять этот материал.'
              : 'Заявку можно повторить с другим файлом.'}
        </p>
      </div>

      {error && phase === 'failed' && (
        <div className="alert" role="alert">
          <div>
            <p className="alert__title">Ошибка проверки</p>
            <p className="alert__text">{error}</p>
          </div>
          <button type="button" className="btn btn--ghost btn--sm" onClick={onRestart}>
            Загрузить заново
          </button>
        </div>
      )}

      <div className="checking">
        <div className="checking__preview">
          {previewUrl ? (
            <img className="checking__image" src={previewUrl} alt="Загруженный кадр" />
          ) : (
            <div className="preview preview--empty">
              <span>превью недоступно</span>
            </div>
          )}
          {trust && (
            <div className="checking__trust">
              <TrustBadge score={trust.score} level={trust.level} />
            </div>
          )}
        </div>

        <div className="checking__body">
          <div className="progress">
            <div className="progress__row">
              <span className="progress__label" role="status" aria-live="polite">
                {phase === 'streaming' ? statusText : phase === 'done' ? 'Готово' : 'Остановлено'}
              </span>
              <span className="progress__count">{signals.length} сигн.</span>
            </div>
            <div
              className="progress__track"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress}
            >
              <span
                className={`progress__fill${phase === 'streaming' ? ' is-live' : ''}`}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {signals.length === 0 && phase === 'streaming' && (
            <p className="loading">
              <span className="spinner" aria-hidden="true" />
              Ждём первые сигналы
            </p>
          )}

          <div className="signals">
            {signals.map((item, index) => (
              <SignalCard key={item.id} signal={item} index={index} fresh={item.id === freshId} />
            ))}
          </div>
        </div>
      </div>

      {phase === 'done' && trust && finalCheck && (
        <EstimateBlock
          trust={trust}
          check={finalCheck}
          offer={offer}
          listing={listing}
          rejectReason={rejectReason}
          onListed={onListed}
        />
      )}
    </div>
  );
}

interface EstimateProps {
  trust: Trust;
  check: OfferCheck;
  offer: Offer;
  listing: Listing | null;
  rejectReason: string | null;
  onListed: (listingId: string) => void;
}

/** Блок «Оценка»: цена и why_price из лота, созданного backend. */
function EstimateBlock({ trust, check, offer, listing, rejectReason, onListed }: EstimateProps) {
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<Listing | null>(null);
  const shown = listing ?? created;

  const usable = check.signals.filter((signal) => signal.verdict !== 'unavailable').length;

  const handleList = async () => {
    setPublishing(true);
    setError(null);
    try {
      const result = await createListing(offer.id);
      setCreated(result);
    } catch (caught) {
      setError(describeError(caught));
    } finally {
      setPublishing(false);
    }
  };

  return (
    <section className="card estimate" aria-labelledby="estimate-title">
      <div className="estimate__head">
        <div>
          <p className="eyebrow">оценка</p>
          <h2 className="estimate__title" id="estimate-title">
            {shown ? 'Материал выставлен' : 'Материал не выставлен'}
          </h2>
        </div>
        <TrustBadge score={trust.score} level={trust.level} />
      </div>

      {shown ? (
        <>
          <div className="estimate__price">
            <span className="estimate__amount">{formatRub(shown.price_rub)}</span>
            <span className="estimate__caption">цена лота, рассчитана сервером</span>
          </div>

          <div className="why">
            <h3 className="why__title">Почему такая цена</h3>
            <ul className="why__list">
              {shown.why_price.map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
          </div>
        </>
      ) : (
        <p className="card__text">
          {rejectReason ??
            'Сервер не создал лот по этой заявке. Причина выше в статусе проверки или в её сигналах.'}
        </p>
      )}

      <dl className="estimate__facts">
        <div>
          <dt>Сигналов отработало</dt>
          <dd>
            {usable} из {check.signals.length}
          </dd>
        </div>
        <div>
          <dt>Покрытие проверки</dt>
          <dd>{Math.round(trust.coverage * 100)}%</dd>
        </div>
        <div>
          <dt>Неопределённость</dt>
          <dd>{Math.round(trust.uncertainty * 100)}%</dd>
        </div>
      </dl>

      {error && (
        <p className="field__error" role="alert">
          {error}
        </p>
      )}

      <div className="actions">
        {shown ? (
          <button type="button" className="btn btn--primary" onClick={() => onListed(shown.id)}>
            Открыть лот
          </button>
        ) : (
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => void handleList()}
            disabled={publishing}
          >
            {publishing ? 'Выставляем…' : 'Выставить лот'}
          </button>
        )}
      </div>
    </section>
  );
}