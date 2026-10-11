import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { api, errorText, onBlocked } from './api';
import { ROLE_TABS, TabBar, type Tab } from './components/TabBar';
import { EmptyState, ErrorState, Spinner } from './components/States';
import { LogoMark } from './components/Logo';
import { loadFilters, saveFilters, type Filters } from './filters';
import { getPosition } from './geo';
import { CreateJob } from './screens/CreateJob';
import { Feed } from './screens/Feed';
import { JobDetail } from './screens/JobDetail';
import { MapView } from './screens/MapView';
import { MyJobs } from './screens/MyJobs';
import { MyResponses } from './screens/MyResponses';
import { Onboarding } from './screens/Onboarding';
import { Profile } from './screens/Profile';
import { Subscriptions } from './screens/Subscriptions';
import { UserProfile } from './screens/UserProfile';
import { backButtonSupported, deepLinkJobId, deepLinkTab, haptic, tg } from './telegram';
import type { GeoPoint, Job, Me, Meta, Role } from './types';

/** Экраны поверх вкладок: карточка заявки, профиль человека, подписки. */
type OverlayInit = { kind: 'job'; id: number; job: Job | null } | { kind: 'user'; id: number } | { kind: 'subs' };
type Overlay = OverlayInit & { key: number; pushed: boolean };

function initialTab(role: Role): Tab {
  const t = deepLinkTab();
  return t && ROLE_TABS[role].includes(t) ? t : ROLE_TABS[role][0];
}

/** Подсказка, если ссылка из бота ведёт во вкладку другой роли. */
const WRONG_ROLE_TAB: Record<string, string> = {
  responses: 'Отклики видны в роли исполнителя. Сменить роль можно в профиле.',
  my: 'Мои заявки видны в роли заказчика. Сменить роль можно в профиле.',
  create: 'Создавать заявки может заказчик. Сменить роль можно в профиле.',
};

function dropQuery(...keys: string[]) {
  try {
    const url = new URL(window.location.href);
    let changed = false;
    for (const k of keys)
      if (url.searchParams.has(k)) {
        url.searchParams.delete(k);
        changed = true;
      }
    if (changed) history.replaceState(history.state, '', url.toString());
  } catch {
    /* ignore */
  }
}

