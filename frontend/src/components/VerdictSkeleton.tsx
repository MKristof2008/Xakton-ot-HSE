import { useEffect, useState } from 'react';

/** Этапы проверки по порядку. Показываем их смену, чтобы ожидание читалось как работа. */
const STEPS = [
  'Сверяем с базой фактов',
  'Ищем первоисточники',
  'Проверяем цитаты',
];

/**
 * Скелетон вердикта. Пульсирует, пока система считает, — чтобы ожидание
 * читалось как работа, а не как зависшая страница.
 *
 * Главред прямо сказал: «пока долго думает, его просто надо оптимизировать».
 * Ускорили бэкенд (провайдеры теперь параллельные), а здесь добавили смену
 * этапов — длинное ожидание перестаёт выглядеть как зависание.
 */
export function VerdictSkeleton() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => {
      setStep((s) => Math.min(s + 1, STEPS.length - 1));
    }, 900);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="skeleton" role="status" aria-live="polite">
      <ol className="skeleton__steps" aria-hidden="true">
        {STEPS.map((label, i) => (
          <li
            key={label}
            className={`skeleton__step${i < step ? ' is-done' : ''}${i === step ? ' is-active' : ''}`}
          >
            <span className="skeleton__dot" />
            {label}
          </li>
        ))}
      </ol>
      <span className="skel skel--eyebrow" />
      <div className="skel-row">
        <span className="skel skel--word" />
        <span className="skel skel--score" />
      </div>
      <span className="skel skel--sub" />
      <span className="skel skel--sub-short" />
      <span className="skel skel--meter" />
      <span className="visually-hidden">Идёт проверка: {STEPS[step]}</span>
    </div>
  );
}
