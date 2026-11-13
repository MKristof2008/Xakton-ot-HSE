import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Listing, Stats } from '../types';
import { describeError, fetchListings, fetchStats } from '../api';
import { isDemoMode } from '../config';
import { formatRub } from '../lib/format';
import { ListingCard } from './ListingCard';

type Filter = 'all' | 'available' | 'sold';
type Sort = 'new' | 'price_asc' | 'price_desc';

interface FeedScreenProps {
  onOpenListing: (id: string) => void;
  onBuy: (id: string) => void;
  onUpload: () => void;
  /** Показать ошибку другим экранам (покупка и т.п.). */
  onError: (message: string) => void;
}

/**
 * Главный экран: лента лотов маркетплейса.
 * При недоступном backend показываем баннер и пустой список —
 * фикстуры под видом живых данных не подставляются.
 */
export function FeedScreen({ onOpenListing, onBuy, onUpload, onError }: FeedScreenProps) {
  const [listings, setListings] = useState<Listing[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>('all');
  const [sort, setSort] = useState<Sort>('new');

  const load = useCallback(
    async (signal: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const [feed, summary] = await Promise.all([fetchListings(), fetchStats()]);
        if (signal.aborted) return;
        setListings(feed);
        setStats(summary);
      } catch (caught) {
        if (signal.aborted) return;
        setListings(null);
        setStats(null);
        const message = describeError(caught);
        setError(message);
        onError(message);
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    [onError],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const visible = useMemo(() => {
    if (!listings) return [];
    const filtered = listings.filter((item) => {
      if (filter === 'all') return true;
      if (filter === 'sold') return item.state === 'sold';
      return item.state !== 'sold';
    });
    return [...filtered].sort((a, b) => {
      if (sort === 'price_asc') return a.price_rub - b.price_rub;
      if (sort === 'price_desc') return b.price_rub - a.price_rub;
      return Date.parse(b.created_at) - Date.parse(a.created_at);
    });
  }, [listings, filter, sort]);

  return (
    <div className="screen screen--feed">
      <section className="hero">
        <p className="eyebrow">маркетплейс свидетельств</p>
        <h1 className="hero__title">Свидетель</h1>
        <p className="hero__subtitle">
          Покупайте достоверные кадры с места события. Каждый материал проверен, цена объяснена,
          автор получает выплату.
        </p>
        <div className="hero__actions">
          <button type="button" className="btn btn--primary" onClick={onUpload}>
            Загрузить своё
          </button>
        </div>
      </section>

      {error && (
        <div className="alert" role="alert">
          <div>
            <p className="alert__title">Сервер недоступен</p>
            <p className="alert__text">
              {error} Лента не загружена — здесь нет вымышленных данных вместо настоящих.
            </p>
          </div>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => void load(new AbortController().signal)}>
            Повторить
          </button>
        </div>
      )}

      <StatsBar stats={stats} loading={loading && !error} />

      <div className="feed__toolbar">
        <div className="segmented" role="group" aria-label="Фильтр лотов">
          {(
            [
              ['all', 'Все'],
              ['available', 'Доступные'],
              ['sold', 'Проданные'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`segmented__item${filter === key ? ' is-active' : ''}`}
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
            >
              {label}
            </button>
          ))}
        </div>

        <label className="select">
          <span className="select__label">Сортировка</span>
          <select
            className="select__input"
            value={sort}
            onChange={(event) => setSort(event.target.value as Sort)}
          >
            <option value="new">Сначала новые</option>
            <option value="price_asc">Цена по возрастанию</option>
            <option value="price_desc">Цена по убыванию</option>
          </select>
        </label>
      </div>

      {isDemoMode && (
        <p className="notice notice--demo">
          Демо-режим: показываем заранее заготовленные лоты. Живых данных здесь нет.
        </p>
      )}

      {loading && !error && <p className="loading"><span className="spinner" aria-hidden="true" />Загружаем лоты…</p>}

      {!loading && !error && visible.length === 0 && (
        <div className="empty">
          <p className="empty__title">Пока нет лотов</p>
          <p className="empty__text">
            {listings && listings.length > 0
              ? 'Под выбранный фильтр ничего не подходит. Смените фильтр или сортировку.'
              : 'Никто ещё не выставил материал. Загрузите свой кадр — система проверит его и предложит цену.'}
          </p>
          <button type="button" className="btn btn--primary" onClick={onUpload}>
            Загрузить своё
          </button>
        </div>
      )}

      {visible.length > 0 && (
        <div className="lots">
          {visible.map((listing) => (
            <ListingCard key={listing.id} listing={listing} onOpen={onOpenListing} onBuy={onBuy} />
          ))}
        </div>
      )}
    </div>
  );
}

function StatsBar({ stats, loading }: { stats: Stats | null; loading: boolean }) {
  const items = [
    { label: 'лотов', value: stats ? String(stats.listings) : '—' },
    { label: 'продано', value: stats ? String(stats.sold) : '—' },
    { label: 'оборот', value: stats ? formatRub(stats.turnover_rub) : '—' },
    { label: 'комиссия', value: stats ? formatRub(stats.commission_rub) : '—' },
  ];

  return (
    <dl className={`stats${loading ? ' stats--loading' : ''}`} aria-busy={loading}>
      {items.map((item) => (
        <div className="stats__item" key={item.label}>
          <dt className="stats__label">{item.label}</dt>
          <dd className="stats__value">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}