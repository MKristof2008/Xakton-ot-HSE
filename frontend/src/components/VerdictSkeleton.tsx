/**
 * Скелетон вердикта. Пульсирует, пока система считает, — чтобы ожидание
 * читалось как работа, а не как зависшая страница.
 */
export function VerdictSkeleton() {
  return (
    <div className="skeleton" role="status" aria-live="polite">
      <div className="skeleton__status">
        Сверяем с базой фактов и источниками
        <span className="dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
      </div>
      <span className="skel skel--eyebrow" />
      <div className="skel-row">
        <span className="skel skel--word" />
        <span className="skel skel--score" />
      </div>
      <span className="skel skel--sub" />
      <span className="skel skel--sub-short" />
      <span className="skel skel--meter" />
      <span className="visually-hidden">Идёт проверка</span>
    </div>
  );
}
