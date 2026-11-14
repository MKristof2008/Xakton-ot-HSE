import { useEffect, useRef, useState } from 'react';
import { ApiError, login, register } from '../api/client';
import type { Me } from '../types';

interface Props {
  /** Почему просим войти: «чтобы проверить», «чтобы открыть разбор». */
  reason?: string;
  onAuth: (me: Me) => void;
  onClose: () => void;
}

type Mode = 'register' | 'login';

/**
 * Вход по требованию: открывается поверх сайта, когда действие без
 * аккаунта невозможно. Гость успевает увидеть продукт и ввести текст —
 * регистрация просится на конкретном шаге, а не на входной стене.
 */
export function AuthDialog({ reason, onAuth, onClose }: Props) {
  const [mode, setMode] = useState<Mode>('register');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    emailRef.current?.focus();
  }, [mode]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onClose();
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose, busy]);

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
    } catch (err) {
      const code = err instanceof ApiError ? err.code : '';
      const message = err instanceof ApiError ? err.message : '';
      setError(
        code === 'EMAIL_TAKEN'
          ? 'Аккаунт с таким email уже есть. Войдите.'
          : code === 'BAD_CREDENTIALS'
            ? 'Неверный email или пароль.'
            : message || 'Не удалось связаться с сервером.',
      );
      setBusy(false);
    }
  }

  return (
    <div
      className="pay-overlay"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div
        className="pay auth-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-title"
        tabIndex={-1}
        ref={dialogRef}
      >
        <button
          className="pay__close"
          onClick={onClose}
          type="button"
          aria-label="Закрыть"
          disabled={busy}
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" stroke="currentColor" strokeWidth="1.8"
              strokeLinecap="round" />
          </svg>
        </button>

        <div className="pay__head">
          <span className="eyebrow">
            {mode === 'register' ? 'Регистрация' : 'Вход'}
          </span>
          <h2 id="auth-title">
            {mode === 'register' ? 'Создайте аккаунт' : 'Войдите'}
          </h2>
          <p className="auth-dialog__reason">
            {reason || 'Проверка доступна по аккаунту: так работают лимиты и подписка.'}
          </p>
        </div>

        <form className="auth__form" onSubmit={submit} noValidate>
          {mode === 'register' && (
            <label className="auth__field">
              <span className="auth__label">Как вас зовут</span>
              <input
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
              ref={emailRef}
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
                ? 'Создать аккаунт и проверить'
                : 'Войти и проверить'}
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
    </div>
  );
}