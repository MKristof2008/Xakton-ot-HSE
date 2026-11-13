import { useCallback, useEffect, useState } from 'react';
import { ApiError, getMe, getPricing, getStats, getTop, runCheck, upgrade } from './api/client';
import type { CheckResponse, Me, PlanInfo, Stats, TopItem } from './types';
import './styles/global.css';

type Tab = 'check' | 'top' | 'plans';

const EXAMPLES = [
  'СРОЧНО! ЦБ запретил наличные с 1 марта 2026 года! Перешли всем!',
  'С 1 января 2026 года штраф за покупку алкоголя составит 5000 рублей.',
  'ЦБ поднял ключевую ставку до 21% годовых 25 октября 2024 года.',
  'Вчера в Казани открыли новый мост через реку.',
];

const LEVEL_COLOR: Record<string, string> = {
  confirmed: 'ok',
  likely_real: 'ok',
  fog: 'fog',
  doubtful: 'warn',
  likely_fake: 'bad',
};

function levelClass(level: string): string {
  return LEVEL_COLOR[level] ?? 'fog';
}

function readTab(): Tab {
  const hash = window.location.hash.replace('#', '');
  return hash === 'top' || hash === 'plans' ? hash : 'check';
}

export default function App() {
  const [tab, setTab] = useState<Tab>(readTab);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    const onHash = () => setTab(readTab());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    getMe().then(setMe).catch(() => setMe(null));
  }, []);

  const go = useCallback((next: Tab) => {
    window.location.hash = next === 'check' ? '' : next;
    setTab(next);
  }, []);

  return (
    <div className="app">
      <header className="top">
        <div className="top__inner">
          <button className="brand" onClick={() => go('check')} type="button">
            <span className="brand__mark" aria-hidden="true" />
            <span className="brand__name">Проверено</span>
          </button>
          <nav className="tabs" aria-label="Разделы">
            <button
              type="button"
              className={`tab${tab === 'check' ? ' is-active' : ''}`}
              onClick={() => go('check')}
            >
              Проверить
            </button>
            <button
              type="button"
              className={`tab${tab === 'top' ? ' is-active' : ''}`}
              onClick={() => go('top')}
            >
              Топы
            </button>
            <button
              type="button"
              className={`tab${tab === 'plans' ? ' is-active' : ''}`}
              onClick={() => go('plans')}
            >
              Тарифы
            </button>
          </nav>
          <span className={`plan-chip plan-chip--${me?.plan ?? 'free'}`}>
            {me?.plan === 'pro' || me?.plan === 'team' ? 'Подписка' : 'Бесплатно'}
          </span>
        </div>
      </header>

      <main className="main">
        {tab === 'check' && <CheckScreen me={me} onMe={setMe} />}
        {tab === 'top' && <TopScreen />}
        {tab === 'plans' && <PlansScreen me={me} onMe={setMe} />}
      </main>

      <footer className="foot">
        <p>
          Проверено — проверяем утверждения по курируемой базе фактов и первоисточникам.
          Если данных нет, честно говорим «непонятно», а не угадываем.
        </p>
      </footer>
    </div>
  );
}

// ---------------------------------------------------------------- проверка

