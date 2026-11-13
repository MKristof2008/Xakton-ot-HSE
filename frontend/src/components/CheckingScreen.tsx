import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Offer, OfferCheck, SignalResult, Trust } from '../types';
import { createListing, describeError, fetchCheck, streamCheck } from '../api';
import { formatRub } from '../lib/format';
import { estimatePrice } from '../lib/pricing';
import { SignalCard } from './SignalCard';
import { TrustBadge } from './TrustBadge';

interface CheckingScreenProps {
  offer: Offer;
  previewUrl: string | null;
  /** Готовый результат — можно выставлять лот. */
  onListed: (check: OfferCheck) => void;
  onRestart: () => void;
}

type Phase = 'streaming' | 'done' | 'failed';

/**
 * Экран проверки: сигналы приходят по SSE и появляются по мере готовности.
 * Если поток оборвался — окончательный результат догружается через
 * GET /api/offers/{id}/check.
 */
export function CheckingScreen({ offer, previewUrl, onListed, onRestart }: CheckingScreenProps) {
  const offerId = offer.id;
  const [signals, setSignals] = useState<SignalResult[]>([]);
  const [trust, setTrust] = useState<Trust | null>(null);
  const [finalCheck, setFinalCheck] = useState<OfferCheck | null>(null);
  const [phase, setPhase] = useState<Phase>('streaming');
  const [statusText, setStatusText] = useState('Ставим заявку в очередь');
  const [error, setError] = useState<string | null>(null);
  const [freshId, setFreshId] = useState<string | null>(null);
  const attemptRef = useRef(0);

  const run = useCallback(
    (signal: AbortSignal) => {
      const attempt = ++attemptRef.current;
      void (async () => {
        try {
          const finalCheck = await streamCheck(
            offerId,
            {
              onStatus: (_status, message) => {
                if (message) setStatusText(message);
              },
              onSignal: (item) => {
                if (attempt !== attemptRef.current) return;
                setSignals((prev) => (prev.some((s) => s.id === item.id) ? prev : [...prev, item]));
                setFreshId(item.id);
              },
              onTrust: (value) => setTrust(value),
              onDone: (check) => {
                if (attempt !== attemptRef.current) return;
                applyFinal(check);
              },
              onError: (message) => {
                if (attempt !== attemptRef.current) return;
                setError(message);
              },
            },
            signal,
          );
          if (attempt !== attemptRef.current || signal.aborted) return;
          if (finalCheck) applyFinal(finalCheck);
          else await recover();
        } catch (caught) {
          if (signal.aborted || attempt !== attemptRef.current) return;
          await recover(caught);
        }

        async function recover(cause?: unknown) {
          // поток мог закрыться раньше итога — пробуем обычный запрос
          try {
            const check = await fetchCheck(offerId);
            if (attempt !== attemptRef.current || signal.aborted) return;
            applyFinal(check);
          } catch (fallbackError) {
            if (attempt !== attemptRef.current || signal.aborted) return;
            setPhase('failed');
            setError(describeError(cause ?? fallbackError));
          }
        }

        function applyFinal(check: OfferCheck) {
          setSignals(check.signals);
          setTrust(check.trust);
          setFinalCheck(check);
          setPhase(check.status === 'failed' ? 'failed' : 'done');
          if (check.status === 'failed') setError('Проверка не удалась на стороне сервера.');
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
          {phase === 'done' && 'Проверка завершена'}
          {phase === 'failed' && 'Проверка не удалась'}
        </h1>
        <p className="screen__lead">
          {phase === 'streaming'
            ? 'Каждый сигнал появляется, как только его посчитали. Ничего не выдумываем — только то, что вернул сервер.'
            : phase === 'done'
              ? 'Ниже — итог проверки и цена, которую получит лот.'
              : 'Материал не выставлен. Можно загрузить другой файл.'}
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
          <div className="progress" aria-hidden={phase !== 'streaming'}>
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
              <span className={`progress__fill${phase === 'streaming' ? ' is-live' : ''}`} style={{ width: `${progress}%` }} />
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
        <EstimateBlock trust={trust} check={finalCheck} offer={offer} onListed={onListed} />
      )}
    </div>
  );
}

interface EstimateProps {
  trust: Trust;
  check: OfferCheck;
  offer: Offer;
  onListed: (check: OfferCheck) => void;
}

/** Блок «Оценка»: предварительная цена по контрактному правилу + выставление лота. */
function EstimateBlock({ trust, check, offer, onListed }: EstimateProps) {
  const [listing, setListing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const estimate = useMemo(() => estimatePrice(offer, check), [offer, check]);

  const handleList = async () => {
    setListing(true);
    setError(null);
    try {
      await createListing(offer.id);
      onListed(check);
    } catch (caught) {
      setError(describeError(caught));
    } finally {
      setListing(false);
    }
  };

  const usable = check.signals.filter((signal) => signal.verdict !== 'unavailable').length;

  return (
    <section className="card estimate" aria-labelledby="estimate-title">
      <div className="estimate__head">
        <div>
          <p className="eyebrow">оценка</p>
          <h2 className="estimate__title" id="estimate-title">
            {estimate.blocked ? 'Материал не выставлен' : 'Материал можно выставить'}
          </h2>
        </div>
        <TrustBadge score={trust.score} level={trust.level} />
      </div>

      <div className="estimate__price">
        <span className="estimate__amount">{formatRub(estimate.priceRub)}</span>
        <span className="estimate__caption">предварительная цена по правилу контракта</span>
      </div>

      <div className="why">
        <h3 className="why__title">Почему такая цена</h3>
        <ul className="why__list">
          {estimate.whyPrice.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      </div>

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
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => void handleList()}
          disabled={listing || estimate.blocked}
        >
          {listing ? 'Выставляем…' : 'Выставить лот'}
        </button>
      </div>
    </section>
  );
}