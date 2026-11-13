import { useEffect, useMemo, useState } from 'react';
import type { Deal, Listing, OfferCheck, SignalResult } from '../types';
import { buy as buyApi, describeError, fetchCheck, fetchListing } from '../api';
import { commissionRate } from '../config';
import { formatAgo, formatRub } from '../lib/format';
import { LEVEL_LABELS, TRUST_LEVEL_HINT } from '../lib/labels';
import { estimatePrice } from '../lib/pricing';
import { Preview } from './ListingCard';
import { SignalCard } from './SignalCard';
import { StateBadge } from './StateBadge';
import { TrustBadge } from './TrustBadge';

interface ListingScreenProps {
  listingId: string;
  onBack: () => void;
  onBuyDone: (deal: Deal) => void;
}

/**
 * Карточка лота: превью, факты, сигналы проверки, объяснение цены, покупка.
 * signals приходят из GET /api/offers/{id}/check. Если проверки нет —
 * честно показываем, что сигналы недоступны, а не рисуем заглушки.
 */
export function ListingScreen({ listingId, onBack, onBuyDone }: ListingScreenProps) {
  const [listing, setListing] = useState<Listing | null>(null);
  const [check, setCheck] = useState<OfferCheck | null>(null);
  const [checkMissing, setCheckMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [buying, setBuying] = useState(false);
  const [buyError, setBuyError] = useState<string | null>(null);
  const [deal, setDeal] = useState<Deal | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setCheckMissing(false);
    setDeal(null);

    void (async () => {
      try {
        const found = await fetchListing(listingId);
        if (controller.signal.aborted) return;
        setListing(found);

        try {
          const offerCheck = await fetchCheck(found.offer_id);
          if (controller.signal.aborted) return;
          setCheck(offerCheck);
        } catch (checkError) {
          // лот может существовать без доступной проверки — это не роняет экран
          if (controller.signal.aborted) return;
          setCheck(null);
          setCheckMissing(true);
          void checkError;
        }
      } catch (caught) {
        if (controller.signal.aborted) return;
        setError(describeError(caught));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();

    return () => controller.abort();
  }, [listingId, reloadKey]);

  const estimate = useMemo(() => {
    if (!check || !listing) return null;
    const offer = {
      id: listing.offer_id,
      status: 'listed' as const,
      created_at: listing.created_at,
      author: { id: '', display_name: 'Аноним', payout: 0 },
      file: { name: '', size: 0, mime: '', sha256: '', preview_url: listing.preview_url },
      caption: listing.title,
      location: listing.facts.geo,
      shot_at: listing.facts.shot_at,
    };
    return estimatePrice(offer, check);
  }, [check, listing]);

  const handleBuy = async () => {
    if (!listing) return;
    setBuying(true);
    setBuyError(null);
    try {
      const result = await buyApi(listing.id);
      setDeal(result);
      setListing({ ...listing, state: 'sold' });
      onBuyDone(result);
    } catch (caught) {
      setBuyError(describeError(caught));
    } finally {
      setBuying(false);
    }
  };

  if (loading) {
    return (
      <div className="screen">
        <p className="loading">
          <span className="spinner" aria-hidden="true" />
          Загружаем лот…
        </p>
      </div>
    );
  }

  if (error || !listing) {
    return (
      <div className="screen">
        <button type="button" className="link-button" onClick={onBack}>
          ← Назад в ленту
        </button>
        <div className="alert" role="alert">
          <div>
            <p className="alert__title">Лот не открылся</p>
            <p className="alert__text">{error ?? 'Лот не найден.'}</p>
          </div>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => setReloadKey((k) => k + 1)}>
            Повторить
          </button>
        </div>
      </div>
    );
  }

  const sold = listing.state === 'sold';
  const signals = check?.signals ?? [];

  return (
    <div className="screen screen--listing">
      <button type="button" className="link-button" onClick={onBack}>
        ← Назад в ленту
      </button>

      <div className="listing-grid">
        <div className="listing-media">
          <Preview url={listing.preview_url} title={listing.title} />
          <div className="listing-media__badges">
            <TrustBadge score={listing.trust.score} level={listing.trust.level} />
            <StateBadge state={listing.state} />
          </div>
        </div>

        <div className="listing-main">
          <h1 className="listing__title">{listing.title}</h1>
          <p className="listing__subtitle">
            {formatAgo(listing.created_at) ? `снято ${formatAgo(listing.created_at)}` : 'время съёмки неизвестно'}
            {listing.facts.geo ? ` · ${listing.facts.geo}` : ''}
          </p>

          <div className="price-row">
            <span className="price-row__amount">{formatRub(listing.price_rub)}</span>
            <span className="price-row__hint">{TRUST_LEVEL_HINT[listing.trust.level]}</span>
          </div>

          {deal ? (
            <DealBlock deal={deal} />
          ) : buyError ? (
            <div className="alert" role="alert">
              <div>
                <p className="alert__title">Покупка не прошла</p>
                <p className="alert__text">{buyError}</p>
              </div>
            </div>
          ) : sold ? (
            <p className="notice">Этот лот уже продан.</p>
          ) : (
            <div className="actions">
              <button type="button" className="btn btn--primary" onClick={() => void handleBuy()} disabled={buying}>
                {buying ? 'Проводим сделку…' : `Купить за ${formatRub(listing.price_rub)}`}
              </button>
              <span className="actions__hint">
                Комиссия платформы {Math.round(commissionRate * 100)}% от суммы
              </span>
            </div>
          )}
        </div>
      </div>

      <section className="card facts" aria-labelledby="facts-title">
        <h2 className="section-title" id="facts-title">
          Факты
        </h2>
        <dl className="facts__grid">
          <Fact label="Происхождение" value={listing.facts.origin || 'неизвестно'} />
          <Fact
            label="Когда снято"
            value={
              listing.facts.shot_at
                ? new Date(listing.facts.shot_at).toLocaleString('ru-RU', {
                    day: 'numeric',
                    month: 'long',
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                : 'не указано'
            }
          />
          <Fact label="Гео" value={listing.facts.geo || 'не указано'} />
          <Fact
            label="Уникальность"
            value={
              listing.facts.unique
                ? 'уникальный кадр'
                : `похожих в архиве: ${listing.facts.similar_in_archive}`
            }
          />
          <Fact
            label="Совпадений в архиве"
            value={String(listing.facts.similar_in_archive)}
          />
          <Fact label="Доверие" value={`${listing.trust.score} · ${LEVEL_LABELS[listing.trust.level]}`} />
        </dl>
      </section>

      <section className="card" aria-labelledby="why-title">
        <h2 className="section-title" id="why-title">
          Почему такая цена
        </h2>
        {listing.why_price.length > 0 ? (
          <ul className="why__list why__list--from-listing">
            {listing.why_price.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        ) : estimate ? (
          <ul className="why__list why__list--from-listing">
            {estimate.whyPrice.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        ) : (
          <p className="card__text">Сервер не прислал объяснение цены.</p>
        )}
      </section>

      <section className="card" aria-labelledby="signals-title">
        <h2 className="section-title" id="signals-title">
          Проверка
        </h2>
        {signals.length > 0 ? (
          <div className="signals">
            {signals.map((signal: SignalResult, index) => (
              <SignalCard key={signal.id} signal={signal} index={index} />
            ))}
          </div>
        ) : (
          <p className="card__text">
            {checkMissing
              ? 'Результат проверки для этого лота недоступен на сервере.'
              : 'Сервер не прислал сигналы проверки.'}
          </p>
        )}
      </section>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="facts__item">
      <dt className="facts__label">{label}</dt>
      <dd className="facts__value">{value}</dd>
    </div>
  );
}

function DealBlock({ deal }: { deal: Deal }) {
  return (
    <div className="deal" role="status">
      <p className="deal__title">Сделка проведена</p>
      <dl className="deal__grid">
        <div>
          <dt>Сумма</dt>
          <dd>{formatRub(deal.amount_rub)}</dd>
        </div>
        <div>
          <dt>Комиссия {Math.round(commissionRate * 100)}%</dt>
          <dd>{formatRub(deal.commission_rub)}</dd>
        </div>
        <div>
          <dt>Выплата автору</dt>
          <dd>{formatRub(deal.author_payout_rub)}</dd>
        </div>
      </dl>
      <p className="deal__meta">
        Покупатель: {deal.buyer.name} · сделка {deal.id}
      </p>
    </div>
  );
}