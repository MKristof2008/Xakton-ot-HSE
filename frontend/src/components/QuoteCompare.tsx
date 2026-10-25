interface QuoteCompareProps {
  claimText: string;
  quote: string | null;
}

/**
 * Сравнение двух цитат бок о бок: что сказано в сообщении
 * и что сказано в источнике. Ничего не додумываем.
 */
export function QuoteCompare({ claimText, quote }: QuoteCompareProps) {
  return (
    <div className="compare">
      <div className="compare__col compare__col--message">
        <p className="compare__label">В сообщении</p>
        <p className="compare__text">{claimText}</p>
      </div>
      <div className="compare__col compare__col--source">
        <p className="compare__label">В источнике</p>
        {quote ? (
          <p className="compare__text">«{quote}»</p>
        ) : (
          <p className="compare__text compare__text--empty">Цитата не найдена</p>
        )}
      </div>
    </div>
  );
}
