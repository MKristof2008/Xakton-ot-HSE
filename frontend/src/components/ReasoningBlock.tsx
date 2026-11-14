import type { Reasoning, TagInfo } from '../types';

/**
 * «Почему такой вердикт» — рубрика вместо голого числа.
 *
 * Раньше человек видел «50 / 100» и не понимал, откуда взялась цифра.
 * Здесь показано, из чего она сложилась: каждый критерий с баллами и
 * объяснением. Это же и есть ответ на вопрос жюри «а как модель думает».
 */
export function ReasoningBlock({
  reasoning,
  tag,
}: {
  reasoning: Reasoning;
  tag?: TagInfo;
}) {
  const criteria = reasoning.criteria ?? [];
  if (!criteria.length && !reasoning.summary) return null;

  return (
    <section className="reasoning" aria-labelledby="reasoning-title">
      <div className="reasoning__head">
        <h3 className="breakdown__title" id="reasoning-title">
          Почему такой вердикт
        </h3>
        <span className="reasoning__score">
          {reasoning.confidence}
          <span className="reasoning__of"> / 100</span>
        </span>
      </div>

      {(tag || reasoning.tag) && (
        <p className="reasoning__tag">
          <span className="reasoning__tag-label">Тема</span>
          {tag?.title || reasoning.tag?.title}
          {tag?.hits && tag.hits.length > 0 && (
            <span className="reasoning__tag-hits">
              {' '}
              · зацепки: {tag.hits.slice(0, 4).join(', ')}
            </span>
          )}
        </p>
      )}

      {reasoning.summary && <p className="reasoning__summary">{reasoning.summary}</p>}

      <ul className="reasoning__list">
        {criteria.map((c) => (
          <li key={c.key} className={`reasoning__item reasoning__item--${c.tone}`}>
            <div className="reasoning__item-top">
              <span className="reasoning__item-title">{c.title}</span>
              <span className="reasoning__points">
                {c.points} / {c.max_points}
              </span>
            </div>
            <p className="reasoning__reason">{c.reason}</p>
            <div className="reasoning__bar" aria-hidden="true">
              <span
                className="reasoning__bar-fill"
                style={{
                  width: `${c.max_points ? (c.points / c.max_points) * 100 : 0}%`,
                }}
              />
            </div>
          </li>
        ))}
      </ul>

      {reasoning.rules_applied && reasoning.rules_applied.length > 0 && (
        <p className="reasoning__rules">
          <span className="reasoning__tag-label">Правила темы</span>{' '}
          {reasoning.rules_applied.join('; ')}
        </p>
      )}
    </section>
  );
}
