import { useEffect, useMemo, useState } from 'react';
import { api, errorText } from '../api';
import { JobCard, JobCardSkeleton } from '../components/JobCard';
import { EmptyState, ErrorState } from '../components/States';
import { Icon } from '../components/Icon';
import { jobState, plural } from '../format';
import { t } from '../i18n';
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
  // открытые: сначала с новыми откликами (больше — выше), потом остальные в прежнем порядке
  const open = items
    .filter((j) => jobState(j) === 'open')
    .map((j, i) => ({ j, i }))
    .sort((a, b) => (b.j.pending_count ?? 0) - (a.j.pending_count ?? 0) || a.i - b.i)
    .map((x) => x.j);
  const past = items.filter((j) => jobState(j) !== 'open');
  const pending = items.reduce((n, j) => n + (j.pending_count ?? 0), 0);
  const stats = [
    { value: open.length, label: plural(open.length, ['открытая', 'открытые', 'открытых']) },
    { value: items.reduce((n, j) => n + j.responses_count, 0), label: t('откликов всего') },
    { value: items.reduce((n, j) => n + j.accepted_count, 0), label: t('выбрано людей') },
  ];

  return (
    <div className="screen">
      <header className="feed-head feed-head--row">
        <div>
          <h1 className="app-title">{t('Мои заявки')}</h1>
          <p className="hint lead">
            {pending ? (
              <span className="lead-accent">
                <Icon name="inbox" size={16} />
                {pending} {plural(pending, ['отклик ждёт ответа', 'отклика ждут ответа', 'откликов ждут ответа'])}
              </span>
            ) : (
              t('Отклики придут сообщением от бота.')
            )}
          </p>
        </div>
        {items.length > 0 && (
          <button type="button" className="btn btn--primary btn--sm" onClick={onCreate}>
            <Icon name="plus" size={18} />
            {t('Новая')}
          </button>
        )}
      </header>

      {status === 'ready' && items.length > 0 && (
        <div className="stats" aria-label={t('Статистика')}>
          {stats.map((s) => (
            <div key={s.label} className="stats__item">
              <span className="stats__value">{s.value}</span>
              <span className="stats__label">{s.label}</span>
            </div>
          ))}
        </div>
      )}

      {status === 'loading' && (
        <div className="list">
          <JobCardSkeleton />
          <JobCardSkeleton />
        </div>
      )}
      {status === 'error' && <ErrorState text={error} onRetry={() => setAttempt((a) => a + 1)} />}

      {status === 'ready' && items.length === 0 && (
        <EmptyState
          icon="clipboard"
          tone="brand"
          title={t('Заявок пока нет')}
          text={t('Опишите задачу и оплату — исполнители откликнутся, а вы выберете подходящих.')}
          action={
            <button type="button" className="btn btn--primary" onClick={onCreate}>
              <Icon name="plus" size={18} />
              {t('Создать заявку')}
            </button>
          }
        />
      )}

      {status === 'ready' && open.length > 0 && (
        <div className="list">
          {past.length > 0 && <h2 className="list-title list-title--first">{t('Открытые')}</h2>}
          {open.map((j) => (
            <JobCard key={j.id} job={j} category={catById.get(j.category)} onOpen={onOpenJob} owner />
          ))}
        </div>
      )}
      {status === 'ready' && past.length > 0 && (
        <>
          <h2 className="list-title">{t('Завершённые')}</h2>
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
