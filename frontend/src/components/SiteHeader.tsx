export function SiteHeader({ isDemo }: { isDemo: boolean }) {
  return (
    <header className="site-header">
      <div className="site-header__inner">
        <span className="brand">
          <span className="brand__dot" aria-hidden="true" />
          До репоста
        </span>
        <span className="brand__tagline">проверка сообщения перед пересылкой</span>
        <span className="hack-chip">сделано на хакатоне ФКН</span>
      </div>
      {isDemo && <p className="demo-badge">Демонстрационный режим · учебные данные</p>}
    </header>
  );
}
