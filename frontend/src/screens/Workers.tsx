import { useEffect, useRef, useState } from 'react';
import { api, errorText, isAbort } from '../api';
import { Icon, categoryIcon } from '../components/Icon';
import { EmptyState, ErrorState, Spinner } from '../components/States';
import { Avatar, RatingText, SkillChips } from '../components/ui';
import { plural } from '../format';
import { haptic } from '../telegram';
import type { Meta, WorkerCard } from '../types';

const PAGE = 30;

interface Props {
  meta: Meta;
  active: boolean;
  onOpenUser(id: number): void;
}

/** Каталог исполнителей для заказчика: навыки, рейтинг, «О себе». Из профиля можно пригласить на заявку. */
export function Workers({ meta, active, onOpenUser }: Props) {
  const [category, setCategory] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  const [items, setItems] = useState<WorkerCard[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [more, setMore] = useState(false);
  const [moreError, setMoreError] = useState(false);
  const ctrl = useRef<AbortController | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setQ(search.trim()), 350);
    return () => window.clearTimeout(t);
  }, [search]);

  useEffect(() => {
    if (!active) return;
    ctrl.current?.abort();
    const c = new AbortController();
    ctrl.current = c;
    setStatus((s) => (s === 'ready' && !category && !q ? s : 'loading'));
    setMoreError(false);
    api
      .workers({ category, q, limit: PAGE }, c.signal)
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
  }, [active, category, q, attempt]);

  const loadMore = () => {
    // тот же контроллер, что у первой страницы: сменили фильтр — старая догрузка не допишется в новый список
    const c = ctrl.current;
    setMore(true);
    setMoreError(false);
    api
      .workers({ category, q, limit: PAGE, offset: items.length }, c?.signal)
      .then((page) => {
        if (c?.signal.aborted) return;
        setItems((prev) => [...prev, ...page.items.filter((w) => !prev.some((x) => x.id === w.id))]);
        setTotal(page.total);
      })
      .catch((e) => {
        if (!isAbort(e) && !c?.signal.aborted) setMoreError(true);
      })
      .finally(() => setMore(false));
  };

  const pick = (id: string | null) => {
    haptic('select');
    setCategory((c) => (c === id ? null : id));
  };

  return (
    <div className="screen">
      <header className="feed-head">
        <h1 className="app-title">Исполнители</h1>
        <p className="hint lead">Откройте профиль и пригласите на свою заявку: бот пришлёт человеку ссылку на неё.</p>
      </header>

      <div className="feed-sticky">
        <div className="feed-search">
          <Icon name="search" size={18} />
          <input
            className="input input--search"
            type="search"
            enterKeyHint="search"
            maxLength={100}
            placeholder="Имя или опыт: права, свой инструмент…"
            aria-label="Поиск исполнителей"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button type="button" className="feed-search__clear" onClick={() => setSearch('')} aria-label="Очистить поиск" title="Очистить поиск">
              <Icon name="x" size={16} />
            </button>
          )}
        </div>
        <div className="filters">
          <div className="chips chips--scroll" role="radiogroup" aria-label="Навык">
            <button type="button" role="radio" aria-checked={!category} className={`chip${!category ? ' chip--on' : ''}`} onClick={() => pick(null)}>
              Все
            </button>
            {meta.categories.map((c) => (
              <button
                key={c.id}
                type="button"
                role="radio"
                aria-checked={category === c.id}
                className={`chip${category === c.id ? ' chip--on' : ''}`}
                onClick={() => pick(c.id)}
              >
                <Icon name={categoryIcon(c.id)} size={16} />
                {c.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="results-bar">
        <span className="hint" aria-live="polite">
          {status === 'ready' ? `${total} ${plural(total, ['исполнитель', 'исполнителя', 'исполнителей'])}` : 'Загружаем…'}
        </span>
      </div>

      {status === 'loading' && (
        <div className="center pad-xl">
          <Spinner />
        </div>
      )}
      {status === 'error' && <ErrorState text={error} onRetry={() => setAttempt((a) => a + 1)} />}
      {status === 'ready' && items.length === 0 && (
        <EmptyState
          icon="users"
          title={category || q ? 'Никого не нашли' : 'Каталог пока пуст'}
          text={
            category || q
              ? 'Попробуйте другой навык или слово. Или создайте заявку: исполнители сами откликнутся.'
              : 'Здесь появятся исполнители, которые заполнили профиль. А пока создайте заявку: исполнители откликнутся сами.'
          }
        />
      )}
      {status === 'ready' && items.length > 0 && (
        <div className="list">
          {items.map((w) => (
            <button key={w.id} type="button" className="worker-card" onClick={() => onOpenUser(w.id)}>
              <div className="worker-card__top">
                <Avatar name={w.first_name} size={44} />
                <span className="worker-card__text">
                  <span className="user-row__name">{w.first_name}</span>
                  <span className="hint small">
                    <RatingText rating={w.rating} count={w.reviews_count} />
                    {w.jobs_count ? ` · ${w.jobs_count} ${plural(w.jobs_count, ['работа', 'работы', 'работ'])} в Gigo` : ''}
                  </span>
                </span>
                <Icon name="chevron-right" size={20} className="user-row__chev" />
              </div>
              {w.skills.length > 0 && <SkillChips ids={w.skills} meta={meta} highlight={category ?? undefined} />}
              {w.about && <p className="worker-card__about">{w.about}</p>}
            </button>
          ))}
          {items.length < total && (
            <div className="more">
              {more ? (
                <Spinner />
              ) : (
                <button type="button" className="btn btn--secondary btn--wide" onClick={loadMore}>
                  {moreError ? 'Не загрузилось. Ещё раз' : 'Показать ещё'}
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
