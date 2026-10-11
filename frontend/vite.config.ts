import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// /api проксируется на бэкенд (uvicorn на :8000) и в dev, и в preview.
const proxy = {
  '/api': {
    target: 'http://localhost:8000',
    changeOrigin: true,
    // Пробрасываем X-Forwarded-For: вход без Telegram (DEV_AUTH) работает только с этой машины, не с телефона в сети.
    xfwd: true,
  },
};

export default defineConfig(({ mode }) => {
  // Ключ карт и имя бота можно держать в общем .env в корне проекта; frontend/.env* и переменные окружения важнее.
  const local = loadEnv(mode, '.', 'VITE_');
  const root = loadEnv(mode, '..', 'VITE_');
  const pick = (k: string) => local[k] || root[k] || '';
  return {
    plugins: [react()],
    define: {
      'import.meta.env.VITE_YANDEX_MAPS_KEY': JSON.stringify(pick('VITE_YANDEX_MAPS_KEY')),
      'import.meta.env.VITE_BOT_USERNAME': JSON.stringify(pick('VITE_BOT_USERNAME')),
      'import.meta.env.VITE_MINIAPP_NAME': JSON.stringify(pick('VITE_MINIAPP_NAME')),
    },
    server: { host: true, port: 5173, proxy },
    preview: { host: true, port: 4173, proxy },
    build: { target: 'es2020' },
  };
});
