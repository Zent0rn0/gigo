import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { api, errorText } from './api';
import { TabBar, type Tab } from './components/TabBar';
import { ErrorState, Spinner } from './components/States';
import { loadFilters, saveFilters, type Filters } from './filters';
import { getPosition } from './geo';
import { Feed } from './screens/Feed';
import { JobDetail } from './screens/JobDetail';
import { MapView } from './screens/MapView';
import { Subscriptions } from './screens/Subscriptions';
import { backButtonSupported, deepLinkJobId, haptic, tg } from './telegram';
import type { GeoPoint, Job, Meta } from './types';

interface Detail {
  id: number;
  job: Job | null;
}

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState('');
  const [metaAttempt, setMetaAttempt] = useState(0);

  const [tab, setTab] = useState<Tab>('feed');
  const [visited, setVisited] = useState<Set<Tab>>(() => new Set<Tab>(['feed']));
  const [detail, setDetail] = useState<Detail | null>(() => {
    const id = deepLinkJobId();
    return id != null ? { id, job: null } : null;
  });

  const [filters, setFilters] = useState<Filters>(loadFilters);
  const [location, setLocation] = useState<GeoPoint | null>(null);
  const [locating, setLocating] = useState(false);
  const [subsVersion, setSubsVersion] = useState(0);
  const [toastText, setToastText] = useState<string | null>(null);

  // справочники
  useEffect(() => {
    setMetaError('');
    api
      .meta()
      .then(setMeta)
      .catch((e) => setMetaError(errorText(e)));
  }, [metaAttempt]);

  useEffect(() => saveFilters(filters), [filters]);

  const toast = useCallback((text: string) => setToastText(text), []);
  useEffect(() => {
    if (!toastText) return;
    const t = window.setTimeout(() => setToastText(null), 3500);
    return () => window.clearTimeout(t);
  }, [toastText]);

  const locate = useCallback(async (): Promise<GeoPoint | null> => {
    setLocating(true);
    try {
      const p = await getPosition();
      setLocation(p);
      return p;
    } catch {
      return null;
    } finally {
      setLocating(false);
    }
  }, []);

  // «Рядом со мной» сохранён с прошлого раза — заново спросить координаты
  useEffect(() => {
    if (filters.nearMe && !location) {
      locate().then((p) => {
        if (!p) setFilters((f) => ({ ...f, nearMe: false }));
      });
    }
    // только при запуске
  }, []);

  const toggleNear = useCallback(async () => {
    haptic('select');
    if (filters.nearMe) {
      setFilters((f) => ({ ...f, nearMe: false }));
      return;
    }
    const p = location ?? (await locate());
    if (p) setFilters((f) => ({ ...f, nearMe: true }));
    else toast('Не удалось определить, где вы. Разрешите доступ к геопозиции и попробуйте снова.');
  }, [filters.nearMe, location, locate, toast]);

  // навигация
  const scrollPos = useRef<Record<Tab, number>>({ feed: 0, map: 0, subs: 0 });

  const openJob = useCallback(
    (job: Job) => {
      haptic('light');
      scrollPos.current[tab] = window.scrollY;
      try {
        history.pushState({ gigoDetail: job.id }, '');
      } catch {
        /* ignore */
      }
      setDetail({ id: job.id, job });
    },
    [tab],
  );

  const closeDetail = useCallback(() => {
    // карточка открыта из приложения — снимаем свою запись истории (popstate закроет карточку)
    if (history.state && history.state.gigoDetail != null) history.back();
    else {
      // открыта по ссылке ?job=…: убрать параметр, чтобы перезагрузка не открывала её снова
      try {
        const url = new URL(window.location.href);
        if (url.searchParams.has('job')) {
          url.searchParams.delete('job');
          history.replaceState(history.state, '', url.toString());
        }
      } catch {
        /* ignore */
      }
      setDetail(null);
    }
  }, []);

  const switchTab = (t: Tab) => {
    if (t === tab) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    haptic('select');
    scrollPos.current[tab] = window.scrollY;
    setVisited((v) => (v.has(t) ? v : new Set(v).add(t)));
    setTab(t);
  };

  // вернуть прокрутку при смене вкладки и закрытии карточки
  useLayoutEffect(() => {
    if (!detail) window.scrollTo(0, scrollPos.current[tab]);
  }, [tab, detail]);

  // Telegram BackButton в карточке
  useEffect(() => {
    if (!detail || !backButtonSupported || !tg) return;
    const bb = tg.BackButton;
    bb.onClick(closeDetail);
    bb.show();
    return () => {
      bb.offClick(closeDetail);
      bb.hide();
    };
  }, [detail, closeDetail]);

  // Системная кнопка «назад» браузера / Android тоже закрывает карточку
  useEffect(() => {
    const onPop = () => setDetail(null);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  if (!meta) {
    return (
      <div className="app">
        {metaError ? (
          <ErrorState text={metaError} onRetry={() => setMetaAttempt((a) => a + 1)} />
        ) : (
          <div className="center pad-xl">
            <Spinner />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="app">
      {detail && <JobDetail key={detail.id} jobId={detail.id} initial={detail.job} meta={meta} onBack={closeDetail} />}

      <div className="tabs" hidden={!!detail}>
        <div hidden={tab !== 'feed'}>
          <Feed
            meta={meta}
            filters={filters}
            location={location}
            locating={locating}
            onFiltersChange={setFilters}
            onToggleNear={toggleNear}
            onOpenJob={openJob}
            onSubscribed={() => setSubsVersion((v) => v + 1)}
            toast={toast}
          />
        </div>
        {visited.has('map') && (
          <div hidden={tab !== 'map'}>
            <MapView meta={meta} filters={filters} location={location} active={tab === 'map' && !detail} onOpenJob={openJob} />
          </div>
        )}
        {visited.has('subs') && (
          <div hidden={tab !== 'subs'}>
            <Subscriptions meta={meta} version={subsVersion} onGoFeed={() => switchTab('feed')} toast={toast} />
          </div>
        )}
        <TabBar tab={tab} onChange={switchTab} />
      </div>

      {toastText && (
        <div className="toast" role="status" onClick={() => setToastText(null)}>
          {toastText}
        </div>
      )}
    </div>
  );
}
