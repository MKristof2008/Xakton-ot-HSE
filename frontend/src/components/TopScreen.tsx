import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { getStats, getTop } from '../api/client';
import type { Stats, TopItem } from '../types';
import { useCountUp } from '../hooks/useCountUp';
import { toneForLevel } from '../lib/verdict';
import { plural } from '../lib/plural';

export function TopScreen() {
  const [items, setItems] = useState<TopItem[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([getTop(168), getStats()])
      .then(([top, st]) => {
        if (!alive) return;
        setItems(top.items);
        setStats(st);
      })
      .catch(() => {
        if (alive) setError('Не удалось загрузить топы. Проверьте, что сервер запущен.');
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="view">
      <section className="hero">
        <span className="eyebrow">Что проверяют сейчас</span>
        <h1 className="hero__title">
          Топы <em>проверок</em>
        </h1>
        <p className="hero__lead">
          Одинаковые сообщения схлопываются в одну строку. Чем больше людей проверило — тем
          выше новость. Так из рейтинга вырастает медиа проверенных новостей.
        </p>
      </section>

      {stats ? <StatsRow stats={stats} /> : !error ? <StatsSkeleton /> : null}

      {error && (
        <p className="alert alert--bad" role="alert">
          <span aria-hidden="true">!</span>
          {error}
        </p>
      )}

      {items === null && !error && <TopSkeleton />}

      {items && items.length === 0 && (
        <div className="empty">
          <span className="empty__mark" aria-hidden="true">
            §
          </span>
          <h3>Пока пусто</h3>
          <p>Проверьте что-нибудь — и это появится здесь первым.</p>
        </div>
      )}

      {items && items.length > 0 && (
        <section aria-labelledby="top-list-title">
          <h2 className="visually-hidden" id="top-list-title">
            Рейтинг проверок за неделю
          </h2>
          <ol className="top-list">
            {items.map((item, i) => (
              <li
                key={item.text_hash}
                className="top-item"
                style={{ '--i': i } as CSSProperties}
              >
                <span className="top-item__rank" aria-hidden="true">
                  {String(i + 1).padStart(2, '0')}
                </span>
                <p className="top-item__text">{item.sample_text}</p>
                <div className="top-item__meta">
                  <span className={`tag tag--${toneForLevel(item.level)}`}>
                    {item.level_label}
                  </span>
                  <span>
                    {item.checks_count}{' '}
                    {plural(item.checks_count, ['проверка', 'проверки', 'проверок'])}
                  </span>
                  <LivePulse lastHour={item.last_hour ?? 0} lastMinute={item.last_minute ?? 0} />
                  {item.verdict_variants > 1 && <span>мнения расходятся</span>}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

/**
 * «Живость» новости: сколько людей проверяют её прямо сейчас.
 * Показываем только когда есть что показывать — нули не выводим,
 * иначе на пустой базе каждый пункт выглядит мёртвым.
 */
function LivePulse({ lastHour, lastMinute }: { lastHour: number; lastMinute: number }) {
  if (!lastHour && !lastMinute) return null;

  if (lastMinute >= 2) {
    return (
      <span className="pulse" title={`${lastMinute} проверок за последнюю минуту`}>
        <span className="pulse__dot" aria-hidden="true" />
        проверяют сейчас
      </span>
    );
  }

  return (
    <span className="pulse pulse--quiet">
      за час: {lastHour} {plural(lastHour, ['проверка', 'проверки', 'проверок'])}
    </span>
  );
}

function StatsRow({ stats }: { stats: Stats }) {
  const cells = [
    { value: stats.checks, label: 'проверок', tone: '' },
    { value: stats.unique_claims, label: 'уникальных', tone: '' },
    { value: stats.fake, label: 'фейков', tone: 'bad' },
    { value: stats.real, label: 'подтверждено', tone: 'ok' },
  ];

  return (
    <dl className="stats">
      {cells.map((cell, i) => (
        <div
          key={cell.label}
          className={`stat${cell.tone ? ` stat--${cell.tone}` : ''}`}
          style={{ '--i': i } as CSSProperties}
        >
          <dt className="stat__l">{cell.label}</dt>
          <dd className="stat__n">
            <CountUp target={cell.value} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function CountUp({ target }: { target: number }) {
  const value = useCountUp(target, 900);
  return <>{value}</>;
}

function StatsSkeleton() {
  return (
    <div className="stats" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <div className="stat" key={i}>
          <span className="skel" style={{ width: 64, height: 32 }} />
          <span className="skel" style={{ width: 84, height: 10, marginTop: 8 }} />
        </div>
      ))}
    </div>
  );
}

function TopSkeleton() {
  return (
    <div aria-hidden="true">
      <ol className="top-list">
        {[0, 1, 2, 3, 4].map((i) => (
          <li className="top-item" key={i}>
            <span className="top-item__rank">
              <span className="skel" style={{ width: 24, height: 22 }} />
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <span className="skel" style={{ width: `${78 - i * 9}%`, height: 16 }} />
              <span className="skel" style={{ width: 160, height: 11 }} />
            </div>
          </li>
        ))}
      </ol>
      <span className="visually-hidden">Загружаем топы</span>
    </div>
  );
}
