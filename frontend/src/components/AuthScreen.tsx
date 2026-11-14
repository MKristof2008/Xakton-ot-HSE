import { useEffect, useRef, useState } from 'react';
import { ApiError, login, register } from '../api/client';
import type { Me } from '../types';

interface Props {
  onAuth: (me: Me) => void;
  onSkip?: () => void;
}

type Mode = 'login' | 'register';

export function AuthScreen({ onAuth }: Props) {
  const [mode, setMode] = useState<Mode>('register');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const firstField = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstField.current?.focus();
  }, [mode]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email.trim())) {
      setError('Введите корректный email');
      return;
    }
    if (password.length < 8) {
      setError('Пароль должен быть не короче 8 символов');
      return;
    }

    setBusy(true);
    try {
      const user =
        mode === 'register'
          ? await register(email.trim(), password, name.trim())
          : await login(email.trim(), password);
      onAuth(user);
    } catch (err: unknown) {
      const code = err instanceof ApiError ? err.code : '';
      const message = err instanceof ApiError ? err.message : '';
      setError(
        code === 'EMAIL_TAKEN'
          ? 'Аккаунт с таким email уже есть. Войдите.'
          : code === 'BAD_CREDENTIALS'
            ? 'Неверный email или пароль.'
            : message || 'Не удалось связаться с сервером. Проверьте, что он запущен.',
      );
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <div className="auth__panel">
        <div className="auth__brand">
          <span className="auth__dot" aria-hidden="true" />
          <span>Ревизор</span>
        </div>

        <h1 className="auth__title">
          {mode === 'register' ? 'Заведите аккаунт' : 'С возвращением'}
        </h1>
        <p className="auth__lead">
          {mode === 'register'
            ? 'Проверка доступна по аккаунту: так работают лимиты и подписка.'
            : 'Войдите, чтобы продолжить проверять сообщения.'}
        </p>

        <form className="auth__form" onSubmit={submit} noValidate>
          {mode === 'register' && (
            <label className="auth__field">
              <span className="auth__label">Как вас зовут</span>
              <input
                ref={firstField}
                className="input"
                type="text"
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Необязательно"
              />
            </label>
          )}

          <label className="auth__field">
            <span className="auth__label">Email</span>
            <input
              ref={mode === 'login' ? firstField : undefined}
              className="input"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setError(null);
              }}
              placeholder="you@example.com"
            />
          </label>

          <label className="auth__field">
            <span className="auth__label">Пароль</span>
            <input
              className="input"
              type="password"
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              required
              minLength={8}
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setError(null);
              }}
              placeholder="Минимум 8 символов"
            />
          </label>

          {error && (
            <p className="alert alert--bad" role="alert">
              {error}
            </p>
          )}

          <button className="btn btn--primary auth__submit" type="submit" disabled={busy}>
            {busy
              ? 'Секунду…'
              : mode === 'register'
                ? 'Создать аккаунт'
                : 'Войти'}
          </button>
        </form>

        <p className="auth__switch">
          {mode === 'register' ? (
            <>
              Уже есть аккаунт?{' '}
              <button type="button" onClick={() => { setMode('login'); setError(null); }}>
                Войти
              </button>
            </>
          ) : (
            <>
              Нет аккаунта?{' '}
              <button type="button" onClick={() => { setMode('register'); setError(null); }}>
                Зарегистрироваться
              </button>
            </>
          )}
        </p>

        <p className="auth__note">
          10 проверок в день бесплатно. Подписка снимает лимит и открывает разбор.
        </p>
      </div>

      <aside className="auth__side">
        <p className="eyebrow">Что внутри</p>
        <ul className="auth__features">
          <li>
            <strong>Вердикт за секунды</strong>
            <span>Сверка с базой фактов и первоисточниками</span>
          </li>
          <li>
            <strong>Цитата в источнике</strong>
            <span>Видно, где именно сказано то, на чём основан вердикт</span>
          </li>
          <li>
            <strong>Паспорт проверки</strong>
            <span>Постоянная ссылка, которую можно переслать в чат</span>
          </li>
        </ul>
      </aside>
    </div>
  );
}