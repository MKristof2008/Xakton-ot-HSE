import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { getMe, getPricing } from '../api/client';
import { PaymentDialog } from './PaymentDialog';
import type { Me, PlanInfo, PricingResponse } from '../types';

interface Props {
  me: Me | null;
  onMe: (me: Me) => void;
  /** Попросить войти перед оплатой. */
  onNeedAuth?: (reason: string) => void;
}

const PLAN_ORDER: Record<string, number> = { free: 0, pro: 1, team: 2 };

export function PlansScreen({ me, onMe, onNeedAuth }: Props) {
  const [plans, setPlans] = useState<PlanInfo[] | null>(null);
  const [note, setNote] = useState('');
  const [trial, setTrial] = useState<PricingResponse['trial'] | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [paying, setPaying] = useState<PlanInfo | null>(null);

  useEffect(() => {
    // ?pay=pro — сразу открыть диалог оплаты (для демо и скриншотов).
    const want = new URLSearchParams(window.location.search).get('pay');
    if (want === 'pro' || want === 'team') {
      setPaying({ id: want, name: want === 'pro' ? 'Разбор' : 'Редакция',
        price_rub: want === 'pro' ? 300 : 5000, limits: '', features: [] });
      if (new URLSearchParams(window.location.search).get('autopay') === '1') {
        window.setTimeout(() => {
          const btn = document.querySelector<HTMLButtonElement>('.pay__cta');
          btn?.click();
        }, 500);
      }
    }
    let alive = true;
    getPricing()
      .then((p) => {
        if (!alive) return;
        setPlans(p.plans);
        setNote(p.note);
        setTrial(p.trial ?? null);
      })
      .catch(() => {
        if (alive) setError('Не удалось загрузить тарифы. Проверьте, что сервер запущен.');
      });
    return () => {
      alive = false;
    };
  }, []);

  function pick(plan: PlanInfo) {
    if (plan.id === 'free') return;
    if (!me && onNeedAuth) {
      onNeedAuth('Чтобы оформить подписку, войдите или создайте аккаунт.');
      return;
    }
    setError(null);
    setPaying(plan);
  }

  async function finishPayment() {
    setPaying(null);
    setPending(null);
    try {
      onMe(await getMe());
    } catch {
      /* тариф уже применён на сервере — интерфейс обновится при перезагрузке */
    }
  }

  return (
    <div className="view">
      <section className="hero">
        <span className="eyebrow">Тарифы</span>
        <h1 className="hero__title">
          Один вердикт — <em>три глубины разбора</em>
        </h1>
        <p className="hero__lead">{note}</p>
      </section>

      {plans === null && !error && <PlansSkeleton />}

      {error && (
        <p className="alert alert--bad" role="alert">
          <span aria-hidden="true">!</span>
          {error}
        </p>
      )}

      {plans && plans.length > 0 && (
        <div className="plans">
          {[...plans]
            .sort((a, b) => (PLAN_ORDER[a.id] ?? 9) - (PLAN_ORDER[b.id] ?? 9))
            .map((plan, i) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                index={i}
                active={me?.plan === plan.id}
                pending={pending === plan.id}
                disabled={pending !== null}
                onPick={() => void pick(plan)}
              />
            ))}
        </div>
      )}

      {trial && (
        <div className="trial-banner">
          <span className="trial-banner__badge">{trial.days} дней бесплатно</span>
          <span className="trial-banner__text">{trial.note}</span>
        </div>
      )}

      <p className="plans-note">
        Демонстрация: платёж проходит без списания денег. В продукте здесь эквайринг.
      </p>

      {paying && (
        <PaymentDialog
          plan={paying.id === 'team' ? 'team' : 'pro'}
          planName={paying.name}
          amountRub={paying.price_rub}
          days={30}
          onClose={() => setPaying(null)}
          onSuccess={() => void finishPayment()}
        />
      )}
    </div>
  );
}

interface CardProps {
  plan: PlanInfo;
  index: number;
  active: boolean;
  pending: boolean;
  disabled: boolean;
  onPick: () => void;
}

function PlanCard({ plan, index, active, pending, disabled, onPick }: CardProps) {
  const isFree = plan.id === 'free';
  const price = plan.price_rub === 0 ? '0 ₽' : `${plan.price_rub.toLocaleString('ru-RU')} ₽`;

  return (
    <article
      className={`plan${plan.recommended ? ' plan--rec' : ''}`}
      style={{ '--i': index } as CSSProperties}
      aria-labelledby={`plan-${plan.id}`}
    >
      <div className="plan__head">
        <h3 id={`plan-${plan.id}`}>{plan.name}</h3>
        {plan.recommended && <span className="plan__flag">рекомендуем</span>}
        {active && <span className="plan__current">ваш тариф</span>}
      </div>

      <p className="plan__price">
        {price}
        {!isFree && <span className="plan__per"> / мес</span>}
      </p>
      <p className="plan__limit">{plan.limits}</p>

      <ul className="plan__features">
        {plan.features.map((feature, i) => (
          <li key={i}>{feature}</li>
        ))}
      </ul>

      <button
        type="button"
        className={`btn ${plan.recommended ? 'btn--primary' : 'btn--ghost'}`}
        disabled={active || disabled || isFree}
        onClick={onPick}
        aria-label={
          isFree
            ? 'Бесплатный тариф доступен всем'
            : active
              ? 'Это ваш текущий тариф'
              : `Подключить тариф «${plan.name}»`
        }
      >
        {pending ? 'Подключаем…' : active ? 'Подключён' : isFree ? 'Доступен всем' : 'Подключить'}
        {!pending && !active && !isFree && (
          <span className="btn__arrow" aria-hidden="true">
            →
          </span>
        )}
      </button>
    </article>
  );
}

function PlansSkeleton() {
  return (
    <div className="plans" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div className="plan" key={i}>
          <span className="skel" style={{ width: 120, height: 22 }} />
          <span className="skel" style={{ width: 100, height: 40 }} />
          <span className="skel" style={{ width: '70%', height: 12 }} />
          {[0, 1, 2, 3].map((j) => (
            <span key={j} className="skel" style={{ width: `${88 - j * 12}%`, height: 12 }} />
          ))}
          <span className="skel" style={{ width: '100%', height: 44, marginTop: 8 }} />
        </div>
      ))}
    </div>
  );
}
