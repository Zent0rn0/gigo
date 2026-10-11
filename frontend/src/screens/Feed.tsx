import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError, errorText, isAbort } from '../api';
import { FilterBar } from '../components/FilterBar';
import { JobCard, JobCardSkeleton } from '../components/JobCard';
import { EmptyState, ErrorState, Spinner } from '../components/States';
import { filtersToQuery, isEmptyFilter, subscriptionBody, EMPTY_FILTERS, type Filters } from '../filters';
import { plural } from '../format';
import { haptic } from '../telegram';
import type { GeoPoint, Job, Meta } from '../types';

const PAGE = 30;

interface Props {
  meta: Meta;
  filters: Filters;
  location: GeoPoint | null;
  locating: boolean;
  onFiltersChange(f: Filters): void;
  onToggleNear(): void;
  onOpenJob(job: Job): void;
  onSubscribed(): void;
  toast(text: string): void;
}

export function Feed({ meta, filters, location, locating, onFiltersChange, onToggleNear, onOpenJob, onSubscribed, toast }: Props) {
  const [items, setItems] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [moreLoading, setMoreLoading] = useState(false);
  const [moreError, setMoreError] = useState(false);
  const [subscribing, setSubscribing] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  // фильтры, на которые уже подписались в этой сессии, чтобы не плодить дубли
  const [subscribedKeys, setSubscribedKeys] = useState<Set<string>>(() => new Set());
  const filterKey = JSON.stringify(filters);
  const alreadySubscribed = subscribedKeys.has(filterKey);

  const query = useMemo(() => filtersToQuery(filters, location), [filters, location]);
  const queryKey = JSON.stringify(query);
  const ctrl = useRef<AbortController | null>(null);

  useEffect(() => {
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    setStatus('loading');
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
        setError(errorText(e));
        setStatus('error');
      });
    return () => c.abort();
  }, [queryKey, reloadKey]);

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
      toast('Готово! Новые заказы по этому фильтру пришлёт бот.');
      setSubscribedKeys((s) => new Set(s).add(filterKey));
      onSubscribed();
    } catch (e) {
      haptic('error');
      toast(e instanceof ApiError && e.status === 409 ? 'Не больше 10 подписок. Удалите ненужную во вкладке «Подписки».' : errorText(e));
    } finally {
      setSubscribing(false);
    }
  };

  const catById = useMemo(() => new Map(meta.categories.map((c) => [c.id, c])), [meta]);
  const waitingLocation = filters.nearMe && !location;

  return (
    <div className="screen">
      <header className="feed-head">
        <h1 className="app-title">
          Подработка <span className="app-title__city">· {meta.city.name}</span>
        </h1>
      </header>

      <FilterBar meta={meta} filters={filters} locating={locating} onChange={onFiltersChange} onToggleNear={onToggleNear} />

      <div className="results-bar">
        <span className="hint">
          {status === 'ready' ? `${total} ${plural(total, ['заказ', 'заказа', 'заказов'])}` : waitingLocation ? 'Ищем вас на карте…' : 'Загружаем…'}
          {filters.nearMe && location && status === 'ready' ? ' · ближе сверху' : ''}
        </span>
        {alreadySubscribed ? (
          <span className="hint">✓ Вы подписаны</span>
        ) : (
          <button type="button" className="link-btn" onClick={subscribe} disabled={subscribing}>
            🔔 {subscribing ? 'Подписываем…' : 'Подписаться на этот фильтр'}
          </button>
        )}
      </div>

      {status === 'loading' && (
        <div className="list">
          <JobCardSkeleton />
          <JobCardSkeleton />
          <JobCardSkeleton />
          <JobCardSkeleton />
        </div>
      )}

      {status === 'error' && <ErrorState text={error} onRetry={() => setReloadKey((k) => k + 1)} />}

      {status === 'ready' && items.length === 0 && (
        <EmptyState
          icon="🔍"
          title="Заказов не нашлось"
          text={
            isEmptyFilter(filters)
              ? 'Сейчас нет активных заказов. Загляните чуть позже или подпишитесь — бот пришлёт новые.'
              : 'Попробуйте смягчить фильтр или подпишитесь: бот пришлёт, когда появится подходящий заказ.'
          }
          action={
            !isEmptyFilter(filters) && (
              <button type="button" className="btn btn--secondary" onClick={() => onFiltersChange(EMPTY_FILTERS)}>
                Сбросить фильтр
              </button>
            )
          }
        />
      )}

      {status === 'ready' && items.length > 0 && (
        <div className="list">
          {items.map((j) => (
            <JobCard key={j.id} job={j} category={catById.get(j.category)} onOpen={onOpenJob} />
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
          {items.length >= total && total > PAGE && <div className="hint center pad">Это все заказы</div>}
        </div>
      )}
    </div>
  );
}
