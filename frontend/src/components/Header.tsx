import type { Me } from '../types';
import type { Tab } from '../lib/tabs';
import { BrandMark } from './icons';

const TABS: { id: Tab; label: string }[] = [
  { id: 'check', label: 'Проверить' },
  { id: 'top', label: 'Топы' },
  { id: 'plans', label: 'Тарифы' },
];

interface Props {
  tab: Tab;
  me: Me | null;
  onNavigate: (tab: Tab) => void;
}

export function Header({ tab, me, onNavigate }: Props) {
  const paid = me?.plan === 'pro' || me?.plan === 'team';

  return (
    <header className="header">
      <div className="header__inner">
        <button className="brand" type="button" onClick={() => onNavigate('check')}>
          <span className="brand__mark" aria-hidden="true">
            <BrandMark />
          </span>
          <span className="brand__name">Ревизор</span>
        </button>

        <nav className="nav" aria-label="Разделы">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`nav__link${tab === item.id ? ' is-active' : ''}`}
              aria-current={tab === item.id ? 'page' : undefined}
              onClick={() => onNavigate(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <span className={`plan-chip plan-chip--${me?.plan ?? 'free'}`}>
          {paid ? 'Подписка' : 'Бесплатно'}
        </span>
      </div>
    </header>
  );
}
