import { useState } from 'react';
import type { CSSProperties } from 'react';
import { upgrade } from '../api/client';
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
      </div>

      <div className="verdict__meta">
        <span>
          Неуверенность <strong>{uncertainty}%</strong>
        </span>
        {typeof result.quota_left === 'number' && (
          <span>
            Осталось сегодня{' '}
            <strong>
              {result.quota_left} {plural(result.quota_left, ['проверка', 'проверки', 'проверок'])}
            </strong>
          </span>
        )}
        {typeof result.duration_ms === 'number' && (
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
    </section>
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
