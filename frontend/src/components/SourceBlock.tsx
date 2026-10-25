import type { SourceItem } from '../types';
import { formatDate } from '../lib/formatDate';
import { readableUrl, safeHttpUrl } from '../lib/safeUrl';

export function SourceBlock({ source }: { source: SourceItem | null }) {
  if (!source) {
    return <p className="source source--missing">Источник недоступен</p>;
  }

  const href = safeHttpUrl(source.url);
  const published = formatDate(source.published_at);
  const retrieved = formatDate(source.retrieved_at);

  return (
    <div className="source">
      <p className="source__title">{source.title || 'Источник без названия'}</p>
      {href ? (
        <a className="source__link" href={href} target="_blank" rel="noopener noreferrer nofollow">
          {readableUrl(href)}
        </a>
      ) : (
        <p className="source__link source__link--plain">
          {source.url ? source.url : 'Ссылка недоступна'}
        </p>
      )}
      {(published || retrieved) && (
        <dl className="source__dates">
          {published && (
            <>
              <dt>Опубликовано</dt>
              <dd>{published}</dd>
            </>
          )}
          {retrieved && (
            <>
              <dt>Получено при проверке</dt>
              <dd>{retrieved}</dd>
            </>
          )}
        </dl>
      )}
    </div>
  );
}
