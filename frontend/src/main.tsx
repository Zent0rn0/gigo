import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { initTelegram } from './telegram';
import './styles.css';

try {
  initTelegram();
} catch (e) {
  // без Telegram-обвязки приложение всё равно должно открыться
  console.error('[gigo] initTelegram', e);
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary name="app" root>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);

// Приложение запустилось: запасной экран из boot-check.js больше не нужен.
(window as { __gigoStarted?: boolean }).__gigoStarted = true;