function CheckScreen({ me, onMe }: { me: Me | null; onMe: (m: Me) => void }) {
  const [text, setText] = useState(() => sessionStorage.getItem('preset_text') ?? '');
  const [result, setResult] = useState<CheckResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = useCallback(async () => {
    const trimmed = text.trim();
    if (trimmed.length < 8) {
      setError('Нужно хотя бы 8 символов — иначе проверять нечего.');
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const data = await runCheck(trimmed);
      setResult(data);
      if (typeof data.quota_left === 'number') {
        onMe({ ...(me ?? { id: '', plan: 'free' }), plan: 'free', quota_left: data.quota_left });
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.code === 'QUOTA_EXCEEDED' ? err.message : `Ошибка: ${err.message}`);
      } else {
        setError('Не удалось проверить. Попробуйте ещё раз.');
      }
    } finally {
      setBusy(false);
    }
  }, [text, me, onMe]);

  // Ссылка вида ?q=... сразу запускает проверку — так удобно делиться вердиктом.
  useEffect(() => {
    const preset = sessionStorage.getItem('preset_text');
    if (!preset) return;
    sessionStorage.removeItem('preset_text');
    setText(preset);
    void (async () => {
      setBusy(true);
      try {
        const data = await runCheck(preset);
        setResult(data);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Не удалось проверить');
      } finally {
        setBusy(false);
      }
    })();
  }, []);

  return (
    <div className="stack">
      <section className="hero">
        <span className="eyebrow">Проверка новостей</span>
        <h1>Фейк или правда — за одну проверку</h1>
        <p className="hero__lead">
          Вставьте сообщение из чата, поста или пересылки. Мы сверим его с базой фактов
          и покажем, откуда взялась новость.
        </p>
      </section>

      <section className="card">
        <label className="label" htmlFor="check-text">
          Текст сообщения
        </label>
        <textarea
          id="check-text"
          className="input textarea"
          rows={5}
          maxLength={4000}
          value={text}
          placeholder="Например: СРОЧНО! ЦБ запретил наличные с 1 марта!"
          onChange={(e) => {
            setText(e.target.value);
            setError(null);
          }}
        />
        <div className="row-between">
          <span className="counter">{text.length} / 4000</span>
          <button className="btn btn--primary" onClick={submit} disabled={busy} type="button">
            {busy ? 'Проверяем…' : 'Проверить'}
          </button>
        </div>

        {error && <p className="alert alert--bad">{error}</p>}

        <div className="chips">
          <span className="chips__label">Примеры</span>
          {EXAMPLES.map((example, i) => (
            <button
              key={i}
              type="button"
              className="chip"
              onClick={() => {
                setText(example);
                setError(null);
                setResult(null);
              }}
            >
              {example.slice(0, 42)}…
            </button>
          ))}
        </div>
      </section>

      {result && <ResultCard result={result} onUpgraded={() => getMe().then(onMe)} />}
    </div>
  );
}

