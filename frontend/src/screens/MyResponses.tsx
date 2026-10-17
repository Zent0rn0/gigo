import { useEffect, useMemo, useState } from 'react';
import { api, errorText } from '../api';
import { JobCard, JobCardSkeleton } from '../components/JobCard';
import { Icon } from '../components/Icon';
import { ReviewSheet, type ReviewTarget } from '../components/ReviewSheet';
import { EmptyState, ErrorState } from '../components/States';
import { ContactButton, StatusChip } from '../components/ui';
import { RESPONSE_LABEL_WORKER, RESPONSE_TONE } from '../format';
import { jobState } from '../format';
import { t } from '../i18n';
import { haptic } from '../telegram';
import type { Job, Meta, MyResponse } from '../types';

interface Props {
  meta: Meta;
  /** Вкладка видима: при каждом показе список обновляется. */
  active: boolean;
  version: number;
  onOpenJob(job: Job): void;
  onGoFeed(): void;
  onChanged(): void;
  toast(text: string): void;
}

export function MyResponses({ meta, active, version, onOpenJob, onGoFeed, onChanged, toast }: Props) {
  const [items, setItems] = useState<MyResponse[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [view, setView] = useState<'responses' | 'saved'>('responses');
  const [saved, setSaved] = useState<Job[] | null>(null);
  const [savedError, setSavedError] = useState('');

  useEffect(() => {
    if (!active || view !== 'saved') return;
    let alive = true;
    setSavedError('');
    api
      .savedJobs()
      .then((list) => alive && setSaved(list))
      .catch((e) => alive && setSavedError(errorText(e)));
    return () => {
      alive = false;
    };
  }, [active, view, version, attempt]);

  const unsave = async (job: Job) => {
    setSaved((l) => l?.filter((j) => j.id !== job.id) ?? l);
    try {
      await api.setSaved(job.id, false);
      haptic('light');
      onChanged();
    } catch (e) {
      setSaved((l) => (l ? [job, ...l] : l));
      toast(errorText(e));
    }
  };

  useEffect(() => {
    if (!active) return;
    let alive = true;
    setStatus((s) => (s === 'ready' ? s : 'loading'));
    api
      .myResponses()
      .then((list) => {
        if (!alive) return;
        setItems(list);
        setStatus('ready');
      })
      .catch((e) => {
        if (!alive) return;
        setError(errorText(e));
        setStatus('error');
      });
    return () => {
      alive = false;
    };
  }, [active, version, attempt]);

  const catById = useMemo(() => new Map(meta.categories.map((c) => [c.id, c])), [meta]);
  const accepted = items.filter((r) => r.status === 'accepted').length;
  // сначала «Вас выбрали», потом ждущие ответа, потом остальные
  const ORDER = { accepted: 0, pending: 1, rejected: 2, withdrawn: 3 } as const;
  const sorted = items
    .map((r, i) => ({ r, i }))
    .sort((a, b) => ORDER[a.r.status] - ORDER[b.r.status] || a.i - b.i)
    .map((x) => x.r);

  return (
    <div className="screen">
      <header className="feed-head">
        <h1 className="app-title">{t('Отклики')}</h1>
        <p className="hint lead">
          {status === 'ready' && items.length
            ? accepted
              ? accepted === 1
                ? t('Вас выбрали в {n} заявке. Напишите заказчику.', { n: accepted })
                : t('Вас выбрали в {n} заявках. Напишите заказчику.', { n: accepted })
              : t('Ответ заказчика придёт сообщением от бота.')
            : t('Здесь заявки, на которые вы откликнулись.')}
        </p>
        <div className="segmented segmented--tabs" role="tablist" aria-label={t('Что показать')}>
          {(
            [
              ['responses', t('Отклики'), 'inbox'],
              ['saved', t('Избранное'), 'bookmark'],
            ] as const
          ).map(([id, label, icon]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={view === id}
              className={`segmented__item${view === id ? ' segmented__item--on' : ''}`}
              onClick={() => {
                haptic('select');
                setView(id);
              }}
            >
              <Icon name={icon} size={17} />
              {label}
              {id === 'saved' && saved?.length ? <span className="segmented__count">{saved.length}</span> : null}
            </button>
          ))}
        </div>
      </header>

      {view === 'saved' && (
        <>
          {savedError && <ErrorState text={savedError} onRetry={() => setAttempt((a) => a + 1)} />}
          {!savedError && saved == null && (
            <div className="list">
              <JobCardSkeleton />
            </div>
          )}
          {!savedError && saved?.length === 0 && (
            <EmptyState
              icon="bookmark"
              title={t('В избранном пусто')}
              text={t('Откройте заявку и нажмите закладку вверху, чтобы вернуться к ней позже.')}
              action={
                <button type="button" className="btn btn--secondary" onClick={onGoFeed}>
                  <Icon name="feed" size={18} />
                  {t('Открыть ленту')}
                </button>
              }
            />
          )}
          {!savedError && !!saved?.length && (
            <div className="list">
              {saved.map((j) => {
                const open = jobState(j) === 'open';
                return (
                  <div key={j.id} className={open ? undefined : 'dim'}>
                    <JobCard job={j} category={catById.get(j.category)} onOpen={onOpenJob} />
                    <div className="card-actions">
                      {!open && <span className="hint small">{t('Набор закрыт')}</span>}
                      <button type="button" className="btn btn--sm btn--secondary" onClick={() => unsave(j)}>
                        <Icon name="x" size={16} />
                        {t('Убрать')}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {view === 'responses' && status === 'loading' && (
        <div className="list">
          <JobCardSkeleton />
          <JobCardSkeleton />
        </div>
      )}
      {view === 'responses' && status === 'error' && <ErrorState text={error} onRetry={() => setAttempt((a) => a + 1)} />}

      {view === 'responses' && status === 'ready' && items.length === 0 && (
        <EmptyState
          icon="inbox"
          tone="brand"
          title={t('Откликов пока нет')}
          text={t('Найдите подходящую заявку в ленте и нажмите «Откликнуться».')}
          action={
            <button type="button" className="btn btn--primary" onClick={onGoFeed}>
              <Icon name="feed" size={18} />
              {t('Открыть ленту')}
            </button>
          }
        />
      )}

      {view === 'responses' && status === 'ready' && items.length > 0 && (
        <div className="list">
          {sorted.map((r) => (
            <div
              key={r.id}
              className={r.status === 'accepted' ? 'stack-card stack-card--ok' : r.status === 'rejected' || r.status === 'withdrawn' ? 'dim' : undefined}
            >
              <JobCard
                job={r.job}
                category={catById.get(r.job.category)}
                onOpen={onOpenJob}
                footer={
                  <div className="job-card__foot">
                    <StatusChip tone={RESPONSE_TONE[r.status]}>{t(RESPONSE_LABEL_WORKER[r.status])}</StatusChip>
                    <span className="hint small job-card__who">{r.job.employer.first_name}</span>
                  </div>
                }
              />
              {r.status === 'accepted' && (
                <div className="card-actions">
                  {r.contact && <ContactButton contact={r.contact} />}
                  <button
                    type="button"
                    className="btn btn--sm btn--secondary"
                    onClick={() => setReview({ responseId: r.id, name: r.job.employer.first_name, jobTitle: r.job.title, initial: r.my_review })}
                  >
                    <Icon name="star" size={16} filled={!!r.my_review} />
                    {r.my_review ? t('Ваш отзыв: {rating}', { rating: r.my_review.rating }) : t('Оставить отзыв')}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {review && (
        <ReviewSheet
          target={review}
          onClose={() => setReview(null)}
          onSaved={(rv) => {
            setItems((l) => l.map((x) => (x.id === review.responseId ? { ...x, my_review: rv } : x)));
            setReview(null);
            toast(t('Спасибо за отзыв!'));
            onChanged();
          }}
        />
      )}
    </div>
  );
}
