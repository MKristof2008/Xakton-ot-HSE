import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles/global.css';

const container = document.getElementById('root');
if (!container) throw new Error('Не найден корневой элемент #root');

// Автозапуск проверки по ?q= — удобно для скриншотов и для ссылок из чата.
const params = new URLSearchParams(window.location.search);
const preset = params.get('q');
if (preset) {
  sessionStorage.setItem('preset_text', preset);
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
