import { apiMode } from '../config';
import type { Deal, Listing, Offer, OfferCheck, Stats } from '../types';
import {
  createOffer as liveCreateOffer,
  getListing as liveGetListing,
  getListings as liveGetListings,
  getStats as liveGetStats,
  buyListing as liveBuyListing,
  createListingForOffer as liveCreateListing,
  getOfferCheck,
  streamOfferEvents,
} from './client';
import type { OfferForm, ProgressHandler } from './client';
import { ApiError } from './errors';
import {
  DEMO_CHECK,
  DEMO_DEAL,
  DEMO_LISTINGS,
  DEMO_OFFER,
  DEMO_STATS,
} from '../fixtures/demo';

/**
 * Единственная точка переключения demo/live.
 * Компоненты не знают, откуда пришли данные. Фикстуры в live-режиме
 * не используются никогда — при недоступности сервера ошибка уходит наверх.
 */

const DEMO_DELAY_MS = 600;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export async function fetchListings(signal?: AbortSignal): Promise<Listing[]> {
  if (apiMode === 'live') return liveGetListings(signal);
  await delay(DEMO_DELAY_MS);
  return clone(DEMO_LISTINGS);
}

export async function fetchListing(id: string, signal?: AbortSignal): Promise<Listing> {
  if (apiMode === 'live') return liveGetListing(id, signal);
  await delay(300);
  const found = DEMO_LISTINGS.find((item) => item.id === id);
  if (!found) throw new ApiError('NOT_FOUND');
  return clone(found);
}

export async function fetchStats(signal?: AbortSignal): Promise<Stats> {
  if (apiMode === 'live') return liveGetStats(signal);
  await delay(DEMO_DELAY_MS);
  return clone(DEMO_STATS);
}

export async function buy(id: string, signal?: AbortSignal): Promise<Deal> {
  if (apiMode === 'live') return liveBuyListing(id, signal);
  await delay(DEMO_DELAY_MS);
  const listing = DEMO_LISTINGS.find((item) => item.id === id);
  if (!listing) throw new ApiError('NOT_FOUND');
  if (listing.state === 'sold') throw new ApiError('ALREADY_SOLD');
  const commission = Math.round(listing.price_rub * 0.2);
  return {
    ...clone(DEMO_DEAL),
    listing_id: id,
    amount_rub: listing.price_rub,
    commission_rub: commission,
    author_payout_rub: listing.price_rub - commission,
  };
}

export async function submitOffer(form: OfferForm, signal?: AbortSignal): Promise<Offer> {
  if (apiMode === 'live') return liveCreateOffer(form, signal);
  await delay(500);
  return {
    ...clone(DEMO_OFFER),
    caption: form.caption,
    location: form.location,
    shot_at: form.shotAt || null,
    file: {
      ...DEMO_OFFER.file,
      name: form.file.name,
      size: form.file.size,
      mime: form.file.type,
      preview_url: null,
    },
  };
}

export async function fetchCheck(offerId: string, signal?: AbortSignal): Promise<OfferCheck> {
  if (apiMode === 'live') return getOfferCheck(offerId, signal);
  await delay(300);
  return { ...clone(DEMO_CHECK), offer_id: offerId };
}

/** Выставить лот по проверенной заявке. */
export async function createListing(offerId: string, signal?: AbortSignal): Promise<Listing> {
  if (apiMode === 'live') return liveCreateListing(offerId, signal);
  await delay(DEMO_DELAY_MS);
  return { ...clone(DEMO_LISTINGS[0]), offer_id: offerId };
}

/** Прогресс проверки. В live — SSE GET /api/offers/{id}/events, в demo — эмуляция. */
export async function streamCheck(
  offerId: string,
  handlers: ProgressHandler,
  signal: AbortSignal,
): Promise<OfferCheck | null> {
  if (apiMode === 'live') {
    const holder: { check: OfferCheck | null } = { check: null };
    await streamOfferEvents(
      offerId,
      {
        ...handlers,
        onDone: (check) => {
          holder.check = check;
          handlers.onDone?.(check);
        },
      },
      signal,
    );
    return holder.check;
  }

  for (const item of DEMO_CHECK.signals) {
    if (signal.aborted) throw new ApiError('ABORTED');
    await delay(700);
    if (signal.aborted) throw new ApiError('ABORTED');
    handlers.onSignal(clone(item));
  }
  await delay(400);
  const finalCheck: OfferCheck = { ...clone(DEMO_CHECK), offer_id: offerId };
  handlers.onTrust?.(finalCheck.trust);
  handlers.onDone?.(finalCheck);
  return finalCheck;
}

export { ApiError, describeError, messageForCode } from './errors';
export type { ProgressHandler } from './client';