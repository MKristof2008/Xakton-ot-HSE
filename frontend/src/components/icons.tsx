import type { SVGProps } from 'react';

/**
 * Знак «Ревизора»: лакмусовая полоска, опущенная в кислоту.
 *
 * Отсылка к первой итерации продукта — он тогда назывался «Лакмус», и
 * полоска была его главным образом: бумажка пропитывается снизу вверх,
 * цвет меняется от жёлтого к красному. Оставили рисунок, но подписали
 * продуктом, который продаём сейчас.
 *
 * Почему полоска, а не галочка с крестом: знак должен читаться в 16px во
 * вкладке браузера. Две тонкие линии (галочка и крест) на этом размере
 * сливаются в пятно, а сплошная полоска с градиентом — нет.
 *
 * Цвета зашиты, а не берутся из currentColor: реакция бумажки на кислоту
 * не зависит от темы, и знак должен выглядеть одинаково на синей плашке,
 * на тёмном фоне и в печати.
 */

/** Общая геометрия полоски: узкий вертикальный прямоугольник. */
const STRIP = { x: 6.5, y: 2, w: 11, h: 20, r: 1.6 };
/** Уровень кислоты: ниже этой линии бумажка пропитана. */
const SOAK_Y = 9.4;

export function BrandMark(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="19"
      height="19"
      fill="none"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <defs>
        <linearGradient id="rv-litmus" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffd94a" />
          <stop offset=".5" stopColor="#f5822a" />
          <stop offset="1" stopColor="#c81e2b" />
        </linearGradient>
        <clipPath id="rv-strip">
          <rect x={STRIP.x} y={STRIP.y} width={STRIP.w} height={STRIP.h} rx={STRIP.r} />
        </clipPath>
      </defs>

      {/* сухая часть бумажки */}
      <rect
        x={STRIP.x} y={STRIP.y} width={STRIP.w} height={STRIP.h} rx={STRIP.r}
        fill="#f5f1e6"
      />
      {/* пропитанная кислотой часть: волнистый край — мениск */}
      <g clipPath="url(#rv-strip)">
        <path
          d={`M${STRIP.x} ${SOAK_Y}q2.75-1.6 5.5 0t5.5 0V${STRIP.y + STRIP.h}h-11Z`}
          fill="url(#rv-litmus)"
        />
      </g>
      {/* контур */}
      <rect
        x={STRIP.x} y={STRIP.y} width={STRIP.w} height={STRIP.h} rx={STRIP.r}
        stroke="#0a1a33" strokeOpacity=".4" strokeWidth=".7"
      />
      {/* блик на мениске: отделяет мокрое от сухого */}
      <path
        d={`M${STRIP.x} ${SOAK_Y}q2.75-1.6 5.5 0t5.5 0`}
        stroke="#fff" strokeOpacity=".85" strokeWidth=".9"
      />
    </svg>
  );
}

/**
 * Полный логотип для страниц вне React: favicon, превью в мессенджере,
 * OG-картинка. Тот же рисунок на синей плашке.
 */
export const BRAND_MARK_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffd94a"/><stop offset=".5" stop-color="#f5822a"/><stop offset="1" stop-color="#c81e2b"/></linearGradient><clipPath id="c"><rect x="10.5" y="5" width="11" height="22" rx="1.6"/></clipPath></defs><rect width="32" height="32" rx="7" fill="#12409b"/><rect x="10.5" y="5" width="11" height="22" rx="1.6" fill="#f5f1e6"/><g clip-path="url(#c)"><path d="M10.5 13.6q2.75-1.7 5.5 0t5.5 0V27h-11Z" fill="url(#g)"/></g><rect x="10.5" y="5" width="11" height="22" rx="1.6" fill="none" stroke="#0a1a33" stroke-opacity=".4" stroke-width=".8"/><path d="M10.5 13.6q2.75-1.7 5.5 0t5.5 0" fill="none" stroke="#fff" stroke-opacity=".85" stroke-width=".9"/></svg>`;
