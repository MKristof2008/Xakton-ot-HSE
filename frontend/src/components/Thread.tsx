import { useEffect, useRef, useState } from 'react';
import type { ClaimStatus } from '../types';

interface ThreadProps {
  board: HTMLElement | null;
  from: HTMLElement | null;
  to: HTMLElement | null;
  status: ClaimStatus;
  anchorKey: string;
}

interface Geometry {
  d: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  width: number;
  height: number;
}

const MIN_BEND = 26;

/**
 * Нить от подчёркнутой фразы к карточке-улике.
 * Геометрия считается по фактическим координатам элементов на доске,
 * поэтому линия остаётся верной при смене ширины окна и на мобильном.
 */
export function Thread({ board, from, to, status, anchorKey }: ThreadProps) {
  const [geometry, setGeometry] = useState<Geometry | null>(null);
  const pathRef = useRef<SVGPathElement | null>(null);

  useEffect(() => {
    if (!board || !from || !to) {
      setGeometry(null);
      return;
    }

    const compute = () => {
      const box = board.getBoundingClientRect();
      const start = from.getBoundingClientRect();
      const end = to.getBoundingClientRect();
      if (box.width === 0 || end.height === 0) return;

      const isHorizontal = end.left - start.right > 24;
      let x1: number;
      let y1: number;
      let x2: number;
      let y2: number;
      let d: string;

      if (isHorizontal) {
        x1 = start.right - box.left + 2;
        y1 = start.top - box.top + start.height / 2;
        x2 = end.left - box.left - 2;
        y2 = end.top - box.top + Math.min(34, end.height / 2);
        const bend = Math.max(MIN_BEND, Math.abs(x2 - x1) * 0.45);
        d = `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
      } else {
        x1 = start.left - box.left + start.width / 2;
        y1 = start.bottom - box.top + 2;
        x2 = end.left - box.left + Math.min(48, end.width / 2);
        y2 = end.top - box.top - 2;
        const bend = Math.max(MIN_BEND, Math.abs(y2 - y1) * 0.5);
        d = `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`;
      }

      setGeometry({ d, x1, y1, x2, y2, width: box.width, height: box.height });
    };

    compute();
    const observer = new ResizeObserver(compute);
    observer.observe(board);
    window.addEventListener('resize', compute);
    window.addEventListener('scroll', compute, true);

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', compute);
      window.removeEventListener('scroll', compute, true);
    };
  }, [board, from, to, anchorKey]);

  useEffect(() => {
    const path = pathRef.current;
    if (!path || !geometry) return;

    const reduceMotion =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (reduceMotion || status === 'insufficient') {
      path.style.transition = 'none';
      path.style.strokeDasharray = status === 'insufficient' ? '7 7' : 'none';
      path.style.strokeDashoffset = '0';
      return;
    }

    const length = path.getTotalLength();
    path.style.transition = 'none';
    path.style.strokeDasharray = `${length}`;
    path.style.strokeDashoffset = `${length}`;
    void path.getBoundingClientRect();
    path.style.transition = 'stroke-dashoffset 480ms cubic-bezier(0.22, 0.7, 0.24, 1)';
    path.style.strokeDashoffset = '0';
  }, [geometry, status]);

  if (!geometry) return null;

  return (
    <svg
      className={`thread thread--${status}`}
      width={geometry.width}
      height={geometry.height}
      viewBox={`0 0 ${geometry.width} ${geometry.height}`}
      aria-hidden="true"
      focusable="false"
    >
      <path ref={pathRef} className="thread__path" d={geometry.d} />
      <circle className="thread__pin" cx={geometry.x1} cy={geometry.y1} r={3.2} />
      <circle className="thread__pin" cx={geometry.x2} cy={geometry.y2} r={3.2} />
    </svg>
  );
}