export function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [bootError, setBootError] = useState('');
  const [bootAttempt, setBootAttempt] = useState(0);
  const [blocked, setBlocked] = useState<string | null>(null);
  useEffect(() => onBlocked(setBlocked), []);

  const [tab, setTab] = useState<Tab>('feed');
  const [visited, setVisited] = useState<Set<Tab>>(() => new Set<Tab>());
  const [stack, setStack] = useState<Overlay[]>(() => {
    const id = deepLinkJobId();
    return id != null ? [{ kind: 'job', id, job: null, key: 0, pushed: false }] : [];
  });
  const stackRef = useRef(stack);
  stackRef.current = stack;
  const keySeq = useRef(1);

  const [version, setVersion] = useState(0);
  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const [patches, setPatches] = useState<Record<number, Job>>({});

  const [filters, setFilters] = useState<Filters>(loadFilters);
  const [location, setLocation] = useState<GeoPoint | null>(null);
  const [locating, setLocating] = useState(false);
  const [toastText, setToastText] = useState<string | null>(null);

  const toast = useCallback((text: string) => setToastText(text), []);
  useEffect(() => {
    if (!toastText) return;
    const t = window.setTimeout(() => setToastText(null), 3500);
    return () => window.clearTimeout(t);
  }, [toastText]);

  const enterRole = useCallback((role: Role, first: boolean) => {
    const t = first ? initialTab(role) : ROLE_TABS[role][0];
    setTab(t);
    setVisited(new Set<Tab>([t]));
  }, []);

  // справочники и текущий пользователь
  useEffect(() => {
    setBootError('');
    Promise.all([api.meta(), api.me()])
      .then(([m, u]) => {
        setMeta(m);
        setMe(u);
        if (u.role) {
          enterRole(u.role, true);
          const t = deepLinkTab();
          if (t && !ROLE_TABS[u.role].includes(t) && WRONG_ROLE_TAB[t]) toast(WRONG_ROLE_TAB[t]);
        }
      })
      .catch((e) => setBootError(errorText(e)));
  }, [bootAttempt, enterRole, toast]);

  useEffect(() => saveFilters(filters), [filters]);

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

  // ——— навигация ———
  const tabScroll = useRef<Partial<Record<Tab, number>>>({});
  const overlayScroll = useRef<number[]>([]);

  const push = useCallback((o: OverlayInit, restoreY?: number) => {
    haptic('light');
    const cur = stackRef.current;
    overlayScroll.current[cur.length] = restoreY ?? window.scrollY;
    const depth = cur.filter((x) => x.pushed).length + 1;
    let pushed = false;
    try {
      history.pushState({ gigoDepth: depth }, '');
      pushed = true;
    } catch {
      /* ignore */
    }
    setStack((s) => [...s, { ...o, key: keySeq.current++, pushed }]);
  }, []);

  const pop = useCallback(() => {
    const cur = stackRef.current;
    const top = cur[cur.length - 1];
    if (!top) return;
    if (top.pushed && history.state && history.state.gigoDepth != null) {
      history.back(); // popstate снимет экран
    } else {
      // открыт по ссылке ?job=…: убрать параметр, чтобы перезагрузка не открывала его снова
      dropQuery('job');
      setStack((s) => s.slice(0, -1));
    }
  }, []);

  // системная «назад» в браузере / Android
  useEffect(() => {
    const onPop = () => {
      const d = (history.state && history.state.gigoDepth) || 0;
      setStack((s) => {
        let n = 0;
        const out: Overlay[] = [];
        for (const x of s) {
          if (x.pushed && ++n > d) break;
          out.push(x);
        }
        return out.length === s.length ? s : out;
      });
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // вернуть прокрутку, когда закрыли экран поверх
  const prevLen = useRef(stack.length);
  useLayoutEffect(() => {
    if (stack.length < prevLen.current) {
      const y = overlayScroll.current[stack.length];
      overlayScroll.current.length = stack.length;
      window.scrollTo(0, y ?? 0);
    }
    prevLen.current = stack.length;
  }, [stack.length]);

  // Telegram BackButton
  const hasOverlay = stack.length > 0;
  useEffect(() => {
    if (!hasOverlay || !backButtonSupported || !tg) return;
    const bb = tg.BackButton;
    bb.onClick(pop);
    bb.show();
    return () => {
      bb.offClick(pop);
      bb.hide();
    };
  }, [hasOverlay, pop]);

  const switchTab = useCallback(
    (t: Tab) => {
      if (t === tab) {
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      haptic('select');
      tabScroll.current[tab] = window.scrollY;
      dropQuery('tab');
      setVisited((v) => (v.has(t) ? v : new Set(v).add(t)));
      setTab(t);
    },
    [tab],
  );

  useLayoutEffect(() => {
    if (!stackRef.current.length) window.scrollTo(0, tabScroll.current[tab] ?? 0);
  }, [tab]);

  const openJob = useCallback((job: Job) => push({ kind: 'job', id: job.id, job }), [push]);
  const openUser = useCallback((id: number) => push({ kind: 'user', id }), [push]);
  const openSubs = useCallback(() => push({ kind: 'subs' }), [push]);
  const onJobUpdated = useCallback((job: Job) => setPatches((p) => (p[job.id] === job ? p : { ...p, [job.id]: job })), []);

  const switchRole = useCallback(
    async (role: Role) => {
      try {
        const upd = await api.updateMe({ role });
        haptic('success');
        setMe(upd);
        enterRole(role, false);
        toast(role === 'worker' ? 'Теперь вы исполнитель: смотрите заявки и откликайтесь' : 'Теперь вы заказчик: создайте заявку');
      } catch (e) {
        haptic('error');
        toast(errorText(e));
      }
    },
    [enterRole, toast],
  );

  const toastEl = toastText && (
    <div className={`toast${hasOverlay ? ' toast--low' : ''}`} role="status" onClick={() => setToastText(null)}>
      {toastText}
    </div>
  );

  if (blocked) {
    return (
      <div className="app blocked" role="alert">
        <EmptyState
          icon="ban"
          tone="danger"
          title="Доступ ограничен"
          text={
            <>
              {blocked}
              <br />
              <br />
              Если считаете, что это ошибка, напишите об этом боту Gigo в чате.
            </>
          }
        />
      </div>
    );
  }

  if (!meta || !me) {
    return (
      <div className="app">
        {bootError ? (
          <ErrorState text={bootError} onRetry={() => setBootAttempt((a) => a + 1)} />
        ) : (
          <div className="boot">
            <LogoMark size={64} />
            <Spinner />
          </div>
        )}
      </div>
    );
  }

  if (!me.role) {
    return (
      <div className="app">
        <Onboarding
          me={me}
          city={meta.city.name}
          onDone={(u) => {
            setMe(u);
            if (u.role) enterRole(u.role, true);
          }}
        />
        {toastEl}
      </div>
    );
  }

  const role = me.role;
  const tabs = ROLE_TABS[role];
  const shown = (t: Tab) => tabs.includes(t) && visited.has(t);
  const on = (t: Tab) => tab === t && !hasOverlay;

  return (
    <div className="app">
      {stack.map((o, i) => {
        const top = i === stack.length - 1;
        return (
          <div key={o.key} className="layer" hidden={!top}>
            {o.kind === 'job' && (
              <JobDetail
                jobId={o.id}
                initial={o.job}
                meta={meta}
                me={me}
                active={top}
                onBack={pop}
                onOpenUser={openUser}
                onSwitchRole={switchRole}
                onChanged={bump}
                onJobUpdated={onJobUpdated}
                toast={toast}
              />
            )}
            {o.kind === 'user' && <UserProfile userId={o.id} isMe={o.id === me.id} onBack={pop} />}
            {o.kind === 'subs' && (
              <Subscriptions
                meta={meta}
                onBack={pop}
                onGoFeed={() => {
                  pop();
                  switchTab('feed');
                }}
                toast={toast}
              />
            )}
          </div>
        );
      })}

      <div className="tabs" hidden={hasOverlay}>
        {shown('feed') && (
          <div className="pane" hidden={tab !== 'feed'}>
            <Feed
              meta={meta}
              active={on('feed')}
              filters={filters}
              location={location}
              locating={locating}
              patches={patches}
              onFiltersChange={setFilters}
              onToggleNear={toggleNear}
              onOpenJob={openJob}
              toast={toast}
            />
          </div>
        )}
        {shown('map') && (
          <div className="pane" hidden={tab !== 'map'}>
            <MapView meta={meta} filters={filters} location={location} active={on('map')} onOpenJob={openJob} />
          </div>
        )}
        {shown('responses') && (
          <div className="pane" hidden={tab !== 'responses'}>
            <MyResponses
              meta={meta}
              active={on('responses')}
              version={version}
              onOpenJob={openJob}
              onGoFeed={() => switchTab('feed')}
              onChanged={bump}
              toast={toast}
            />
          </div>
        )}
        {shown('my') && (
          <div className="pane" hidden={tab !== 'my'}>
            <MyJobs meta={meta} active={on('my')} version={version} onOpenJob={openJob} onCreate={() => switchTab('create')} />
          </div>
        )}
        {shown('create') && (
          <div className="pane" hidden={tab !== 'create'}>
            <CreateJob
              meta={meta}
              me={me}
              active={on('create')}
              toast={toast}
              onCreated={(job) => {
                bump();
                tabScroll.current.create = 0;
                switchTab('my');
                push({ kind: 'job', id: job.id, job }, 0);
              }}
            />
          </div>
        )}
        {shown('profile') && (
          <div className="pane" hidden={tab !== 'profile'}>
            <Profile me={me} onMeChange={setMe} onSwitchRole={switchRole} onOpenUser={openUser} onOpenSubs={openSubs} toast={toast} />
          </div>
        )}
        <TabBar tabs={tabs} tab={tab} onChange={switchTab} />
      </div>

      {toastEl}
    </div>
  );
}
