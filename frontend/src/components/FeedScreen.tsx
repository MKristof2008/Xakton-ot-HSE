import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { getFeed } from '../api/client';
import type { FeedResponse } from '../types';
import { toneForLevel } from '../lib/verdict';
import { plural } from '../lib/plural';
import { formatDate } from '../lib/formatDate';

/**
 * Лента проверенного: что уже разобрали и с каким итогом.
 *
 * Отличие от топов: топ — рейтинг сомнений (что проверяют чаще всего),
 * лента — витрина результата. Из неё вырастает медиа, которое публикует
 * только проверенное: сюда попадает то, у чего есть вердикт и паспорт.
 */
export function FeedScreen() {
  const [data, setData] = useState<FeedResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'verified' | 'refuted'>('all');

  useEffect(() => {
    let alive = true;
    getFeed(168)
      .then((res) => {
        if (alive) setData(res);
      })
      .catch(() => {
        if (alive) setError('Не удалось загрузить ленту. Проверьте, что сервер запущен.');
      });
    return () => {
      alive = false;
    };
  }, []);

  const items = (data?.items ?? []).filter((item) => {
    if (filter === 'verified') return item.level === 'confirmed' || item.level === 'likely_real';
    if (filter === 'refuted') return item.level === 'likely_fake';
    return true;
  });

  return (
    <div className="view">
      <section className="hero">
        <span className="eyebrow">Проверенные новости</span>
        <h1 className="hero__title">
          Лента <em>проверенного</em>
        </h1>
        <p className="hero__lead">
          Что уже разобрали и с каким итогом. У каждой строки есть постоянная
          ссылка — её можно переслать в чат как доказательство.
        </p>
      </section>

      {data && (
        <div className="feed-summary">
          <button
            type="button"
            className={`feed-filter${filter === 'all' ? ' is-active' : ''}`}
            onClick={() => setFilter('all')}
          >
            Всё <strong>{data.items.length}</strong>
          </button>
          <button
            type="button"
            className={`feed-filter${filter === 'verified' ? ' is-active' : ''}`}
            onClick={() => setFilter('verified')}
          >
            Подтверждено <strong>{data.verified}</strong>
          </button>
          <button
            type="button"
            className={`feed-filter${filter === 'refuted' ? ' is-active' : ''}`}
            onClick={() => setFilter('refuted')}
          >
            Опровергнуто <strong>{data.refuted}</strong>
          </button>
          <span className="feed-summary__note">
            за {Math.round(data.window_hours / 24)}{' '}
            {plural(Math.round(data.window_hours / 24), ['день', 'дня', 'дней'])}
          </span>
        </div>
      )}

      {error && (
        <p className="alert alert--bad" role="alert">
          <span aria-hidden="true">!</span>
          {error}
        </p>
      )}

      {!data && !error && <FeedSkeleton />}

      {data && items.length === 0 && (
        <div className="empty">
          <span className="empty__mark" aria-hidden="true">
            §
          </span>
          <h3>Пока пусто</h3>
          <p>Проверьте что-нибудь — и результат появится здесь первым.</p>
        </div>
      )}

      {items.length > 0 && (
        <ol className="feed-list">
          {items.map((item, i) => (
            <li
              key={item.text_hash}
              className="feed-item"
              style={{ '--i': i } as CSSProperties}
            >
              <div className="feed-item__head">
                <span className={`tag tag--${toneForLevel(item.level)}`}>
                  {item.level_label}
                </span>
                <span className="feed-item__date">
                  {formatDate(item.last_at) ?? 'дата неизвестна'}
                </span>
              </div>
              <p className="feed-item__text">{item.sample_text}</p>
              <div className="feed-item__foot">
                <span>
                  {item.checks_count}{' '}
                  {plural(item.checks_count, ['проверка', 'проверки', 'проверок'])}
                </span>
                <a className="feed-item__link" href={item.passport} target="_blank" rel="noreferrer">
                  Паспорт
                  <span aria-hidden="true">↗</span>
                </a>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function FeedSkeleton() {
  return (
    <div className="feed-list" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div className="feed-item feed-item--skeleton" key={i}>
          <span className="sk sk--line" />
          <span className="sk sk--line sk--short" />
        </div>
      ))}
    </div>
  );
}
