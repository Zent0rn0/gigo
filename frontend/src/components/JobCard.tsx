import type { ReactNode } from 'react';
import type { Category, Job } from '../types';
import {
  JOB_STATE_LABEL,
  JOB_STATE_TONE,
  formatAge,
  formatDistance,
  formatPay,
  formatPayTotal,
  formatWhen,
  isActiveResponse,
  jobState,
  plural,
} from '../format';
import { MetroDot } from './MetroDot';
import { StatusChip } from './ui';

interface Props {
  job: Job;
  category: Category | undefined;
  onOpen(job: Job): void;
  /** Вид для автора: статус и новые отклики вместо имени заказчика. */
  owner?: boolean;
  /** Дополнительная строка внизу (статус отклика и т.п.). */
  footer?: ReactNode;
}

export function JobCard({ job, category, onOpen, owner, footer }: Props) {
  const pay = formatPay(job);
  const total = formatPayTotal(job);
  const when = formatWhen(job);
  const state = jobState(job);
  const pending = job.pending_count ?? 0;
  return (
    <button type="button" className="job-card" onClick={() => onOpen(job)}>
      <div className="job-card__top">
        <span className="job-card__emoji" aria-hidden="true">
          {category?.emoji ?? '🧩'}
        </span>
        <span className="job-card__title">{job.title}</span>
        <span className="job-card__age">{formatAge(job.created_at)}</span>
      </div>
      <div className="job-card__pay">
        {pay ? <span className="pay">{pay}</span> : <span className="pay pay--none">оплата не указана</span>}
        {total && <span className="pay-total">{total} за всё</span>}
      </div>
      <div className="job-card__meta">
        {job.metro && (
          <span className="meta-item">
            <MetroDot color={job.metro.color} title={job.metro.line} />
            {job.metro.name}
          </span>
        )}
        {!job.metro && job.address && <span className="meta-item">{job.address}</span>}
        {job.distance_km != null && <span className="meta-item">{formatDistance(job.distance_km)}</span>}
        {when && <span className="meta-item meta-item--when">{when}</span>}
      </div>
      {owner ? (
        <div className="job-card__foot">
          <StatusChip tone={JOB_STATE_TONE[state]}>{JOB_STATE_LABEL[state]}</StatusChip>
          {pending > 0 ? (
            <span className="badge badge--accent">
              {pending} {plural(pending, ['новый отклик', 'новых отклика', 'новых откликов'])}
            </span>
          ) : (
            <span className="hint small">
              {job.responses_count ? `${job.responses_count} ${plural(job.responses_count, ['отклик', 'отклика', 'откликов'])}` : 'откликов пока нет'}
            </span>
          )}
        </div>
      ) : (
        footer ??
        (job.is_mine ? (
          <div className="job-card__foot">
            <StatusChip tone="muted">Ваша заявка</StatusChip>
          </div>
        ) : isActiveResponse(job.my_response) && (
          <div className="job-card__foot">
            <StatusChip tone={job.my_response!.status === 'accepted' ? 'ok' : 'wait'}>
              {job.my_response!.status === 'accepted' ? '✓ Вас выбрали' : '✓ Вы откликнулись'}
            </StatusChip>
          </div>
        ))
      )}
    </button>
  );
}

export function JobCardSkeleton() {
  return (
    <div className="job-card job-card--skeleton" aria-hidden="true">
      <div className="sk sk--title" />
      <div className="sk sk--pay" />
      <div className="sk sk--meta" />
    </div>
  );
}
