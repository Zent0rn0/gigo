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
import { Icon, categoryIcon } from './Icon';
import { MetroDot } from './MetroDot';
import { RatingText, StatusChip } from './ui';

interface Props {
  job: Job;
  category: Category | undefined;
  onOpen?(job: Job): void;
  /** Вид для автора: статус и новые отклики вместо имени заказчика. */
  owner?: boolean;
  /** Дополнительная строка внизу (статус отклика и т.п.). */
  footer?: ReactNode;
  /** Предпросмотр в форме: не нажимается. */
  preview?: boolean;
}

export function CategoryTile({ id, size = 40 }: { id: string | null | undefined; size?: number }) {
  return (
    <span className={`cat-tile cat-tile--${categoryIcon(id)}`} style={{ width: size, height: size }} aria-hidden="true">
      <Icon name={categoryIcon(id)} size={Math.round(size * 0.55)} />
    </span>
  );
}

export function JobCard({ job, category, onOpen, owner, footer, preview }: Props) {
  const pay = formatPay(job);
  const total = formatPayTotal(job);
  const when = formatWhen(job);
  const state = jobState(job);
  const pending = job.pending_count ?? 0;
  const hot = owner && pending > 0 && state === 'open';

  const foot = owner ? (
    <div className="job-card__foot">
      <StatusChip tone={JOB_STATE_TONE[state]}>{JOB_STATE_LABEL[state]}</StatusChip>
      {pending > 0 ? (
        <span className="badge badge--brand">
          <Icon name="inbox" size={14} strokeWidth={2.2} />
          {pending} {plural(pending, ['новый отклик', 'новых отклика', 'новых откликов'])}
        </span>
      ) : (
        <span className="hint small">
          {job.responses_count ? `${job.responses_count} ${plural(job.responses_count, ['отклик', 'отклика', 'откликов'])}` : 'откликов пока нет'}
        </span>
      )}
    </div>
  ) : (
    footer ?? (
      <div className="job-card__foot">
        <span className="job-card__who">
          {job.employer.first_name} · <RatingText rating={job.employer.rating} count={job.employer.reviews_count} />
        </span>
        {job.is_mine ? (
          <StatusChip tone="muted">Ваша заявка</StatusChip>
        ) : isActiveResponse(job.my_response) ? (
          <StatusChip tone={job.my_response!.status === 'accepted' ? 'ok' : 'wait'} icon="check">
            {job.my_response!.status === 'accepted' ? 'Вас выбрали' : 'Вы откликнулись'}
          </StatusChip>
        ) : job.is_invited ? (
          <StatusChip tone="ok" icon="send">
            Вас пригласили
          </StatusChip>
        ) : (
          <span className="job-card__age">{preview ? 'только что' : formatAge(job.created_at)}</span>
        )}
      </div>
    )
  );

  const body = (
    <>
      <div className="job-card__top">
        <CategoryTile id={job.category} />
        <div className="job-card__head">
          <span className="job-card__title">{job.title}</span>
          <div className="job-card__pay">
            {pay ? <span className="pay">{pay}</span> : <span className="pay pay--none">оплата не указана</span>}
            {total && <span className="pay-total">{total} за всё</span>}
          </div>
        </div>
      </div>
      <div className="job-card__meta">
        {job.metro && (
          <span className="meta-item">
            <MetroDot color={job.metro.color} title={job.metro.line} />
            {job.metro.name}
          </span>
        )}
        {!job.metro && job.address && (
          <span className="meta-item meta-item--clip">
            <Icon name="pin" size={15} />
            {job.address}
          </span>
        )}
        {job.distance_km != null && (
          <span className="meta-item">
            <Icon name="navigation" size={14} />
            {formatDistance(job.distance_km)}
          </span>
        )}
        {when && (
          <span className="meta-item meta-item--when">
            <Icon name="clock" size={15} />
            {when}
          </span>
        )}
        {job.workers_needed != null && job.workers_needed > 1 && (
          <span className="meta-item">
            <Icon name="users" size={15} />
            {job.workers_needed} чел.
          </span>
        )}
      </div>
      {foot}
    </>
  );

  const cls = `job-card${hot ? ' job-card--hot' : ''}${preview ? ' job-card--preview' : ''}`;
  if (preview || !onOpen) return <div className={cls}>{body}</div>;
  return (
    <button type="button" className={cls} onClick={() => onOpen(job)} title={category?.label}>
      {body}
    </button>
  );
}

export function JobCardSkeleton() {
  return (
    <div className="job-card job-card--skeleton" aria-hidden="true">
      <div className="job-card__top">
        <span className="sk sk--tile" />
        <div className="job-card__head">
          <div className="sk sk--title" />
          <div className="sk sk--pay" />
        </div>
      </div>
      <div className="sk sk--meta" />
      <div className="sk sk--foot" />
    </div>
  );
}
