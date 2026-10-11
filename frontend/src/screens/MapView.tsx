/* Яндекс Карты 2.1 не имеют официальных типов, поэтому объекты карты — any. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, errorText, isAbort } from '../api';
import { EmptyState, Spinner } from '../components/States';
import { Icon } from '../components/Icon';
import { filtersToQuery, isEmptyFilter, type Filters } from '../filters';
import { formatPay, formatWhen, plural } from '../format';
import { YMAPS_KEY, loadYmaps } from '../ymaps';
import type { GeoPoint, Job, Meta } from '../types';

interface Props {
  meta: Meta;
  filters: Filters;
  location: GeoPoint | null;
  active: boolean;
  onOpenJob(job: Job): void;
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);

export function MapView(props: Props) {
  if (!YMAPS_KEY) {
    return (
      <div className="screen">
        <EmptyState
          icon="map"
          title="Карта скоро появится"
          text="Пока все заявки есть во вкладке «Лента». Для карты нужен ключ Яндекс Карт."
        />
      </div>
    );
  }
  return <YandexMap {...props} />;
}

function YandexMap({ meta, filters, location, active, onOpenJob }: Props) {
  const box = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const omRef = useRef<any>(null);
  const meRef = useRef<any>(null);
  const jobsById = useRef(new Map<number, Job>());
  const openRef = useRef(onOpenJob);
  openRef.current = onOpenJob;

  const [mapState, setMapState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [data, setData] = useState<{ status: 'loading' | 'ready' | 'error'; count: number; total: number; error?: string }>({
    status: 'loading',
    count: 0,
    total: 0,
  });
  const [reload, setReload] = useState(0);

  const query = useMemo(() => filtersToQuery(filters, location), [filters, location]);
  const queryKey = JSON.stringify(query);

  // создать карту один раз
  useEffect(() => {
    let destroyed = false;
    loadYmaps()
      .then((ymaps) => {
        if (destroyed || !box.current) return;
        const map = new ymaps.Map(
          box.current,
          { center: [meta.city.lat, meta.city.lng], zoom: 10, controls: ['zoomControl'] },
          { suppressMapOpenBlock: true, yandexMapDisablePoiInteractivity: true },
        );
        const om = new ymaps.ObjectManager({
          clusterize: true,
          gridSize: 64,
          clusterDisableClickZoom: false,
          clusterBalloonContentLayout: 'cluster#balloonCarousel',
          clusterBalloonContentLayoutWidth: 260,
          clusterBalloonContentLayoutHeight: 130,
        });
        om.objects.options.set({ preset: 'islands#dotIcon', iconColor: '#8A2BF7', hasBalloon: false });
        om.clusters.options.set({ preset: 'islands#invertedOrangeClusterIcons' });
        om.objects.events.add('click', (e: any) => {
          const job = jobsById.current.get(Number(e.get('objectId')));
          if (job) openRef.current(job);
        });
        map.geoObjects.add(om);
        mapRef.current = map;
        omRef.current = om;
        setMapState('ready');
      })
      .catch(() => !destroyed && setMapState('error'));
    return () => {
      destroyed = true;
      mapRef.current?.destroy();
      mapRef.current = null;
      omRef.current = null;
      meRef.current = null;
    };
  }, [meta.city.lat, meta.city.lng, reload]);

  // кнопка «Подробнее» в балуне кластера
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const el = (e.target as HTMLElement | null)?.closest?.('[data-gigo-job]');
      if (!el) return;
      const job = jobsById.current.get(Number(el.getAttribute('data-gigo-job')));
      if (job) openRef.current(job);
    };
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, []);

  // данные под фильтр
  useEffect(() => {
    if (mapState !== 'ready') return;
    const c = new AbortController();
    setData((d) => ({ ...d, status: 'loading' }));
    api
      .jobs({ ...query, with_location: true, limit: 500 }, c.signal)
      .then((page) => {
        const om = omRef.current;
        if (c.signal.aborted || !om) return;
        const withPoint = page.items.filter((j) => j.lat != null && j.lng != null);
        jobsById.current = new Map(withPoint.map((j) => [j.id, j]));
        om.removeAll();
        om.add({
          type: 'FeatureCollection',
          features: withPoint.map((j) => {
            const pay = formatPay(j);
            const when = formatWhen(j);
            const sub = [pay, j.metro?.name, when].filter(Boolean).join(' · ');
            return {
              type: 'Feature',
              id: j.id,
              geometry: { type: 'Point', coordinates: [j.lat, j.lng] },
              properties: {
                hintContent: esc(`${j.title}${pay ? ` · ${pay}` : ''}`),
                clusterCaption: esc(pay ?? j.title),
                balloonContentHeader: esc(j.title),
                balloonContentBody: `<div class="ymap-balloon">${esc(sub)}<br><button type="button" class="ymap-open" data-gigo-job="${j.id}">Подробнее</button></div>`,
              },
            };
          }),
        });
        setData({ status: 'ready', count: withPoint.length, total: page.total });
      })
      .catch((e) => {
        if (isAbort(e) || c.signal.aborted) return;
        setData({ status: 'error', count: 0, total: 0, error: errorText(e) });
      });
    return () => c.abort();
  }, [queryKey, mapState]);

  // моё местоположение
  useEffect(() => {
    const map = mapRef.current;
    const ymaps = window.ymaps;
    if (mapState !== 'ready' || !map || !ymaps) return;
    if (meRef.current) {
      map.geoObjects.remove(meRef.current);
      meRef.current = null;
    }
    if (location) {
      const me = new ymaps.Placemark([location.lat, location.lng], { hintContent: 'Вы здесь' }, { preset: 'islands#geolocationIcon', iconColor: '#2481cc' });
      map.geoObjects.add(me);
      meRef.current = me;
    }
  }, [location, mapState]);

  // карта была скрыта (display: none) — пересчитать размер
  useEffect(() => {
    if (active && mapRef.current) mapRef.current.container.fitToViewport();
  }, [active]);

  const centerOnMe = useCallback(() => {
    if (location && mapRef.current) mapRef.current.setCenter([location.lat, location.lng], 14, { duration: 300 });
  }, [location]);

  return (
    <div className="map-screen">
      <div ref={box} className="map-box" />
      <div className="map-status">
        {mapState === 'loading' && (
          <span className="map-pill">
            <Spinner /> Загружаем карту…
          </span>
        )}
        {mapState === 'error' && (
          <span className="map-pill">
            <Icon name="alert" size={16} />
            Карта не загрузилась.{' '}
            <button
              type="button"
              className="link-btn"
              onClick={() => {
                setMapState('loading');
                setReload((r) => r + 1);
              }}
            >
              Повторить
            </button>
          </span>
        )}
        {mapState === 'ready' && data.status === 'loading' && (
          <span className="map-pill">
            <Spinner /> Ищем заявки…
          </span>
        )}
        {mapState === 'ready' && data.status === 'ready' && (
          <span className="map-pill">
            {data.count} {plural(data.count, ['заявка', 'заявки', 'заявок'])} на карте
            {!isEmptyFilter(filters) && ' · фильтр как в ленте'}
          </span>
        )}
        {mapState === 'ready' && data.status === 'error' && <span className="map-pill">{data.error}</span>}
      </div>
      {location && mapState === 'ready' && (
        <button type="button" className="map-me" onClick={centerOnMe} aria-label="Показать, где я" title="Где я">
          <Icon name="locate" size={22} />
        </button>
      )}
    </div>
  );
}
