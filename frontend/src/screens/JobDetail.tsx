import { useEffect, useState, type ReactNode } from 'react';
import { api, ApiError, errorText } from '../api';
import { EmptyState, ErrorState, Spinner } from '../components/States';
import { MetroDot } from '../components/MetroDot';
import {
  UNIT_LABEL,
  formatAge,
  formatDistance,
  formatHours,
  formatPay,
  formatPayTotal,
  formatPhone,
  formatUntil,
  formatWhen,
  plural,
  rub,
  telHref,
} from '../format';
import { backButtonSupported, haptic, openLink } from '../telegram';
import type { Job, Meta } from '../types';

interface Props {
  jobId: number;
  initial: Job | null;
  meta: Meta | null;
  onBack(): void;
}

export function JobDetail({ jobId, initial, meta, onBack }: Props) {
  const [job, setJob] = useState<Job | null>(initial);
  const [status, setStatus] = useState<'loading' | 'ready' | 'notfound' | 'error'>(initial ? 'ready' : 'loading');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (initial && attempt === 0) return;
    let alive = true;
    setStatus('loading');
    api
      .job(jobId)
      .then((j) => {
        if (!alive) return;
        setJob(j);
        setStatus('ready');
      })
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) setStatus('notfound');
        else {
          setError(errorText(e));
          setStatus('error');
        }
      });
    return () => {
      alive = false;
    };
  }, [jobId, initial, attempt]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [jobId]);

  const backBar = !backButtonSupported && (
    <div className="topbar">
      <button type="button" className="link-btn topbar__back" onClick={onBack}>
        ‹ Назад
      </button>
    </div>
  );

  if (status === 'loading' || (status === 'ready' && !job)) {
    return (
      <div className="screen screen--detail">
        {backBar}
        <div className="center pad-xl">
          <Spinner />
        </div>
      </div>
    );
  }
  if (status === 'notfound') {
    return (
      <div className="screen screen--detail">
        {backBar}
        <EmptyState
          icon="🕓"
          title="Заказ уже неактуален"
          text="Его сняли или время прошло. Посмотрите свежие заказы в ленте."
          action={
            <button type="button" className="btn btn--primary" onClick={onBack}>
              К ленте
            </button>
          }
        />
      </div>
    );
  }
  if (status === 'error' || !job) {
    return (
      <div className="screen screen--detail">
        {backBar}
        <ErrorState text={error} onRetry={() => setAttempt((a) => a + 1)} />
      </div>
    );
  }

  const cat = meta?.categories.find((c) => c.id === job.category);
  const pay = formatPay(job);
  const total = formatPayTotal(job);
  const when = formatWhen(job);
  const chats = job.posts.length;

  const rows: [string, ReactNode][] = [];
  if (when) rows.push(['Когда', when + (job.duration_hours != null ? ` · ${formatHours(job.duration_hours)}` : '')]);
  else if (job.duration_hours != null) rows.push(['Сколько', formatHours(job.duration_hours)]);
  if (job.workers_needed != null) rows.push(['Нужно', `${job.workers_needed} ${plural(job.workers_needed, ['человек', 'человека', 'человек'])}`]);
  if (job.metro)
    rows.push([
      'Метро',
      <>
        <span className="meta-item">
          <MetroDot color={job.metro.color} />
          {job.metro.name}
        </span>
        {job.metro.line && <span className="hint metro-line">{job.metro.line}</span>}
      </>,
    ]);
  if (job.address) rows.push(['Адрес', job.address]);
  if (job.distance_km != null) rows.push(['От вас', formatDistance(job.distance_km)]);
  if (job.pay_amount != null && job.pay_unit && job.pay_unit !== 'hour')
    rows.push(['В объявлении', `${rub(job.pay_amount)} ${UNIT_LABEL[job.pay_unit]}`]);
  if (job.pay_timing) rows.push(['Выплата', job.pay_timing]);
  if (job.phone) rows.push(['Телефон', <a href={telHref(job.phone)}>{formatPhone(job.phone)}</a>]);

  return (
    <div className="screen screen--detail">
      {backBar}
      <div className="detail">
        <div className="detail__cat">
          <span aria-hidden="true">{cat?.emoji ?? '🧩'}</span> {cat?.label ?? 'Подработка'}
        </div>
        <h1 className="detail__title">{job.title}</h1>

        <div className="detail__pay">
          <span className="pay pay--big">{pay ?? 'Оплата не указана'}</span>
          {total && <span className="pay-total">{total} за всё</span>}
        </div>
        {job.pay_estimated && job.pay_per_hour != null && (
          <div className="hint small">≈ — ставка в час посчитана из объявления, уточните у заказчика</div>
        )}

        <dl className="facts">
          {rows.map(([k, v]) => (
            <div className="facts__row" key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>

        {job.description && (
          <section className="section">
            <h2 className="section__title">Описание</h2>
            <p className="detail__desc">{job.description}</p>
          </section>
        )}

        <div className="actions">
          {job.phone && (
            <a className="btn btn--primary btn--wide" href={telHref(job.phone)} onClick={() => haptic('light')}>
              📞 Позвонить
            </a>
          )}
          {job.posts.length === 1 && (
            <button
              type="button"
              className={`btn btn--wide ${job.phone ? 'btn--secondary' : 'btn--primary'}`}
              onClick={() => openLink(job.posts[0].link)}
            >
              💬 Открыть пост
            </button>
          )}
        </div>

        {chats > 0 && (
          <section className="section">
            <h2 className="section__title">
              Опубликовано в {chats} {plural(chats, ['чате', 'чатах', 'чатах'])}
            </h2>
            <ul className="posts">
              {job.posts.map((p) => (
                <li key={p.link} className="post">
                  <div className="post__info">
                    <div className="post__chat">{p.chat ?? p.link.replace(/^https?:\/\//, '')}</div>
                    {p.sent_at && <div className="hint small">{formatAge(p.sent_at)}</div>}
                  </div>
                  {job.posts.length > 1 && (
                    <button type="button" className="btn btn--secondary btn--sm" onClick={() => openLink(p.link)}>
                      Открыть пост
                    </button>
                )}
              </li>
            ))}
          </ul>
        </section>
        )}

        <div className="hint small detail__foot">
          Найдено {formatAge(job.first_seen_at)} · актуально {formatUntil(job.expires_at)}
        </div>
        <div className="hint small detail__warn">
          Gigo только собирает объявления из чатов. Не платите заранее за «оформление» или «форму» и не передавайте данные карты.
        </div>
      </div>
    </div>
  );
}
