import { useEffect, useRef, useState } from 'react';
import { confirmPayment, createPayment } from '../api/client';
import type { Payment } from '../types';

type Step = 'method' | 'processing' | 'done' | 'error';

interface Props {
  plan: 'pro' | 'team';
  planName: string;
  amountRub: number;
  days: number;
  onClose: () => void;
  onSuccess: () => void;
}

const METHODS = [
  {
    id: 'card' as const,
    title: 'Карта',
    hint: 'Мир, Visa, Mastercard',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
        <rect x="2.5" y="5" width="19" height="14" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
        <path d="M2.5 10h19" stroke="currentColor" strokeWidth="1.6" />
        <path d="M6 15h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: 'sbp' as const,
    title: 'СБП',
    hint: 'По QR-коду из банка',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
        <path d="M12 2.5 21 7v10l-9 4.5L3 17V7l9-4.5Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M8.5 12.5 11 15l4.5-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: 'invoice' as const,
    title: 'Счёт для редакции',
    hint: 'Оплата по реквизитам',
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" aria-hidden="true">
        <path d="M6 3.5h9l4 4v13H6z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M9 12h7M9 16h5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    ),
  },
];

export function PaymentDialog({ plan, planName, amountRub, days, onClose, onSuccess }: Props) {
  const [method, setMethod] = useState<'card' | 'sbp' | 'invoice'>('card');
  const [step, setStep] = useState<Step>('method');
  const [error, setError] = useState<string | null>(null);
  const [payment, setPayment] = useState<Payment | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  // Закрытие по Esc и возврат фокуса — базовая доступность модалки.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && step !== 'processing') onClose();
    };
    document.addEventListener('keydown', onKey);
    dialogRef.current?.focus();
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose, step]);

  async function pay() {
    setStep('processing');
    setError(null);
    try {
      const created = await createPayment(plan, method);
      setPayment(created);
      // Небольшая пауза: у реального эквайринга она есть, и пользователь
      // успевает увидеть, что происходит.
      await new Promise((resolve) => setTimeout(resolve, 1100));
      await confirmPayment(created.id);
      setStep('done');
      window.setTimeout(onSuccess, 900);
    } catch (err) {
      setStep('error');
      setError(
        err instanceof Error ? err.message : 'Платёж не прошёл. Попробуйте ещё раз.',
      );
    }
  }

  return (
    <div className="pay-overlay" role="presentation" onMouseDown={(e) => {
      if (e.target === e.currentTarget && step !== 'processing') onClose();
    }}>
      <div
        className="pay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pay-title"
        tabIndex={-1}
        ref={dialogRef}
      >
        <button
          className="pay__close"
          onClick={onClose}
          type="button"
          aria-label="Закрыть"
          disabled={step === 'processing'}
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>

        {step === 'method' && (
          <>
            <div className="pay__head">
              <span className="eyebrow">Оплата подписки</span>
              <h2 id="pay-title">{planName}</h2>
              <p className="pay__sum">
                {amountRub.toLocaleString('ru-RU')} ₽
                <span className="pay__per"> на {days} дней</span>
              </p>
            </div>

            <div className="pay__methods" role="radiogroup" aria-label="Способ оплаты">
              {METHODS.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  role="radio"
                  aria-checked={method === m.id}
                  className={`pay-method${method === m.id ? ' is-active' : ''}`}
                  onClick={() => setMethod(m.id)}
                >
                  <span className="pay-method__icon">{m.icon}</span>
                  <span className="pay-method__body">
                    <span className="pay-method__title">{m.title}</span>
                    <span className="pay-method__hint">{m.hint}</span>
                  </span>
                  <span className="pay-method__dot" aria-hidden="true" />
                </button>
              ))}
            </div>

            <button className="btn btn--primary pay__cta" onClick={pay} type="button">
              Оплатить {amountRub.toLocaleString('ru-RU')} ₽
            </button>

            <p className="pay__legal">
              Демонстрационный режим: деньги не списываются. В продукте здесь эквайринг.
              Нажимая «Оплатить», вы принимаете условия подписки.
            </p>
          </>
        )}

        {step === 'processing' && (
          <div className="pay__state">
            <div className="pay__spinner" aria-hidden="true" />
            <h2 id="pay-title">Проводим платёж</h2>
            <p>Обычно это занимает пару секунд. Не закрывайте окно.</p>
          </div>
        )}

        {step === 'done' && (
          <div className="pay__state pay__state--ok">
            <div className="pay__check" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="30" height="30" fill="none">
                <path d="m5 12.5 4.5 4.5L19 7.5" stroke="currentColor" strokeWidth="2.2"
                  strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h2 id="pay-title">Готово</h2>
            <p>
              Тариф «{planName}» активен на {days} дней.
              {payment && (
                <>
                  <br />
                  <span className="pay__id">Платёж {payment.id}</span>
                </>
              )}
            </p>
          </div>
        )}

        {step === 'error' && (
          <div className="pay__state pay__state--err">
            <div className="pay__check" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="28" height="28" fill="none">
                <path d="M12 7v7M12 17.2v.1" stroke="currentColor" strokeWidth="2.2"
                  strokeLinecap="round" />
              </svg>
            </div>
            <h2 id="pay-title">Платёж не прошёл</h2>
            <p>{error}</p>
            <button
              className="btn btn--primary"
              onClick={() => setStep('method')}
              type="button"
            >
              Попробовать снова
            </button>
          </div>
        )}
      </div>
    </div>
  );
}