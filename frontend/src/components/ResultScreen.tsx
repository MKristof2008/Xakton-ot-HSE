import { useCallback, useEffect, useRef, useState } from 'react';
import type { CheckResponse } from '../types';
import { ClaimList } from './ClaimList';
import { EvidencePanel } from './EvidencePanel';
import { HighlightedMessage } from './HighlightedMessage';
import { MessageBlock } from './MessageBlock';
import { ShareBlock } from './ShareBlock';
import { Thread } from './Thread';

interface ResultScreenProps {
  text: string;
  data: CheckResponse;
  onReset: () => void;
}

interface Anchor {
  from: HTMLElement | null;
  to: HTMLElement | null;
}

export function ResultScreen({ text, data, onReset }: ResultScreenProps) {
  const [selectedId, setSelectedId] = useState<string | null>(data.claims[0]?.id ?? null);
  const [board, setBoard] = useState<HTMLElement | null>(null);
  const [anchor, setAnchor] = useState<Anchor>({ from: null, to: null });
  const phraseRefs = useRef<Map<string, HTMLElement>>(new Map());
  const cardRefs = useRef<Map<string, HTMLElement>>(new Map());

  const activeClaim = data.claims.find((claim) => claim.id === selectedId) ?? data.claims[0] ?? null;
  const hasClaims = data.claims.length > 0;
  const activeId = activeClaim?.id ?? null;

  const registerPhrase = useCallback((id: string, element: HTMLElement | null) => {
    if (element) phraseRefs.current.set(id, element);
    else phraseRefs.current.delete(id);
  }, []);

  const registerCard = useCallback((id: string, element: HTMLElement | null) => {
    if (element) cardRefs.current.set(id, element);
    else cardRefs.current.delete(id);
  }, []);

  useEffect(() => {
    if (!activeId) {
      setAnchor({ from: null, to: null });
      return;
    }
    setAnchor({
      from: phraseRefs.current.get(activeId) ?? null,
      to: cardRefs.current.get(activeId) ?? null,
    });
  }, [activeId, data]);

  return (
    <div className="screen screen--result">
      <div className="result__head">
        <div className="result__headline">
          <p className="eyebrow">Разбор сообщения</p>
          <h1 className="result__title">Что подтверждают источники</h1>
          <p className="result__note">Вывод основан на материалах, полученных во время проверки.</p>
        </div>
        <button type="button" className="btn btn--ghost" onClick={onReset}>
          Проверить другое сообщение
        </button>
      </div>

      {hasClaims ? (
        <>
          <div className="board" ref={setBoard}>
            {activeClaim && (
              <Thread
                board={board}
                from={anchor.from}
                to={anchor.to}
                status={activeClaim.status}
                anchorKey={activeId ?? ''}
              />
            )}
            <div className="board__col board__col--message">
              <HighlightedMessage
                text={text}
                claims={data.claims}
                selectedId={activeId}
                onSelect={setSelectedId}
                registerPhrase={registerPhrase}
              />
            </div>
            <div className="board__col board__col--claims">
              <ClaimList
                claims={data.claims}
                selectedId={activeId}
                onSelect={setSelectedId}
                registerCard={registerCard}
              />
            </div>
          </div>
          <EvidencePanel claim={activeClaim} sources={data.sources} />
          {data.share_text && <ShareBlock text={data.share_text} />}
        </>
      ) : (
        <>
          <section className="card card--empty" aria-labelledby="no-claims-title">
            <h2 className="section-title" id="no-claims-title">
              В сообщении не выделены проверяемые утверждения
            </h2>
            <p className="card__text">
              {data.uncheckable_reason ??
                'Попробуйте переформулировать: добавьте конкретное утверждение, которое можно сверить с источником.'}
            </p>
          </section>
          <MessageBlock text={text} />
          {data.share_text && <ShareBlock text={data.share_text} />}
        </>
      )}
    </div>
  );
}
