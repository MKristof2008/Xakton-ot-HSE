import type { Listing } from '../types';
import { formatAgo, formatRub } from '../lib/format';
import { TrustBadge } from './TrustBadge';

interface ListingCardProps {
  listing: Listing;
  onOpen: (id: string) => void;
  onBuy: (id: string) => void;
}

/** Карточка лота в ленте. */
export function ListingCard({ listing, onOpen, onBuy }: ListingCardProps) {
  const ago = formatAgo(listing.created_at);
  const sold = listing.state === 'sold';

  return (
    <article className={`lot${sold ? ' lot--sold' : ''}`}>
      <button
        type="button"
        className="lot__preview"
        onClick={() => onOpen(listing.id)}
        aria-label={`Открыть лот: ${listing.title}`}
      >
        <Preview url={listing.preview_url} title={listing.title} />
        <TrustBadge score={listing.trust.score} level={listing.trust.level} compact />
        {sold && <span className="lot__sold-flag">продан</span>}
      </button>

      <div className="lot__body">
        <button type="button" className="lot__title" onClick={() => onOpen(listing.id)}>
          {listing.title}
        </button>

        <p className="lot__meta">
          {ago ? `снято ${ago}` : 'время съёмки неизвестно'}
          {listing.facts.geo ? ` · ${listing.facts.geo}` : ''}
        </p>

        <div className="lot__foot">
          <span className="lot__price">{formatRub(listing.price_rub)}</span>
          {sold ? (
            <span className="lot__sold-note">продан</span>
          ) : (
            <button type="button" className="btn btn--primary btn--sm" onClick={() => onBuy(listing.id)}>
              Купить
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

export function Preview({ url, title }: { url: string | null; title: string }) {
  if (!url) {
    return (
      <div className="preview preview--empty" aria-hidden="true">
        <span>нет превью</span>
      </div>
    );
  }
  return <img className="preview" src={url} alt={`Превью: ${title}`} loading="lazy" />;
}