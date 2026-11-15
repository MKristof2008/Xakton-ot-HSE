import type { SVGProps } from 'react';

/**
 * Знак «Ревизор»: галочка и красный крест — вердикт на одном знаке.
 *
 * Раньше здесь была одна галочка: она годилась в кнопку «готово», но
 * ничего не говорила о продукте. Теперь знак показывает обе стороны
 * проверки — «подтверждено» и «опровергнуто», и совпадает с тем, что
 * человек видит в карточке вердикта: зелёная галочка против красного
 * креста.
 *
 * Крест всегда красный (--signal), поэтому цвет зашит, а не берётся из
 * currentColor: знак должен читаться одинаково на синей плашке, на
 * тёмной теме и в монохромной печати.
 */
export function BrandMark(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="19"
      height="19"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <path
        d="M2.5 12.6l3.4 3.6 6.2-6.9"
        stroke="currentColor"
        strokeWidth="2.4"
      />
      <path d="M13.6 7.2l7 7M20.6 7.2l-7 7" stroke="var(--signal)" strokeWidth="2.1" />
    </svg>
  );
}

/**
 * Полный логотип для страниц вне React: favicon, превью в мессенджере,
 * OG-картинка. Тот же рисунок, но самостоятельным SVG-файлом.
 */
export const BRAND_MARK_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 12.6l3.4 3.6 6.2-6.9" stroke="#ffffff" stroke-width="2.4"/><path d="M13.6 7.2l7 7M20.6 7.2l-7 7" stroke="#ff6b5c" stroke-width="2.1"/></svg>`;
