import { useCallback, useEffect, useRef, useState } from 'react';
import type { Deal, Offer } from './types';
import type { Screen } from './components/SiteHeader';
import { SiteHeader } from './components/SiteHeader';
import { FeedScreen } from './components/FeedScreen';
import { UploadScreen } from './components/UploadScreen';
import { CheckingScreen } from './components/CheckingScreen';
import { ListingScreen } from './components/ListingScreen';
import { describeError, fetchListings } from './api';
import { isDemoMode } from './config';

interface UploadState {
  offer: Offer;
  previewUrl: string | null;
}

interface Toast {
  id: number;
  text: string;
  kind: 'error' | 'success';
}

export default function App() {
  const [screen, setScreen] = useState<Screen>('feed');
  const [listingId, setListingId] = useState<string | null>(null);
  const [upload, setUpload] = useState<UploadState | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const toastId = useRef(0);

  const notify = useCallback((text: string, kind: Toast['kind']) => {
    toastId.current += 1;
    setToast({ id: toastId.current, text, kind });
  }, []);

  const showError = useCallback((text: string) => notify(text, 'error'), [notify]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  const goFeed = useCallback(() => {
    setScreen('feed');
    setListingId(null);
  }, []);

  const goUpload = useCallback(() => {
    setScreen('upload');
    setListingId(null);
  }, []);

  const openListing = useCallback((id: string) => {
    setListingId(id);
    setScreen('listing');
  }, []);

  /** Покупка из ленты: открываем карточку, где сделка проводится и видна. */
  const buyFromFeed = useCallback(
    (id: string) => {
      openListing(id);
    },
    [openListing],
  );

  const handleUploadSubmitted = useCallback((offer: Offer, previewUrl: string | null) => {
    setUpload({ offer, previewUrl });
    setScreen('checking');
  }, []);

  /**
   * После выставления лота ищем его на сервере по offer_id.
   * Если ещё не появился — уводим в ленту и показываем пояснение.
   */
  const handleListed = useCallback(
    async () => {
      const offerId = upload?.offer.id;
      if (!offerId) {
        goFeed();
        return;
      }
      try {
        const listings = await fetchListings();
        const found = listings.find((item) => item.offer_id === offerId);
        if (found) {
          setUpload(null);
          openListing(found.id);
          notify('Лот выставлен', 'success');
          return;
        }
        notify('Лот отправлен, но в ленте ещё не появился. Обновите ленту чуть позже.', 'success');
      } catch (error) {
        notify(describeError(error), 'error');
      }
      setUpload(null);
      goFeed();
    },
    [upload, goFeed, openListing, notify],
  );

  const handleRestart = useCallback(() => {
    setUpload(null);
    goUpload();
  }, [goUpload]);

  const handleDeal = useCallback(
    (deal: Deal) => {
      notify(`Сделка ${deal.id}: автору выплачено`, 'success');
    },
    [notify],
  );

  return (
    <div className="app">
      <SiteHeader screen={screen} onNavigate={(next) => (next === 'upload' ? goUpload() : goFeed())} />

      <main className="app__main">
        {screen === 'feed' && (
          <FeedScreen
            onOpenListing={openListing}
            onBuy={buyFromFeed}
            onUpload={goUpload}
            onError={showError}
          />
        )}

        {screen === 'upload' && <UploadScreen onSubmitted={handleUploadSubmitted} />}

        {screen === 'checking' && upload && (
          <CheckingScreen
            offer={upload.offer}
            previewUrl={upload.previewUrl}
            onListed={() => void handleListed()}
            onRestart={handleRestart}
          />
        )}

        {screen === 'listing' && listingId && (
          <ListingScreen listingId={listingId} onBack={goFeed} onBuyDone={handleDeal} />
        )}
      </main>

      {toast && (
        <div className={`toast toast--${toast.kind}`} role="status" key={toast.id}>
          {toast.text}
          <button type="button" className="toast__close" onClick={() => setToast(null)} aria-label="Закрыть">
            ×
          </button>
        </div>
      )}

      <footer className="site-footer">
        <p>
          «Свидетель» — маркетплейс достоверных свидетельств с места события. Проверка подлинности —
          инфраструктура: без неё лот не выставляется.
        </p>
        {isDemoMode && <p className="site-footer__demo">Демо-режим · данные заготовлены заранее</p>}
      </footer>
    </div>
  );
}