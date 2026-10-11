import type { Category, Job } from '../types';
import { formatAge, formatDistance, formatPay, formatPayTotal, formatWhen } from '../format';
import { MetroDot } from './MetroDot';

interface Props {
  job: Job;
  category: Category | undefined;
  onOpen(job: Job): void;
}

export function JobCard({ job, category, onOpen }: Props) {
  const pay = formatPay(job);
  const total = formatPayTotal(job);
  const when = formatWhen(job);
  return (
    <button type="button" className="job-card" onClick={() => onOpen(job)}>
      <div className="job-card__top">
        <span className="job-card__emoji" aria-hidden="true">
          {category?.emoji ?? '🧩'}
        </span>
        <span className="job-card__title">{job.title}</span>
        <span className="job-card__age">{formatAge(job.first_seen_at)}</span>
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
        {job.distance_km != null && <span className="meta-item">{formatDistance(job.distance_km)}</span>}
        {when && <span className="meta-item meta-item--when">{when}</span>}
      </div>
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
