import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// /api проксируется на бэкенд (uvicorn на :8000) и в dev, и в preview.
const proxy = {
  '/api': {
    target: 'http://localhost:8000',
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react()],
  server: { host: true, port: 5173, proxy },
  preview: { host: true, port: 4173, proxy },
  build: { target: 'es2020' },
});
