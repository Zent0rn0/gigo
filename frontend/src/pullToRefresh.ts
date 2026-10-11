import { useEffect, useRef, useState } from 'react';

const TRIGGER = 64;
const MAX = 96;

/**
 * «Потяните вниз, чтобы обновить» для страницы, которая прокручивается целиком (window).
 * Возвращает, насколько оттянули (0…MAX px); при отпускании дальше TRIGGER вызывает onRefresh.
 */
export function usePullToRefresh(onRefresh: () => void, enabled: boolean): { pull: number; ready: boolean } {
  const [pull, setPull] = useState(0);
  const cb = useRef(onRefresh);
  cb.current = onRefresh;

  useEffect(() => {
    if (!enabled) return;
    let startY = 0;
    let tracking = false;
    let dist = 0;
    const onStart = (e: TouchEvent) => {
      if (e.touches.length !== 1 || window.scrollY > 0 || document.body.style.overflow === 'hidden') return;
      startY = e.touches[0].clientY;
      tracking = true;
      dist = 0;
    };
    const onMove = (e: TouchEvent) => {
      if (!tracking) return;
      const dy = e.touches[0].clientY - startY;
      if (dy <= 0 || window.scrollY > 0) {
        if (dist) setPull((dist = 0));
        return;
      }
      dist = Math.min(MAX, dy * 0.5);
      setPull(dist);
    };
    const onEnd = () => {
      if (!tracking) return;
      tracking = false;
      if (dist >= TRIGGER) cb.current();
      dist = 0;
      setPull(0);
    };
    window.addEventListener('touchstart', onStart, { passive: true });
    window.addEventListener('touchmove', onMove, { passive: true });
    window.addEventListener('touchend', onEnd);
    window.addEventListener('touchcancel', onEnd);
    return () => {
      window.removeEventListener('touchstart', onStart);
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onEnd);
      window.removeEventListener('touchcancel', onEnd);
      setPull(0);
    };
  }, [enabled]);

  return { pull, ready: pull >= TRIGGER };
}
