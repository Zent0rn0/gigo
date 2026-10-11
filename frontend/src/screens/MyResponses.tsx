import { useEffect, useMemo, useState } from 'react';
import { api, errorText } from '../api';
import { JobCard, JobCardSkeleton } from '../components/JobCard';
import { Icon } from '../components/Icon';
import { ReviewSheet, type ReviewTarget } from '../components/ReviewSheet';
import { EmptyState, ErrorState } from '../components/States';
import { ContactButton, StatusChip } from '../components/ui';
import { RESPONSE_LABEL_WORKER, RESPONSE_TONE } from '../format';
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
        <h1 className="app-title">Отклики</h1>
        <p className="hint lead">
          {status === 'ready' && items.length
            ? accepted
              ? `Вас выбрали в ${accepted} ${accepted === 1 ? 'заявке' : 'заявках'}. Напишите заказчику.`
              : 'Ответ заказчика придёт сообщением от бота.'
            : 'Здесь заявки, на которые вы откликнулись.'}
        </p>
      </header>

      {status === 'loading' && (
        <div className="list">
          <JobCardSkeleton />
          <JobCardSkeleton />
        </div>
      )}
      {status === 'error' && <ErrorState text={error} onRetry={() => setAttempt((a) => a + 1)} />}

      {status === 'ready' && items.length === 0 && (
        <EmptyState
          icon="inbox"
          tone="brand"
          title="Откликов пока нет"
          text="Найдите подходящую заявку в ленте и нажмите «Откликнуться»."
          action={
            <button type="button" className="btn btn--primary" onClick={onGoFeed}>
              <Icon name="feed" size={18} />
              Открыть ленту
            </button>
          }
        />
      )}

      {status === 'ready' && items.length > 0 && (
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
                    <StatusChip tone={RESPONSE_TONE[r.status]}>{RESPONSE_LABEL_WORKER[r.status]}</StatusChip>
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
                    {r.my_review ? `Ваш отзыв: ${r.my_review.rating}` : 'Оставить отзыв'}
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
            toast('Спасибо за отзыв!');
            onChanged();
          }}
        />
      )}
    </div>
  );
}
