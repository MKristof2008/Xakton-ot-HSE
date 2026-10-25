import { useCallback, useState } from 'react';
import { isDemoMode, maxTextLength } from './config';
import { InputScreen } from './components/InputScreen';
import { ResultScreen } from './components/ResultScreen';
import { SiteHeader } from './components/SiteHeader';
import { useCheckMessage } from './hooks/useCheckMessage';
import type { Example } from './fixtures/examples';

function validateMessage(text: string): string | null {
  if (!text.trim()) return 'Введите текст сообщения — пустое сообщение проверить нельзя.';
  if (text.length > maxTextLength) {
    return `Текст длиннее лимита: ${text.length} из ${maxTextLength} символов. Сократите сообщение.`;
  }
  return null;
}

export default function App() {
  const [text, setText] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const { phase, isLoading, run, reset } = useCheckMessage();

  const handleSubmit = useCallback(() => {
    const error = validateMessage(text);
    setValidationError(error);
    if (error) return;
    void run(text);
  }, [run, text]);

  const handleClear = useCallback(() => {
    setText('');
    setValidationError(null);
  }, []);

  const handlePickExample = useCallback((example: Example) => {
    setText(example.text);
    setValidationError(null);
  }, []);

  const handleReset = useCallback(() => {
    reset();
    setText('');
    setValidationError(null);
  }, [reset]);

  const handleRetry = useCallback(() => {
    if (phase.kind === 'error') void run(phase.text);
  }, [phase, run]);

  return (
    <div className="app">
      <SiteHeader isDemo={isDemoMode} />
      <main className="app__main">
        {phase.kind === 'result' ? (
          <ResultScreen text={phase.text} data={phase.data} onReset={handleReset} />
        ) : (
          <InputScreen
            text={text}
            onTextChange={setText}
            onSubmit={handleSubmit}
            onClear={handleClear}
            onPickExample={handlePickExample}
            validationError={validationError}
            apiErrorKind={phase.kind === 'error' ? phase.error.kind : null}
            isLoading={isLoading}
            onRetry={handleRetry}
          />
        )}
      </main>
      <footer className="site-footer">
        <p>
          «До репоста» — учебный прототип. Мы не проверяем сообщение целиком и не ставим оценку
          правдивости: смотрите на доказательства по каждому утверждению.
        </p>
      </footer>
    </div>
  );
}
