import type { SVGProps } from 'react';

/** Знак «Ревизор»: галочка в рамке — как отметка редактора на полях. */
export function BrandMark(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <path d="M5 12.5 9.5 17 19 7" />
    </svg>
  );
}

