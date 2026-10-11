// Загрузка Яндекс Карт JS API 2.1 по требованию.

declare global {
  interface Window {
    ymaps?: any;
  }
}

export const YMAPS_KEY = (import.meta.env.VITE_YANDEX_MAPS_KEY ?? '').trim();

let loading: Promise<any> | null = null;

export function loadYmaps(): Promise<any> {
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    if (window.ymaps) {
      window.ymaps.ready(() => resolve(window.ymaps));
      return;
    }
    const s = document.createElement('script');
    s.src = `https://api-maps.yandex.ru/2.1/?apikey=${encodeURIComponent(YMAPS_KEY)}&lang=ru_RU`;
    s.async = true;
    s.onload = () => {
      if (!window.ymaps) return reject(new Error('ymaps missing'));
      window.ymaps.ready(() => resolve(window.ymaps), reject);
    };
    s.onerror = () => reject(new Error('ymaps load failed'));
    document.head.appendChild(s);
  });
  loading.catch(() => {
    loading = null;
  });
  return loading;
}
