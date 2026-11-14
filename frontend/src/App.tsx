import { useCallback, useEffect, useState } from 'react';
import { getMe } from './api/client';
import type { Me } from './types';
import { hashFor, readTab } from './lib/tabs';
import type { Tab } from './lib/tabs';
import { Header } from './components/Header';
import { Footer } from './components/Footer';
import { CheckScreen } from './components/CheckScreen';
import { TopScreen } from './components/TopScreen';
import { PlansScreen } from './components/PlansScreen';
import './styles/global.css';

export default function App() {
  const [tab, setTab] = useState<Tab>(readTab);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    const onHash = () => setTab(readTab());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  const go = useCallback((next: Tab) => {
    const hash = hashFor(next);
    if (window.location.hash.replace('#', '') !== hash.replace('#', '')) {
      if (hash) {
        window.location.hash = hash;
      } else {
        // убираем #, не оставляя «висящий» решётчатый адрес
        history.replaceState(null, '', window.location.pathname + window.location.search);
      }
    }
    setTab(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  return (
    <div className="app">
      <a className="skip" href="#content">
        К содержимому
      </a>
      <Header tab={tab} me={me} onNavigate={go} />

      <main className="main" id="content">
        {tab === 'check' && <CheckScreen me={me} onMe={setMe} />}
        {tab === 'top' && <TopScreen />}
        {tab === 'plans' && <PlansScreen me={me} onMe={setMe} />}
      </main>

      <Footer />
    </div>
  );
}
