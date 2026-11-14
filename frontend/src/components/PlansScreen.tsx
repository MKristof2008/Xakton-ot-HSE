import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { getMe, getPricing, upgrade } from '../api/client';
import type { Me, PlanInfo } from '../types';

interface Props {
  me: Me | null;
  onMe: (me: Me) => void;
}

const PLAN_ORDER: Record<string, number> = { free: 0, pro: 1, team: 2 };

export function PlansScreen({ me, onMe }: Props) {
  const [plans, setPlans] = useState<PlanInfo[] | null>(null);
  const [note, setNote] = useState('');
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getPricing()
      .then((p) => {
        if (!alive) return;
        setPlans(p.plans);
        setNote(p.note);
      })
      .catch(() => {
        if (alive) setError('Не удалось загрузить тарифы. Проверьте, что сервер запущен.');
      });
    return () => {
      alive = false;
    };
  }, []);

  async function pick(plan: PlanInfo) {
    if (plan.id === 'free') return;
    setPending(plan.id);
    setError(null);
    try {
      await upgrade(plan.id);
      onMe(await getMe());
    } catch {
      setError('Не удалось подключить тариф. Попробуйте ещё раз.');
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="view">
      <section className="hero">
        <span className="eyebrow">Тарифы</span>
        <h1 className="hero__title">
          Бесплатно — вердикт. <em>По подписке — разбор</em>
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

      <p className="plans-note">
        Демонстрация: оплата не подключена, тариф переключается сразу. В продукте здесь
        платёжный провайдер.
      </p>
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
