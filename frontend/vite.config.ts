import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// /api проксируется на бэкенд (uvicorn на :8000) и в dev, и в preview.
const proxy = {
  '/api': {
    target: 'http://localhost:8000',
    changeOrigin: true,
  },
};

export default defineConfig(({ mode }) => {
  // Ключ карт можно держать в общем .env в корне проекта; frontend/.env* и переменные окружения важнее.
  const mapsKey = loadEnv(mode, '.', 'VITE_').VITE_YANDEX_MAPS_KEY || loadEnv(mode, '..', 'VITE_').VITE_YANDEX_MAPS_KEY || '';
  return {
    plugins: [react()],
    define: { 'import.meta.env.VITE_YANDEX_MAPS_KEY': JSON.stringify(mapsKey) },
    server: { host: true, port: 5173, proxy },
    preview: { host: true, port: 4173, proxy },
    build: { target: 'es2020' },
  };
});
