import { useState } from 'react';
import type { CSSProperties } from 'react';
import { upgrade, sendFeedback } from '../api/client';
import type { CheckResponse, ClaimFinding, Signal } from '../types';
import { useCountUp } from '../hooks/useCountUp';
import {
  signalLabel,
  stepLabel,
  stepTone,
  toneForLevel,
  toneForSignal,
  uncertaintyPercent,
  verdictSubline,
} from '../lib/verdict';
import { formatDate } from '../lib/formatDate';
import { safeHttpUrl } from '../lib/safeUrl';
import { plural } from '../lib/plural';

interface Props {
  result: CheckResponse;
  onUpgraded: () => void;
}

export function VerdictCard({ result, onUpgraded }: Props) {
  const tone = toneForLevel(result.level);
  // Хук вызывается всегда — правила хуков не позволяют звать его под
  // условием, а на free-тарифе число скрыто.
  const score = useCountUp(result.score, 1000);
  const uncertainty = uncertaintyPercent(result.uncertainty);

  return (
    <section
      className={`verdict verdict--${tone}`}
      aria-label={`Вердикт: ${result.level_label}`}
    >
      <div className="verdict__grid">
        <div className="verdict__main">
          <span className="eyebrow">Вердикт</span>
          <h2 className="verdict__word">{result.level_label}</h2>
          <span className="verdict__rule" aria-hidden="true" />
          <p className="verdict__sub">{verdictSubline(result.verdict)}</p>
        </div>

        {/* Индекс доверия — только в подписке. По словам главреда, на
            бесплатном экране «5 из 10» читается как «это обман» и путает:
            человеку нужен ответ словами, а не число. */}
        {result.plan !== 'free' && (
          <div className="score">
            <span className="score__label">Уровень доверия</span>
            <span className="score__num">
              {score}
              <span className="score__of"> / 100</span>
            </span>
            <div className="meter" role="img" aria-label={`Уровень доверия ${result.score} из 100`}>
              <span className="meter__fill" style={{ width: `${result.score}%` }} />
            </div>
          </div>
        )}
      </div>

      <div className="verdict__meta">
        {result.plan !== 'free' && (
          <span>
            Неуверенность <strong>{uncertainty}%</strong>
          </span>
        )}
        {typeof result.quota_left === 'number' && (
          <span>
            Осталось сегодня{' '}
            <strong>
              {result.quota_left} {plural(result.quota_left, ['проверка', 'проверки', 'проверок'])}
            </strong>
          </span>
        )}
        {/* Время проверки — тоже деталь разбора: бесплатному пользователю
            миллисекунды ничего не говорят, а места занимают. */}
        {result.plan !== 'free' && typeof result.duration_ms === 'number' && (
          <span>
            Проверка заняла <strong>{Math.round(result.duration_ms)} мс</strong>
          </span>
        )}
      </div>

      {result.plan === 'free' ? (
        <Paywall onUpgraded={onUpgraded} />
      ) : (
        <Breakdown result={result} />
      )}

      {result.explanation && (
        <section className="explain">
          <span className="explain__label">
            {result.explanation_source === 'model' ? 'Объяснение модели' : 'Что показали детекторы'}
          </span>
          <p className="explain__text">{result.explanation}</p>
        </section>
      )}

      {result.passport && (
        <PassportLink
          path={result.passport}
          quoteHref={
            (result.claims ?? []).some((c) => c.quote)
              ? `${result.passport}/quote/${(result.claims ?? []).findIndex((c) => c.quote)}`
              : undefined
          }
        />
      )}

      <FeedbackRow checkId={result.id} />
    </section>
  );
}

// ---------------------------------------------------------------- обратная связь

/**
 * «Вердикт верный?» — это не голосование за результат, а корпус ошибок.
 *
 * На встрече эксперт спрашивал, как модель будет дообучаться. Здесь
 * собираются случаи, где человек знает лучше: текст, наш вердикт и
 * ожидаемый. Обучение идёт отдельным шагом, а не по одному клику.
 */
