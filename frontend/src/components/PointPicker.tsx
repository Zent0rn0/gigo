import { useEffect, useRef, useState } from 'react';
import { loadYmaps } from '../ymaps';
import { Icon } from './Icon';
import { Sheet } from './Sheet';

export interface Point {
  lat: number;
  lng: number;
}

interface Props {
  center: Point;
  zoom: number;
  onClose(): void;
  /** Точка и адрес, который Яндекс нашёл под ней (если нашёл). */
  onApply(point: Point, address: string | null): void;
}

/** Выбор места на карте: двигаешь карту, булавка в центре. */
export function PointPicker({ center, zoom, onClose, onApply }: Props) {
  const box = useRef<HTMLDivElement | null>(null);
  const map = useRef<any>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    loadYmaps()
      .then((ymaps) => {
        if (!alive || !box.current) return;
        map.current = new ymaps.Map(box.current, { center: [center.lat, center.lng], zoom, controls: ['zoomControl'] },
          { suppressMapOpenBlock: true });
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
      map.current?.destroy();
      map.current = null;
    };
    // карта создаётся один раз при открытии
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const apply = async () => {
    if (!map.current || busy) return;
    const [lat, lng] = map.current.getCenter();
    setBusy(true);
    let address: string | null = null;
    try {
      const res = await window.ymaps.geocode([lat, lng], { kind: 'house', results: 1 });
      const obj = res.geoObjects.get(0);
      address = obj ? obj.getAddressLine().replace(/^Россия,\s*/, '').replace(/^Москва,\s*/, '') : null;
    } catch {
      /* без адреса тоже годится */
    }
    setBusy(false);
    onApply({ lat, lng }, address);
  };

  return (
    <Sheet
      title="Где работа"
      onClose={onClose}
      footer={
        <button type="button" className="btn btn--primary btn--wide" onClick={apply} disabled={failed || busy}>
          {busy ? 'Ищем адрес…' : 'Выбрать это место'}
        </button>
      }
    >
      {failed ? (
        <div className="hint center">Карта не загрузилась. Укажите метро или адрес текстом.</div>
      ) : (
        <div className="point-map">
          <div className="point-map__map" ref={box} />
          <div className="point-map__pin" aria-hidden="true">
            <Icon name="pin" size={40} strokeWidth={2.2} />
          </div>
        </div>
      )}
      <div className="hint small center">Передвиньте карту так, чтобы булавка стояла на месте работы.</div>
    </Sheet>
  );
}
