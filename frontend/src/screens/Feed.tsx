import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError, errorText, isAbort } from '../api';
import { FilterBar } from '../components/FilterBar';
import { Icon } from '../components/Icon';
import { JobCard, JobCardSkeleton } from '../components/JobCard';
import { LogoMark } from '../components/Logo';
import { EmptyState, ErrorState, Spinner } from '../components/States';
import { IconButton } from '../components/ui';
import { filtersToQuery, isEmptyFilter, subscriptionBody, EMPTY_FILTERS, type Filters } from '../filters';
import { plural } from '../format';
import { usePullToRefresh } from '../pullToRefresh';
import { haptic } from '../telegram';
import type { GeoPoint, Job, Meta } from '../types';

const PAGE = 30;

interface Props {
  meta: Meta;
  /** Вкладка видима (для «потяните, чтобы обновить»). */
  active: boolean;
  filters: Filters;
  location: GeoPoint | null;
  locating: boolean;
  /** Заявки, обновлённые в карточке (отклик): заменяют устаревшие из ленты. */
  patches: Record<number, Job>;
  onFiltersChange(f: Filters): void;
  onToggleNear(): void;
  onOpenJob(job: Job): void;
  toast(text: string): void;
  /** Навыки исполнителя из профиля: быстрый фильтр «Мои навыки». */
  skills: string[];
}

