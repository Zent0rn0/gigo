import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { DEFAULT_LANG, normalizeLang, setLang, storedLang, useLang } from './i18n';
import { initTelegram, telegramLanguage } from './telegram';
import './styles.css';

try {
  initTelegram();
} catch (e) {
  // без Telegram-обвязки приложение всё равно должно открыться
  console.error('[gigo] initTelegram', e);
}

/** При смене языка приложение собирается заново: так все экраны и справочники берутся на новом языке. */
function LangRoot() {
  const lang = useLang();
  return <App key={lang} />;
}

function render() {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <ErrorBoundary name="app" root>
        <LangRoot />
      </ErrorBoundary>
    </StrictMode>,
  );
}

// Первый экран сразу на нужном языке: выбранный на этом устройстве, иначе язык Telegram, иначе русский.
// Язык из профиля на сервере придёт вместе с /api/me и при отличии переключит интерфейс.
const startLang = storedLang() ?? normalizeLang(telegramLanguage) ?? DEFAULT_LANG;
setLang(startLang).then(render, render);

// Приложение запустилось: запасной экран из boot-check.js больше не нужен.
(window as { __gigoStarted?: boolean }).__gigoStarted = true;
