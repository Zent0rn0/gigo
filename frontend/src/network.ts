import { useEffect, useRef, useState } from 'react';

function onlineNow(): boolean {
  return typeof navigator === 'undefined' || navigator.onLine !== false;
}

/** Есть ли сеть по мнению устройства. «Есть» не гарантирует, что сервер доступен, но «нет» — точно нет. */
export function useOnline(): boolean {
  const [online, setOnline] = useState(onlineNow);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    return () => {
      window.removeEventListener('online', up);
      window.removeEventListener('offline', down);
    };
  }, []);
  return online;
}

/** Вызвать cb, когда сеть вернулась: экран с ошибкой загрузки сам повторит запрос. */
export function useOnReconnect(cb: () => void) {
  const ref = useRef(cb);
  ref.current = cb;
  useEffect(() => {
    const on = () => ref.current();
    window.addEventListener('online', on);
    return () => window.removeEventListener('online', on);
  }, []);
}
