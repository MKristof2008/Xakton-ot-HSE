import { useCallback, useEffect, useState } from 'react';
import { getMe, hasSession } from './api/client';
import type { Me } from './types';
import { hashFor, readTab } from './lib/tabs';
import type { Tab } from './lib/tabs';
import { Header } from './components/Header';
import { AuthScreen } from './components/AuthScreen';
import { Footer } from './components/Footer';
import { CheckScreen } from './components/CheckScreen';
import { TopScreen } from './components/TopScreen';
import { PlansScreen } from './components/PlansScreen';
import './styles/global.css';

export default function App() {
  const [tab, setTab] = useState<Tab>(readTab);
  const [me, setMe] = useState<Me | null>(null);
  // Три состояния входа: проверяем сессию → гость → пользователь.
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    const onHash = () => setTab(readTab());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    if (!hasSession()) {
      setAuthChecked(true);
      return;
    }
    getMe()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setAuthChecked(true));
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

  // Пока проверяем сессию — тишина вместо мигания формы входа.
  if (!authChecked) {
    return <div className="app app--boot" aria-busy="true" />;
  }

  // Без аккаунта проверки недоступны: лимиты и подписка живут в профиле.
  if (!me) {
    return (
      <div className="app">
        <AuthScreen onAuth={(user) => setMe(user)} />
      </div>
    );
  }

  return (
    <div className="app">
      <a className="skip" href="#content">
        К содержимому
      </a>
      <Header tab={tab} me={me} onNavigate={go} onLogout={() => setMe(null)} />

      <main className="main" id="content">
        {tab === 'check' && <CheckScreen me={me} onMe={setMe} />}
        {tab === 'top' && <TopScreen />}
        {tab === 'plans' && <PlansScreen me={me} onMe={setMe} />}
      </main>

      <Footer />
    </div>
  );
}
