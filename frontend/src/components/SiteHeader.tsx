import { isDemoMode } from '../config';

export type Screen = 'feed' | 'upload' | 'listing' | 'checking';

const NAV: { key: Screen; label: string }[] = [
  { key: 'feed', label: 'Лента' },
  { key: 'upload', label: 'Загрузить' },
];

interface SiteHeaderProps {
  screen: Screen;
  onNavigate: (screen: Screen) => void;
}

export function SiteHeader({ screen, onNavigate }: SiteHeaderProps) {
  return (
    <header className="site-header">
      <div className="site-header__inner">
        <button type="button" className="brand" onClick={() => onNavigate('feed')}>
          <span className="brand__mark" aria-hidden="true">
            ○
          </span>
          Свидетель
        </button>

        <nav className="site-nav" aria-label="Разделы">
          {NAV.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`site-nav__link${isActive(screen, item.key) ? ' is-active' : ''}`}
              aria-current={isActive(screen, item.key) ? 'page' : undefined}
              onClick={() => onNavigate(item.key)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        {isDemoMode && <span className="demo-badge">демо</span>}
      </div>
    </header>
  );
}

function isActive(screen: Screen, key: Screen): boolean {
  if (key === 'upload') return screen === 'upload' || screen === 'checking';
  return screen === 'feed' || screen === 'listing';
}