function FeedbackRow({ checkId }: { checkId: string }) {
  const [sent, setSent] = useState<'ok' | 'wrong' | null>(null);
  const [failed, setFailed] = useState(false);

  async function vote(ok: boolean) {
    setFailed(false);
    try {
      await sendFeedback({ check_id: checkId, verdict_ok: ok });
      setSent(ok ? 'ok' : 'wrong');
    } catch {
      setFailed(true);
    }
  }

  if (sent) {
    return (
      <div className="feedback feedback--done">
        <span className="feedback__thanks">
          {sent === 'ok'
            ? 'Спасибо — отметили как верный.'
            : 'Спасибо — попадёт в разбор ошибок.'}
        </span>
      </div>
    );
  }

  return (
    <div className="feedback">
      <span className="feedback__question">Вердикт верный?</span>
      <div className="feedback__actions">
        <button className="btn btn--ghost btn--small" type="button" onClick={() => void vote(true)}>
          Да, верно
        </button>
        <button className="btn btn--ghost btn--small" type="button" onClick={() => void vote(false)}>
          Нет, ошибка
        </button>
      </div>
      {failed && (
        <span className="feedback__error" role="alert">
          Не удалось отправить. Попробуйте ещё раз.
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- паспорт

function PassportLink({ path, quoteHref }: { path: string; quoteHref?: string }) {
  const [copied, setCopied] = useState(false);
  const url = `${window.location.origin}${path}`;

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // Приватный режим или нет разрешения — показываем ссылку текстом.
      setCopied(false);
    }
  }

  return (
    <div className="passport">
      <div className="passport__text">
        <span className="eyebrow">Паспорт утверждения</span>
        <p>
          Постоянная ссылка на эту проверку. Отправьте её в чат — человек откроет
          вердикт и цитату из первоисточника без регистрации.
        </p>
        <code className="passport__url">{url}</code>
      </div>
      <div className="passport__actions">
        <button className="btn btn--ghost" onClick={copy} type="button">
          {copied ? 'Скопировано' : 'Скопировать ссылку'}
        </button>
        <a className="btn btn--ghost" href={path} target="_blank" rel="noreferrer">
          Открыть
        </a>
        {quoteHref && (
          <a className="btn btn--ghost" href={quoteHref} target="_blank" rel="noreferrer">
            Где в источнике
          </a>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ пейволл

function Paywall({ onUpgraded }: { onUpgraded: () => void }) {
  const [upgrading, setUpgrading] = useState(false);
  const [failed, setFailed] = useState(false);

  async function handleUpgrade() {
    setUpgrading(true);
    setFailed(false);
    try {
      await upgrade('pro');
      onUpgraded();
    } catch {
      setFailed(true);
      setUpgrading(false);
    }
  }

  return (
    <div className="paywall">
      <div className="paywall__head">
        <h3>Разбор — по подписке</h3>
        <span className="tag tag--ghost">300 ₽ / мес</span>
      </div>
      {/* upgrade_hint с бэкенда дословно повторяет пункты ниже — оставляем список. */}
      <ul className="paywall__list">
        <li>почему такой вердикт</li>
        <li>по каждому сигналу</li>
        <li>ссылки на первоисточники</li>
        <li>что проверить дальше</li>
      </ul>
      <div className="paywall__actions">
        <button
          className="btn btn--primary"
          type="button"
          onClick={() => void handleUpgrade()}
          disabled={upgrading}
        >
          {upgrading ? (
            'Включаем…'
          ) : (
            <>
              Открыть разбор
              <span className="btn__arrow" aria-hidden="true">
                →
              </span>
            </>
          )}
        </button>
        <span className="paywall__note">Первый месяц бесплатно · в демо оплата не подключена</span>
      </div>
      {failed && (
        <p className="alert alert--bad" role="alert">
          Не удалось включить подписку. Попробуйте ещё раз.
        </p>
      )}
    </div>
  );
}

// ------------------------------------------------------------------- разбор

function Breakdown({ result }: { result: CheckResponse }) {
  const signals = result.signals ?? [];
  const claims = result.claims ?? [];
  const nextSteps = result.next_steps ?? [];
  const limits = result.limits ?? [];
  const provenance = result.provenance ?? [];

  return (
    <div className="breakdown">
      {claims.length > 0 && (
        <section className="breakdown__section">
          <h3 className="breakdown__title">
            Что проверяли{' '}
            <span>
              {claims.length} {plural(claims.length, ['утверждение', 'утверждения', 'утверждений'])}
            </span>
          </h3>
          <ol className="signals">
            {claims.map((claim, i) => (
              <ClaimRow key={i} claim={claim} index={i} />
            ))}
          </ol>
        </section>
      )}

      {signals.length > 0 && (
        <section className="breakdown__section">
          <h3 className="breakdown__title">
            Из чего сложился вердикт{' '}
            <span>
              {signals.length} {plural(signals.length, ['сигнал', 'сигнала', 'сигналов'])}
            </span>
          </h3>
          <ol className="signals">
            {signals.map((signal, i) => (
              <SignalRow key={signal.id} signal={signal} index={i} />
            ))}
          </ol>
        </section>
      )}

      {nextSteps.length > 0 && (
        <section className="breakdown__section">
          <h3 className="breakdown__title">Что проверить дальше</h3>
          <ol className="steps">
            {nextSteps.map((step, i) => (
              <li className="step" key={i} style={{ '--i': i } as CSSProperties}>
                <span className="step__num">{String(i + 1).padStart(2, '0')}</span>
                <div className="step__body">
                  <span className="step__title">{step.title}</span>
                  <span className="step__why">{step.why}</span>
                </div>
                <span className={`tag tag--${stepTone(step.kind)}`}>{stepLabel(step.kind)}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {provenance.length > 0 && (
        <section className="breakdown__section">
          <h3 className="breakdown__title">Откуда взялась новость</h3>
          <ul className="limits">
            {provenance.map((entry, i) => (
              <li key={i}>
                {formatDate(entry.date) ?? 'дата неизвестна'} · {entry.where}
                {entry.note ? ` — ${entry.note}` : ''}
              </li>
            ))}
          </ul>
        </section>
      )}

      {limits.length > 0 && (
        <section className="breakdown__section">
          <h3 className="breakdown__title">Границы проверки</h3>
          <ul className="limits">
            {limits.map((limit, i) => (
              <li key={i}>{limit}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ сигнал

/** Одно проверенное утверждение: статус, объяснение, цитата и ссылка. */
function ClaimRow({ claim, index }: { claim: ClaimFinding; index: number }) {
  const tone = toneForClaim(claim.status);
  const url = safeHttpUrl(claim.source_url);

  return (
    <li className={`signal signal--${tone}`} style={{ '--i': index } as CSSProperties}>
      <div className="signal__top">
        <span className="signal__name">{claim.text}</span>
        <span className={`tag tag--${tone}`}>{claimLabel(claim.status)}</span>
      </div>

      {claim.explanation && <p className="signal__text">{claim.explanation}</p>}

      {claim.quote && <p className="signal__fact">«{claim.quote}»</p>}

      {url && (
        <a className="signal__src" href={url} target="_blank" rel="noreferrer noopener">
          {claim.source_title || 'первоисточник'}
          <span aria-hidden="true">↗</span>
        </a>
      )}

      {claim.action && (
        <p className="signal__action">
          <span className="signal__action-label">Что делать</span>
          {claim.action}
        </p>
      )}

      {claim.resend && (
        <div className="signal__resend">
          <span className="signal__action-label">Готово к пересылке</span>
          <p className="signal__resend-text">{claim.resend}</p>
          <button
            type="button"
            className="btn btn--ghost btn--small"
            onClick={() => {
              void navigator.clipboard?.writeText(claim.resend ?? '');
            }}
          >
            Скопировать
          </button>
        </div>
      )}

      {claim.limitations.length > 0 && (
        <ul className="limits">
          {claim.limitations.map((lim, i) => (
            <li key={i}>{lim}</li>
          ))}
        </ul>
      )}
    </li>
  );
}

function toneForClaim(status: ClaimFinding['status']): 'ok' | 'bad' | 'fog' {
  if (status === 'supported') return 'ok';
  if (status === 'contradicted') return 'bad';
  return 'fog';
}

function claimLabel(status: ClaimFinding['status']): string {
  switch (status) {
    case 'supported':
      return 'подтверждено';
    case 'contradicted':
      return 'опровергнуто';
    case 'context':
      return 'контекст';
    default:
      return 'не проверено';
  }
}

function SignalRow({ signal, index }: { signal: Signal; index: number }) {
  const tone = toneForSignal(signal.verdict);
  const strength = Math.max(0, Math.min(1, signal.strength));

  const source = typeof signal.details.source === 'string' ? signal.details.source : null;
  const url = safeHttpUrl(typeof signal.details.url === 'string' ? signal.details.url : null);
  const matched = signal.details.matched_fact;
  const fact =
    matched && typeof matched === 'object' && 'claim' in matched &&
    typeof (matched as { claim?: unknown }).claim === 'string'
      ? (matched as { claim: string }).claim
      : null;

  return (
    <li className={`signal signal--${tone}`} style={{ '--i': index } as CSSProperties}>
      <div className="signal__top">
        <span className="signal__name">{signal.name}</span>
        <span className={`tag tag--${tone}`}>{signalLabel(signal.verdict)}</span>
      </div>

      <p className="signal__text">{signal.summary}</p>

      {fact && <p className="signal__fact">«{fact}»</p>}

      {signal.verdict !== 'unavailable' && strength > 0 && (
        <span className="signal__strength">
          <span className="signal__bar" aria-hidden="true">
            <span style={{ width: `${Math.round(strength * 100)}%` }} />
          </span>
          вес сигнала {Math.round(strength * 100)}%
        </span>
      )}

      {url && (
        <a className="signal__src" href={url} target="_blank" rel="noreferrer noopener">
          {source ?? 'первоисточник'}
          <span aria-hidden="true">↗</span>
        </a>
      )}
    </li>
  );
}