export function Feed({ meta, active, filters, location, locating, patches, onFiltersChange, onToggleNear, onOpenJob, toast, skills }: Props) {
  const [items, setItems] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [moreLoading, setMoreLoading] = useState(false);
  const [moreError, setMoreError] = useState(false);
  const [subscribing, setSubscribing] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  // фильтры, на которые уже подписались в этой сессии, чтобы не плодить дубли
  const [subscribedKeys, setSubscribedKeys] = useState<Set<string>>(() => new Set());
  const filterKey = JSON.stringify(filters);
  const alreadySubscribed = subscribedKeys.has(filterKey);

  // поиск: в запрос уходит через паузу в наборе, чтобы не дёргать сервер на каждую букву
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  useEffect(() => {
    const t = window.setTimeout(() => setQ(search.trim()), 350);
    return () => window.clearTimeout(t);
  }, [search]);
  const clearSearch = () => {
    setSearch('');
    setQ('');
  };

  const query = useMemo(() => ({ ...filtersToQuery(filters, location), ...(q ? { q } : {}) }), [filters, location, q]);
  const queryKey = JSON.stringify(query);
  const ctrl = useRef<AbortController | null>(null);
  // обновление без смены фильтра: список остаётся на экране, сверху — индикатор
  const soft = useRef(false);

  useEffect(() => {
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    const isSoft = soft.current && status === 'ready';
    soft.current = false;
    if (isSoft) setRefreshing(true);
    else setStatus('loading');
    setMoreError(false);
    api
      .jobs({ ...query, limit: PAGE, offset: 0 }, c.signal)
      .then((page) => {
        if (c.signal.aborted) return;
        setItems(page.items);
        setTotal(page.total);
        setStatus('ready');
      })
      .catch((e) => {
        if (isAbort(e) || c.signal.aborted) return;
        if (isSoft) toast(errorText(e));
        else {
          setError(errorText(e));
          setStatus('error');
        }
      })
      .finally(() => !c.signal.aborted && setRefreshing(false));
    return () => c.abort();
    // status читается только в момент запуска
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey, reloadKey]);

  const refresh = useCallback(() => {
    haptic('light');
    soft.current = true;
    setReloadKey((k) => k + 1);
  }, []);

  const { pull, ready: pullReady } = usePullToRefresh(refresh, active && status !== 'loading' && !refreshing);

  const loadMore = useCallback(() => {
    if (moreLoading || status !== 'ready' || items.length >= total) return;
    const c = ctrl.current;
    setMoreLoading(true);
    setMoreError(false);
    api
      .jobs({ ...query, limit: PAGE, offset: items.length }, c?.signal)
      .then((page) => {
        if (c?.signal.aborted) return;
        setItems((prev) => {
          const seen = new Set(prev.map((j) => j.id));
          return [...prev, ...page.items.filter((j) => !seen.has(j.id))];
        });
        setTotal(page.total);
      })
      .catch((e) => {
        if (!isAbort(e)) setMoreError(true);
      })
      .finally(() => setMoreLoading(false));
  }, [moreLoading, status, items.length, total, query]);

  // бесконечная прокрутка
  const sentinel = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = sentinel.current;
    if (!el || !('IntersectionObserver' in window)) return;
    const io = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && !moreError && loadMore(), {
      rootMargin: '400px 0px',
    });
    io.observe(el);
    return () => io.disconnect();
  }, [loadMore, moreError]);

  const subscribe = async () => {
    setSubscribing(true);
    try {
      await api.createSubscription(subscriptionBody(filters, meta, location));
      haptic('success');
      toast('Готово! Новые такие заявки пришлёт бот. Подписки — в профиле.');
      setSubscribedKeys((s) => new Set(s).add(filterKey));
    } catch (e) {
      haptic('error');
      toast(e instanceof ApiError && e.status === 409 ? 'Не больше 10 подписок. Удалите ненужную: Профиль → Подписки.' : errorText(e));
    } finally {
      setSubscribing(false);
    }
  };

  const catById = useMemo(() => new Map(meta.categories.map((c) => [c.id, c])), [meta]);
  const waitingLocation = filters.nearMe && !location;
  const showSkills = skills.length > 0 && !filters.categories.length;
  const skillLabels = skills.map((id) => catById.get(id)?.label ?? id).join(', ');
  const showPull = pull > 0 || refreshing;

  return (
    <div className="screen">
      <header className="feed-head feed-head--row">
        <div className="brand-title">
          <LogoMark size={30} />
          <h1 className="app-title">
            Подработка <span className="app-title__city">{meta.city.name}</span>
          </h1>
        </div>
        <IconButton icon="refresh" label="Обновить" onClick={refresh} disabled={status === 'loading' || refreshing} spin={refreshing} />
      </header>

      <div className="feed-sticky">
        <div className="feed-search">
          <Icon name="search" size={18} />
          <input
            className="input input--search"
            type="search"
            enterKeyHint="search"
            maxLength={100}
            placeholder="Поиск: склад, курьер, Таганская…"
            aria-label="Поиск заявок"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setQ(search.trim());
                (e.target as HTMLInputElement).blur();
              }
            }}
          />
          {search && (
            <button type="button" className="feed-search__clear" onClick={clearSearch} aria-label="Очистить поиск" title="Очистить поиск">
              <Icon name="x" size={16} />
            </button>
          )}
        </div>
        <FilterBar meta={meta} filters={filters} locating={locating} onChange={onFiltersChange} onToggleNear={onToggleNear} />
      </div>

      {showPull && (
        <div className="ptr" style={{ height: refreshing ? 44 : pull }} aria-hidden={!refreshing}>
          {refreshing ? (
            <Spinner />
          ) : (
            <span className={`ptr__icon${pullReady ? ' ptr__icon--ready' : ''}`} style={{ transform: `rotate(${pull * 3}deg)` }}>
              <Icon name="refresh" size={20} />
            </span>
          )}
        </div>
      )}

      <div className="results-bar">
        <span className="hint" aria-live="polite">
          {status === 'ready'
            ? `${total} ${plural(total, ['заявка', 'заявки', 'заявок'])}${filters.nearMe && location ? ' · ближе сверху' : ''}`
            : waitingLocation
              ? 'Ищем вас на карте…'
              : 'Загружаем…'}
        </span>
        {q ? null : alreadySubscribed ? (
          <span className="sub-done">
            <Icon name="bell-check" size={16} />
            Вы подписаны
          </span>
        ) : (
          <button type="button" className="sub-btn" onClick={subscribe} disabled={subscribing}>
            <Icon name="bell" size={16} />
            {subscribing ? 'Подписываем…' : isEmptyFilter(filters) ? 'Уведомлять о новых' : 'Уведомлять о таких'}
          </button>
        )}
      </div>

      {showSkills && (
        <div className="skills-hint">
          <button type="button" className="chip chip--ghost" onClick={() => onFiltersChange({ ...filters, categories: skills })}>
            <Icon name="zap" size={16} />
            Только мои навыки
          </button>
          <span className="hint small">{skillLabels}</span>
        </div>
      )}

      {status === 'loading' && (
        <div className="list">
          <JobCardSkeleton />
          <JobCardSkeleton />
          <JobCardSkeleton />
          <JobCardSkeleton />
        </div>
      )}

      {status === 'error' && <ErrorState text={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {status === 'ready' && items.length === 0 && q && (
        <EmptyState
          icon="search"
          title={`Ничего не нашли по «${q}»`}
          text={isEmptyFilter(filters) ? 'Попробуйте другое слово: название работы, метро или район.' : 'Попробуйте другое слово или сбросьте фильтр.'}
          action={
            <button type="button" className="btn btn--secondary" onClick={clearSearch}>
              <Icon name="x" size={18} />
              Очистить поиск
            </button>
          }
        />
      )}

      {status === 'ready' && items.length === 0 && !q && (
        <EmptyState
          icon="search"
          title={isEmptyFilter(filters) ? 'Пока заявок нет' : 'Под фильтр ничего нет'}
          text={
            isEmptyFilter(filters)
              ? 'Загляните чуть позже или включите уведомления — бот пришлёт новые заявки.'
              : 'Попробуйте смягчить фильтр или включите уведомления: бот пришлёт, когда появится подходящая заявка.'
          }
          action={
            !isEmptyFilter(filters) ? (
              <button type="button" className="btn btn--secondary" onClick={() => onFiltersChange(EMPTY_FILTERS)}>
                <Icon name="x" size={18} />
                Сбросить фильтр
              </button>
            ) : (
              <button type="button" className="btn btn--secondary" onClick={refresh}>
                <Icon name="refresh" size={18} />
                Обновить
              </button>
            )
          }
        />
      )}

      {status === 'ready' && items.length > 0 && (
        <div className="list">
          {items.map((j) => (
            <JobCard key={j.id} job={patches[j.id] ?? j} category={catById.get(j.category)} onOpen={onOpenJob} />
          ))}
          <div ref={sentinel} />
          {items.length < total && (
            <div className="more">
              {moreLoading ? (
                <Spinner />
              ) : (
                <button type="button" className="btn btn--secondary btn--wide" onClick={loadMore}>
                  {moreError ? 'Не загрузилось. Ещё раз' : 'Показать ещё'}
                </button>
              )}
            </div>
          )}
          {items.length >= total && total > 3 && <div className="hint center pad small">Это все заявки. Потяните вниз, чтобы обновить.</div>}
        </div>
      )}
    </div>
  );
}
