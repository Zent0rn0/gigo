import { useEffect, useMemo, useState } from 'react';
import { api, errorText } from '../api';
import { JobCard, JobCardSkeleton } from '../components/JobCard';
import { EmptyState, ErrorState } from '../components/States';
import { jobState } from '../format';
import type { Job, Meta } from '../types';

interface Props {
  meta: Meta;
  active: boolean;
  version: number;
  onOpenJob(job: Job): void;
  onCreate(): void;
}

export function MyJobs({ meta, active, version, onOpenJob, onCreate }: Props) {
  const [items, setItems] = useState<Job[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!active) return;
    let alive = true;
    setStatus((s) => (s === 'ready' ? s : 'loading'));
    api
      .myJobs()
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
  const open = items.filter((j) => jobState(j) === 'open');
  const past = items.filter((j) => jobState(j) !== 'open');
  const pending = items.reduce((n, j) => n + (j.pending_count ?? 0), 0);

  return (
    <div className="screen">
      <header className="feed-head feed-head--row">
        <div>
          <h1 className="app-title">Мои заявки</h1>
          <p className="hint lead">{pending ? `Ждут ответа: ${pending}` : 'Отклики придут сообщением от бота.'}</p>
        </div>
        {items.length > 0 && (
          <button type="button" className="btn btn--primary btn--sm" onClick={onCreate}>
            + Новая
          </button>
        )}
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
          icon="📝"
          title="Заявок пока нет"
          text="Опишите задачу и оплату — исполнители откликнутся, а вы выберете подходящих."
          action={
            <button type="button" className="btn btn--primary" onClick={onCreate}>
              Создать заявку
            </button>
          }
        />
      )}

      {status === 'ready' && open.length > 0 && (
        <div className="list">
          {open.map((j) => (
            <JobCard key={j.id} job={j} category={catById.get(j.category)} onOpen={onOpenJob} owner />
          ))}
        </div>
      )}
      {status === 'ready' && past.length > 0 && (
        <>
          <h2 className="list-title">Завершённые</h2>
          <div className="list dim">
            {past.map((j) => (
              <JobCard key={j.id} job={j} category={catById.get(j.category)} onOpen={onOpenJob} owner />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