function ResultCard({ result, onUpgraded }: { result: CheckResponse; onUpgraded: () => void }) {
  const [upgrading, setUpgrading] = useState(false);
  const cls = levelClass(result.level);

  async function handleUpgrade() {
    setUpgrading(true);
    try {
      await upgrade('pro');
      onUpgraded();
      window.location.reload();
    } catch {
      setUpgrading(false);
    }
  }

  return (
    <section className={`card result result--${cls}`}>
      <div className="result__head">
        <div>
          <span className="eyebrow">Вердикт</span>
          <h2 className="result__verdict">{result.level_label}</h2>
        </div>
        <div className="gauge" aria-label={`Уровень доверия ${result.score} из 100`}>
          <span className="gauge__num">{result.score}</span>
          <span className="gauge__unit">из 100</span>
        </div>
      </div>

      <p className="result__line">
        Неуверенность {Math.round(result.uncertainty * 100)}% ·{' '}
        {result.verdict === 'правда'
          ? 'утверждение совпало с базой фактов'
          : result.verdict === 'фейк'
            ? 'база фактов утверждение опровергает'
            : 'данных для однозначного ответа нет'}
      </p>

      {result.plan === 'free' ? (
        <div className="paywall">
          <h3>Разбор — по подписке</h3>
          <p>{result.upgrade_hint}</p>
          <button className="btn btn--primary" onClick={handleUpgrade} disabled={upgrading} type="button">
            {upgrading ? 'Включаем…' : 'Открыть разбор — 300 ₽/мес'}
          </button>
          <span className="paywall__note">Первый месяц бесплатно</span>
        </div>
      ) : (
        <div className="breakdown">
          <h3>Из чего сложился вердикт</h3>
          <div className="signals">
            {(result.signals ?? []).map((s) => (
              <div key={s.id} className="signal">
                <div className="signal__top">
                  <span className="signal__name">{s.name}</span>
                  <span className={`tag tag--${s.verdict}`}>{signalLabel(s.verdict)}</span>
                </div>
                <p className="signal__text">{s.summary}</p>
                {typeof s.details?.url === 'string' && s.details.url && (
                  <a className="signal__src" href={s.details.url} target="_blank" rel="noreferrer">
                    {String(s.details.source ?? 'первоисточник')} →
                  </a>
                )}
              </div>
            ))}
          </div>

          {(result.next_steps ?? []).length > 0 && (
            <>
              <h3>Что проверить дальше</h3>
              <ul className="list">
                {(result.next_steps ?? []).map((n, i) => (
                  <li key={i}>{n.title}</li>
                ))}
              </ul>
            </>
          )}

          {(result.limits ?? []).length > 0 && (
            <>
              <h3>Границы проверки</h3>
              <ul className="list list--muted">
                {(result.limits ?? []).map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}

function signalLabel(v: string): string {
  return {
    supports_real: 'подтверждает',
    supports_fake: 'опровергает',
    neutral: 'нейтрально',
    unavailable: 'нет данных',
  }[v] ?? v;
}

// ------------------------------------------------------------------- топы

function TopScreen() {
  const [items, setItems] = useState<TopItem[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getTop(168), getStats()])
      .then(([top, st]) => {
        setItems(top.items);
        setStats(st);
      })
      .catch(() => setError('Не удалось загрузить топы'));
  }, []);

  return (
    <div className="stack">
      <section className="hero">
        <span className="eyebrow">Что проверяют сейчас</span>
        <h1>Топы проверок</h1>
        <p className="hero__lead">
          Одинаковые сообщения схлопываются в одну строку. Чем больше людей проверило —
          тем выше новость. Так из рейтинга вырастает медиа проверенных новостей.
        </p>
      </section>

      {stats && (
        <div className="stats">
          <div className="stat">
            <span className="stat__n">{stats.checks}</span>
            <span className="stat__l">проверок</span>
          </div>
          <div className="stat">
            <span className="stat__n">{stats.unique_claims}</span>
            <span className="stat__l">уникальных</span>
          </div>
          <div className="stat">
            <span className="stat__n">{stats.fake}</span>
            <span className="stat__l">фейков</span>
          </div>
          <div className="stat">
            <span className="stat__n">{stats.real}</span>
            <span className="stat__l">подтверждено</span>
          </div>
        </div>
      )}

      {error && <p className="alert alert--bad">{error}</p>}

      {items === null && !error && <p className="muted">Загружаем…</p>}

      {items && items.length === 0 && (
        <div className="empty">
          <h3>Пока пусто</h3>
          <p>Проверьте что-нибудь — и это появится здесь первым.</p>
        </div>
      )}

      {items && items.length > 0 && (
        <ol className="top-list">
          {items.map((item, i) => (
            <li key={item.text_hash} className={`top-item top-item--${levelClass(item.level)}`}>
              <span className="top-item__rank">{i + 1}</span>
              <div className="top-item__body">
                <p className="top-item__text">{item.sample_text}</p>
                <div className="top-item__meta">
                  <span className={`tag tag--${item.verdict === 'фейк' ? 'supports_fake' : item.verdict === 'правда' ? 'supports_real' : 'neutral'}`}>
                    {item.level_label}
                  </span>
                  <span>{item.checks_count} проверок</span>
                  {item.verdict_variants > 1 && (
                    <span className="muted">мнения расходятся</span>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ----------------------------------------------------------------- тарифы

function PlansScreen({ me, onMe }: { me: Me | null; onMe: (m: Me) => void }) {
  const [plans, setPlans] = useState<PlanInfo[]>([]);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getPricing()
      .then((p) => {
        setPlans(p.plans);
        setNote(p.note);
      })
      .catch(() => setPlans([]));
  }, []);

  async function pick(plan: PlanInfo) {
    if (plan.id === 'free') return;
    setBusy(true);
    try {
      await upgrade(plan.id);
      const fresh = await getMe();
      onMe(fresh);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <section className="hero">
        <span className="eyebrow">Тарифы</span>
        <h1>Бесплатно — вердикт. По подписке — разбор</h1>
        <p className="hero__lead">{note}</p>
      </section>

      <div className="plans">
        {plans.map((plan) => {
          const active = me?.plan === plan.id;
          return (
            <div key={plan.id} className={`plan${plan.recommended ? ' plan--rec' : ''}`}>
              <div className="plan__head">
                <h3>{plan.name}</h3>
                {plan.recommended && <span className="badge">рекомендуем</span>}
              </div>
              <div className="plan__price">
                {plan.price_rub === 0 ? '0 ₽' : `${plan.price_rub.toLocaleString('ru-RU')} ₽`}
                <span className="plan__per">/мес</span>
              </div>
              <p className="plan__limit">{plan.limits}</p>
              <ul className="list">
                {plan.features.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
              <button
                className={`btn ${plan.recommended ? 'btn--primary' : 'btn--ghost'}`}
                disabled={active || busy || plan.id === 'free'}
                onClick={() => pick(plan)}
                type="button"
              >
                {active ? 'Ваш тариф' : plan.id === 'free' ? 'Доступен всем' : 'Подключить'}
              </button>
            </div>
          );
        })}
      </div>

      <p className="muted small">
        Демонстрация: оплата не подключена, тариф переключается сразу. В продукте здесь
        платёжный провайдер.
      </p>
    </div>
  );
}
