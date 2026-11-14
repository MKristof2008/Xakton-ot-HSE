import { useCallback, useEffect, useState } from 'react';
import { createApiKey, getApiKeys, revokeApiKey } from '../api/client';
import type { ApiKey, ApiKeyUsage, Me } from '../types';
import { formatDate } from '../lib/formatDate';

/**
 * Корпоративный доступ: API-ключи для редакций.
 *
 * На встрече эксперт спрашивал, как строить бизнес с медиа: «корпорации
 * большие покупают просто токены». Здесь это и есть — ключ вместо
 * браузерного токена, с отзывом и счётчиком проверок.
 *
 * Ключ показывается один раз: на сервере лежит только его хеш.
 */
export function AccessScreen({ me }: { me: Me | null }) {
  const [items, setItems] = useState<ApiKey[] | null>(null);
  const [usage, setUsage] = useState<ApiKeyUsage | null>(null);
  const [fresh, setFresh] = useState<string | null>(null);
  const [label, setLabel] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const isTeam = me?.plan === 'team';

  const load = useCallback(() => {
    getApiKeys()
      .then((res) => {
        setItems(res.items);
        setUsage(res.usage);
      })
      .catch(() => setError('Не удалось загрузить ключи. Проверьте, что сервер запущен.'));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function issue() {
    setBusy(true);
    setError(null);
    try {
      const created = await createApiKey(label.trim());
      setFresh(created.key ?? null);
      setLabel('');
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось выпустить ключ.');
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    setError(null);
    try {
      await revokeApiKey(id);
      load();
    } catch {
      setError('Не удалось отозвать ключ.');
    }
  }

  async function copy() {
    if (!fresh) return;
    try {
      await navigator.clipboard.writeText(fresh);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="view">
      <section className="hero">
        <span className="eyebrow">Для редакций</span>
        <h1 className="hero__title">
          API-ключи <em>для команд</em>
        </h1>
        <p className="hero__lead">
          Один ключ на редакцию или сервис. Проверка вызывается тем же
          <code> POST /api/check</code>, только вместо токена браузера передаётся
          заголовок <code>X-Api-Key</code>.
        </p>
      </section>

      {!isTeam && (
        <div className="gate">
          <h3>Ключи доступны на тарифе «Редакция»</h3>
          <p>
            Сейчас у вас тариф {me?.plan === 'pro' ? '«Разбор»' : '«Бесплатно»'}.
            Ключи — часть «Редакции»: до 10 сотрудников, проверка пачкой,
            счётчик проверок для отчётности.
          </p>
        </div>
      )}

      {isTeam && (
        <>
          <section className="panel">
            <div className="field">
              <label className="field__label" htmlFor="key-label">
                <span>Название ключа</span>
                <span className="field__hint">чтобы понять, чей он</span>
              </label>
              <input
                id="key-label"
                className="textarea textarea--line"
                value={label}
                placeholder="Например: редакция новостей"
                onChange={(e) => setLabel(e.target.value)}
              />
            </div>
            <div className="form__foot">
              <span className="counter">
                {usage ? `${usage.checks} проверок за ${usage.days} дней` : ''}
              </span>
              <button
                className="btn btn--primary"
                type="button"
                onClick={() => void issue()}
                disabled={busy}
              >
                {busy ? 'Выпускаем…' : 'Выпустить ключ'}
              </button>
            </div>
          </section>

          {fresh && (
            <div className="key-reveal">
              <span className="eyebrow">Ключ создан — сохраните сейчас</span>
              <code className="key-reveal__value">{fresh}</code>
              <p>
                Больше мы его не покажем: в базе лежит только хеш.
              </p>
              <button className="btn btn--ghost" type="button" onClick={() => void copy()}>
                {copied ? 'Скопировано' : 'Скопировать ключ'}
              </button>
            </div>
          )}

          {error && (
            <p className="alert alert--bad" role="alert">
              <span aria-hidden="true">!</span>
              {error}
            </p>
          )}

          {items && items.length === 0 && (
            <div className="empty">
              <span className="empty__mark" aria-hidden="true">
                §
              </span>
              <h3>Ключей пока нет</h3>
              <p>Выпустите первый — он понадобится для интеграции.</p>
            </div>
          )}

          {items && items.length > 0 && (
            <ol className="key-list">
              {items.map((key) => (
                <li className={`key-item${key.revoked_at ? ' is-revoked' : ''}`} key={key.id}>
                  <div className="key-item__main">
                    <span className="key-item__label">{key.label || 'без названия'}</span>
                    <code className="key-item__prefix">{key.prefix}…</code>
                  </div>
                  <div className="key-item__meta">
                    <span>создан {formatDate(key.created_at) ?? '—'}</span>
                    <span>
                      {key.revoked_at
                        ? 'отозван'
                        : key.last_used_at
                          ? `использован ${formatDate(key.last_used_at)}`
                          : 'ещё не использовался'}
                    </span>
                  </div>
                  {!key.revoked_at && (
                    <button
                      className="btn btn--ghost btn--small"
                      type="button"
                      onClick={() => void revoke(key.id)}
                    >
                      Отозвать
                    </button>
                  )}
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </div>
  );
}
