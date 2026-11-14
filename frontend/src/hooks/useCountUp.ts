import { useEffect, useState } from 'react';
import { useReducedMotion } from './useReducedMotion';

/**
 * Счётчик от 0 до target: именно он превращает цифру в «система вынесла
 * решение», а не «страница перерисовалась». При prefers-reduced-motion
 * значение появляется сразу.
 */
export function useCountUp(target: number, duration = 900): number {
  const reduced = useReducedMotion();
  const [value, setValue] = useState(reduced ? target : 0);

  useEffect(() => {
    if (reduced) {
      setValue(target);
      return;
    }

    let frame = 0;
    const start = performance.now();
    setValue(0);

    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(target * eased));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);

    // Страховка: в headless-браузере и в фоновой вкладке requestAnimationFrame
    // не тикает, и счётчик навсегда остаётся на нуле. Через duration + 150 мс
    // ставим конечное значение, если анимация так и не дошла.
    const settle = window.setTimeout(() => setValue(target), duration + 150);

    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settle);
    };
  }, [target, duration, reduced]);

  return value;
}
