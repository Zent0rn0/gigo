import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { api, ApiError, errorText } from '../api';
import { EmptyState, ErrorState, Spinner } from '../components/States';
import { HelpSheet, type HelpTopic } from '../components/HelpSheet';
import { Icon, type IconName } from '../components/Icon';
import { CategoryTile } from '../components/JobCard';
import { MetroDot } from '../components/MetroDot';
import { ReportSheet } from '../components/ReportSheet';
import { ReviewSheet, type ReviewTarget } from '../components/ReviewSheet';
import { Sheet } from '../components/Sheet';
import { ConfirmButton, ContactButton, IconButton, SkillChips, StatusChip, UserRow } from '../components/ui';
import {
  JOB_STATE_LABEL,
  JOB_STATE_TONE,
  RESPONSE_LABEL_OWNER,
  RESPONSE_LABEL_WORKER,
  RESPONSE_TONE,
  UNIT_LABEL,
  formatAge,
  formatDistance,
  formatHours,
  formatPay,
  formatPayTotal,
  formatUntil,
  formatWhen,
  jobState,
  plural,
  rub,
} from '../format';
import { t } from '../i18n';
import { useMainButton } from '../mainButton';
import { backButtonSupported, haptic, jobShareLink, mainButtonSupported, shareText } from '../telegram';
import type { Job, JobResponse, JobStatus, Me, Meta, ResponseStatus, Role } from '../types';

interface Props {
  jobId: number;
  initial: Job | null;
  meta: Meta;
  me: Me;
  /** Экран сверху стека (видим): только тогда он управляет MainButton. */
  active: boolean;
  /** Меняется после правки заявки: карточка тихо перезагружается. */
  version: number;
  onBack(): void;
  onOpenUser(id: number): void;
  onSwitchRole(role: Role): void;
  /** Что-то поменялось: списки «Мои заявки» / «Отклики» перезагрузятся. */
  onChanged(): void;
  /** Свежая версия заявки, чтобы лента показала «Вы откликнулись». */
  onJobUpdated(job: Job): void;
  /** Автор: открыть форму правки. */
  onEdit(job: Job): void;
  /** Автор: новая заявка по образцу этой. */
  onRepeat(job: Job): void;
  toast(text: string): void;
}

export function JobDetail({
  jobId,
  initial,
  meta,
  me,
  active,
  version,
  onBack,
  onOpenUser,
  onSwitchRole,
  onChanged,
  onJobUpdated,
  onEdit,
  onRepeat,
  toast,
}: Props) {
  const [job, setJob] = useState<Job | null>(initial);
  const [status, setStatus] = useState<'loading' | 'ready' | 'notfound' | 'error'>(initial ? 'ready' : 'loading');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  const [respondOpen, setRespondOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [respondError, setRespondError] = useState('');
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const [help, setHelp] = useState<HelpTopic | null>(null);

  const loaded = useRef(!!initial);
  // Карточку из списка показываем сразу и тихо обновляем: у автора догрузятся отклики, у исполнителя — свежий my_response.
  useEffect(() => {
    let alive = true;
    const soft = loaded.current && attempt === 0;
    if (!soft) setStatus('loading');
    api
      .job(jobId)
      .then((j) => {
        if (!alive) return;
        loaded.current = true;
        setJob(j);
        setStatus('ready');
      })
      .catch((e) => {
        if (!alive) return;
        if (soft) return; // показываем то, что уже есть
        if (e instanceof ApiError && e.status === 404) setStatus('notfound');
        else {
          setError(errorText(e));
          setStatus('error');
        }
      });
    return () => {
      alive = false;
    };
  }, [jobId, attempt, version]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [jobId]);

  useEffect(() => {
    if (job) onJobUpdated(job);
  }, [job, onJobUpdated]);

  const reload = useCallback(() => {
    api
      .job(jobId)
      .then(setJob)
      .catch(() => {
        /* оставим как есть */
      });
  }, [jobId]);

  const isOwner = !!job?.is_mine;
  const my = job?.my_response ?? null;
  const state = job ? jobState(job) : 'open';
  const canRespond = !!job && !isOwner && me.role === 'worker' && state === 'open' && (!my || my.status === 'withdrawn');

  const submitResponse = async () => {
    if (!job || busy) return;
    setBusy('respond');
    setRespondError('');
    try {
      const r = await api.respond(job.id, message.trim() || null);
      haptic('success');
      setJob({ ...job, my_response: r, responses_count: job.responses_count + (my ? 0 : 1) });
      setRespondOpen(false);
      setMessage('');
      toast(t('Отклик отправлен. Заказчик получит уведомление в Telegram.'));
      onChanged();
    } catch (e) {
      haptic('error');
      setRespondError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  useMainButton(
    active && job && !review && !reportOpen && !help
      ? respondOpen
        ? { text: t('Отправить отклик'), onClick: submitResponse, progress: busy === 'respond' }
        : canRespond
          ? { text: my ? t('Откликнуться снова') : t('Откликнуться'), onClick: () => setRespondOpen(true) }
          : null
      : null,
  );

  const withdraw = async () => {
    if (!job || !my || busy) return;
    setBusy('withdraw');
    try {
      const r = await api.setResponseStatus(my.id, 'withdrawn');
      haptic('success');
      setJob({ ...job, my_response: r });
      toast(t('Отклик отозван'));
      onChanged();
    } catch (e) {
      haptic('error');
      toast(errorText(e));
      reload(); // заявка могла измениться на сервере или запрос всё-таки прошёл: показываем как есть
    } finally {
      setBusy(null);
    }
  };

  const setJobStatus = async (s: JobStatus) => {
    if (!job || busy) return;
    setBusy(`job-${s}`);
    try {
      const j = await api.setJobStatus(job.id, s);
      haptic('success');
      setJob({ ...j, responses: j.responses ?? job.responses });
      toast(s === 'closed' ? t('Набор закрыт. Заявка пропала из ленты.') : s === 'cancelled' ? t('Заявка отменена') : t('Заявка снова в ленте'));
      onChanged();
    } catch (e) {
      haptic('error');
      toast(errorText(e));
      reload(); // заявка могла измениться на сервере или запрос всё-таки прошёл: показываем как есть
    } finally {
      setBusy(null);
    }
  };

  const decide = async (r: JobResponse, s: Exclude<ResponseStatus, 'pending' | 'withdrawn'>) => {
    if (!job || busy) return;
    setBusy(`resp-${r.id}`);
    try {
      const upd = await api.setResponseStatus(r.id, s);
      haptic('success');
      setJob({ ...job, responses: (job.responses ?? []).map((x) => (x.id === r.id ? upd : x)) });
      toast(s === 'accepted' ? t('{name} принят. Контакты пришлём вам обоим в Telegram.', { name: r.worker.first_name }) : t('Отклик отклонён'));
      onChanged();
      reload();
    } catch (e) {
      haptic('error');
      toast(errorText(e));
      reload(); // заявка могла измениться на сервере или запрос всё-таки прошёл: показываем как есть
    } finally {
      setBusy(null);
    }
  };

  const savedReview = (responseId: number, rv: { rating: number; text: string | null }) => {
    setReview(null);
    toast(t('Спасибо за отзыв!'));
    setJob((j) => {
      if (!j) return j;
      if (j.my_response?.id === responseId) return { ...j, my_response: { ...j.my_response, my_review: rv } };
      return { ...j, responses: j.responses?.map((x) => (x.id === responseId ? { ...x, my_review: rv } : x)) };
    });
    onChanged();
  };

  const toggleSaved = async () => {
    if (!job || busy) return;
    const on = !job.is_saved;
    setBusy('save');
    setJob({ ...job, is_saved: on }); // сразу, без ожидания сервера
    try {
      await api.setSaved(job.id, on);
      haptic(on ? 'success' : 'light');
      toast(on ? t('Сохранено в избранное. Оно во вкладке «Отклики».') : t('Убрано из избранного'));
      onChanged();
    } catch (e) {
      haptic('error');
      setJob((j) => (j ? { ...j, is_saved: !on } : j));
      toast(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  const share = async () => {
    if (!job) return;
    const parts = [formatPay(job), job.metro ? t('м. {station}', { station: job.metro.name }) : job.address, formatWhen(job)].filter(Boolean);
    const text = `${job.title}${parts.length ? ` — ${parts.join(', ')}` : ''}`;
    const link = jobShareLink(job.id);
    const r = await shareText(link ? t('{text}. Заявка в Gigo:', { text }) : t('{text}. Ищите в Gigo.', { text }), link);
    if (r === 'copied') toast(link ? t('Ссылка на заявку скопирована') : t('Текст заявки скопирован'));
    else if (r === 'failed') toast(t('Не удалось поделиться'));
  };

  const backBar = (withActions: boolean) =>
    (!backButtonSupported || withActions) && (
      <div className="topbar">
        {!backButtonSupported ? (
          <button type="button" className="topbar__back" onClick={onBack}>
            <Icon name="chevron-left" size={22} />
            {t('Назад')}
          </button>
        ) : (
          <span />
        )}
        {withActions && (
          <span className="topbar__actions">
            {job && !job.is_mine && (
              <button
                type="button"
                className={`icon-btn${job.is_saved ? ' icon-btn--on' : ''}`}
                onClick={toggleSaved}
                aria-pressed={!!job.is_saved}
                aria-label={job.is_saved ? t('Убрать из избранного') : t('В избранное')}
                title={job.is_saved ? t('Убрать из избранного') : t('В избранное')}
              >
                <Icon name="bookmark" size={20} filled={!!job.is_saved} />
              </button>
            )}
            <IconButton icon="share" label={t('Поделиться')} onClick={share} />
          </span>
        )}
      </div>
    );

  if (status === 'loading' || (status === 'ready' && !job)) {
    return (
      <div className="screen screen--detail">
        {backBar(false)}
        <div className="center pad-xl">
          <Spinner />
        </div>
      </div>
    );
  }
  if (status === 'notfound') {
    return (
      <div className="screen screen--detail">
        {backBar(false)}
        <EmptyState
          icon="clock"
          title={t('Заявка уже неактуальна')}
          text={t('Её закрыли или время прошло.')}
          action={
            <button type="button" className="btn btn--primary" onClick={onBack}>
              {t('Назад')}
            </button>
          }
        />
      </div>
    );
  }
  if (status === 'error' || !job) {
    return (
      <div className="screen screen--detail">
        {backBar(false)}
        <ErrorState text={error} onRetry={() => setAttempt((a) => a + 1)} />
      </div>
    );
  }

  const cat = meta.categories.find((c) => c.id === job.category);
  const pay = formatPay(job);
  const total = formatPayTotal(job);
  const when = formatWhen(job);
  const unitLabel = (u: NonNullable<Job['pay_unit']>) => meta.pay_units.find((p) => p.id === u)?.label ?? t(UNIT_LABEL[u]);

  const rows: [IconName, string, ReactNode][] = [];
  if (when) rows.push(['clock', t('Когда'), when + (job.duration_hours != null ? ` · ${formatHours(job.duration_hours)}` : '')]);
  else if (job.duration_hours != null) rows.push(['clock', t('Сколько'), formatHours(job.duration_hours)]);
  if (job.workers_needed != null)
    rows.push([
      'users',
      t('Нужно'),
      `${job.workers_needed} ${plural(job.workers_needed, ['человек', 'человека', 'человек'])}` +
        (job.accepted_count ? ` · ${t('выбрано {n}', { n: job.accepted_count })}` : ''),
    ]);
  if (job.metro)
    rows.push([
      'metro',
      t('Метро'),
      <>
        <span className="meta-item">
          <MetroDot color={job.metro.color} />
          {job.metro.name}
        </span>
        {job.metro.line && <span className="hint metro-line">{job.metro.line}</span>}
      </>,
    ]);
  if (job.address) rows.push(['pin', t('Адрес'), job.address]);
  if (job.distance_km != null) rows.push(['navigation', t('От вас'), formatDistance(job.distance_km)]);
  if (job.pay_amount != null && job.pay_unit && job.pay_unit !== 'hour') rows.push(['ruble', t('Оплата'), `${rub(job.pay_amount)} ${unitLabel(job.pay_unit)}`]);
  if (job.pay_timing) rows.push(['wallet', t('Выплата'), t(job.pay_timing)]); // готовые варианты («сразу»…) переводятся, свой текст заказчика — как есть

  const reviewFor = (r: JobResponse, name: string): ReviewTarget => ({
    responseId: r.id,
    name,
    jobTitle: job.title,
    initial: r.my_review,
  });

  return (
    <div className={`screen screen--detail${canRespond && !mainButtonSupported ? ' screen--with-action' : ''}`}>
      {backBar(true)}
      <div className="detail">
        <div className="detail__cat">
          <span className="detail__cat-label">
            <CategoryTile id={job.category} size={28} />
            {cat?.label ?? t('Подработка')}
          </span>
          {(isOwner || state !== 'open') && <StatusChip tone={JOB_STATE_TONE[state]}>{t(JOB_STATE_LABEL[state])}</StatusChip>}
        </div>
        <h1 className="detail__title">{job.title}</h1>

        <div className="detail__pay">
          <span className="pay pay--big">{pay ?? t('Оплата не указана')}</span>
          {total && <span className="pay-total">{t('{sum} за всё', { sum: total })}</span>}
        </div>
        {job.pay_estimated && job.pay_per_hour != null && <div className="hint small">{t('≈ ставка в час посчитана из оплаты за смену (8 часов)')}</div>}

        <dl className="facts">
          {rows.map(([icon, k, v]) => (
            <div className="facts__row" key={k}>
              <dt>
                <Icon name={icon} size={18} />
                {k}
              </dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>

        {/* ——— исполнитель ——— */}
        {!isOwner && job.is_invited && canRespond && (
          <div className="note note--accent invite-note">
            <Icon name="send" size={18} />
            {t('{name} приглашает вас на эту заявку. Откликнитесь, если подходит.', { name: job.employer.first_name })}
          </div>
        )}
        {!isOwner && my && my.status !== 'withdrawn' && (
          <section className="section my-response">
            <div className="my-response__head">
              <span>{t('Ваш отклик')}</span>
              <StatusChip tone={RESPONSE_TONE[my.status]}>{t(RESPONSE_LABEL_WORKER[my.status])}</StatusChip>
            </div>
            {my.message && <p className="quote">{my.message}</p>}
            {my.status === 'pending' && <div className="hint small">{t('Заказчик получил уведомление. Ответ придёт сообщением от бота.')}</div>}
            {my.status === 'rejected' && <div className="hint small">{t('Заказчик выбрал других. Посмотрите другие заявки в ленте.')}</div>}
            {my.status === 'accepted' && (
              <>
                <div className="hint small">{t('Договоритесь о деталях с заказчиком напрямую.')}</div>
                <div className="actions">
                  {my.contact && <ContactButton contact={my.contact} wide />}
                  <button type="button" className="btn btn--secondary btn--wide" onClick={() => setReview(reviewFor(my, job.employer.first_name))}>
                    <Icon name="star" size={18} filled={!!my.my_review} />
                    {my.my_review ? t('Ваш отзыв: {rating} из 5 · изменить', { rating: my.my_review.rating }) : t('Оставить отзыв')}
                  </button>
                </div>
              </>
            )}
            {(my.status === 'pending' || my.status === 'accepted') && (
              <div className="actions">
                <ConfirmButton
                  label={my.status === 'accepted' ? t('Отказаться от работы') : t('Отозвать отклик')}
                  confirm={my.status === 'accepted' ? t('Точно отказаться? Заказчик получит уведомление.') : t('Отозвать отклик?')}
                  busy={busy === 'withdraw'}
                  onConfirm={withdraw}
                  className="btn btn--ghost-danger btn--wide"
                />
              </div>
            )}
          </section>
        )}

        {job.description && (
          <section className="section">
            <h2 className="section__title">{t('Описание')}</h2>
            <p className="detail__desc">{job.description}</p>
          </section>
        )}

        {!isOwner && (
          <section className="section">
            <h2 className="section__title">{t('Заказчик')}</h2>
            <div className="person-card">
              <UserRow user={job.employer} onOpen={onOpenUser} caption={t('профиль и отзывы')} />
            </div>
          </section>
        )}

        {!isOwner && me.role === 'worker' && (
          <div className="safety-note">
            <Icon name="shield" size={18} />
            <span>
              {t('Не платите за «оформление» и не передавайте данные карт.')}{' '}
              <button type="button" className="link-btn link-btn--inline" onClick={() => setHelp('safety')}>
                {t('Подробнее')}
              </button>
            </span>
          </div>
        )}

        {!isOwner && me.role === 'employer' && state === 'open' && (
          <div className="note">
            <Icon name="info" size={18} />
            {t('Откликаться могут исполнители.')}{' '}
            <button type="button" className="link-btn" onClick={() => onSwitchRole('worker')}>
              {t('Стать исполнителем')}
            </button>
          </div>
        )}

        {canRespond && !mainButtonSupported && (
          <div className="action-bar">
            <button type="button" className="btn btn--primary btn--wide btn--lg" onClick={() => setRespondOpen(true)}>
              <Icon name="send" size={20} />
              {my ? t('Откликнуться снова') : t('Откликнуться')}
            </button>
          </div>
        )}

        {/* ——— автор ——— */}
        {isOwner && (
          <div className="actions">
            {state === 'open' && (
              <>
                <div className="row-gap">
                  <button type="button" className="btn btn--secondary btn--grow" disabled={!!busy} onClick={() => onEdit(job)}>
                    <Icon name="edit" size={18} />
                    {t('Изменить')}
                  </button>
                  <button type="button" className="btn btn--secondary btn--grow" disabled={!!busy} onClick={() => onRepeat(job)}>
                    <Icon name="copy" size={18} />
                    {t('Повторить')}
                  </button>
                </div>
                <button type="button" className="btn btn--secondary btn--wide" disabled={!!busy} onClick={() => setJobStatus('closed')}>
                  <Icon name="check" size={18} />
                  {busy === 'job-closed' ? t('Закрываем…') : t('Закрыть набор')}
                </button>
                <ConfirmButton label={t('Отменить заявку')} confirm={t('Отменить заявку? Исполнители получат уведомление.')} onConfirm={() => setJobStatus('cancelled')} busy={!!busy} className="btn btn--ghost-danger btn--wide" />
              </>
            )}
            {state === 'closed' && (
              <>
                <button type="button" className="btn btn--secondary btn--wide" disabled={!!busy} onClick={() => setJobStatus('open')}>
                  {busy === 'job-open' ? t('Открываем…') : t('Открыть набор снова')}
                </button>
                <ConfirmButton label={t('Отменить заявку')} confirm={t('Отменить заявку?')} onConfirm={() => setJobStatus('cancelled')} busy={!!busy} className="btn btn--ghost-danger btn--wide" />
              </>
            )}
            {state === 'cancelled' && (
              <button type="button" className="btn btn--secondary btn--wide" disabled={!!busy} onClick={() => setJobStatus('open')}>
                {busy === 'job-open' ? t('Открываем…') : t('Открыть снова')}
              </button>
            )}
            {state !== 'open' && (
              <button type="button" className="btn btn--primary btn--wide" onClick={() => onRepeat(job)}>
                <Icon name="copy" size={18} />
                {t('Повторить заявку')}
              </button>
            )}
            {state === 'expired' && <div className="hint small center">{t('Срок заявки прошёл. Нажмите «Повторить», если люди ещё нужны.')}</div>}
          </div>
        )}

        <div className="hint small detail__foot">
          {t('Опубликована {age}', { age: formatAge(job.created_at) })}
          {state === 'open' ? ` · ${t('актуальна {until}', { until: formatUntil(job.expires_at) })}` : ''}
        </div>
      </div>

      {!isOwner && (
        <div className="detail-links">
          <button type="button" className="text-btn" onClick={share}>
            <Icon name="share" size={18} />
            {t('Поделиться')}
          </button>
          <button type="button" className="text-btn text-btn--danger" onClick={() => setReportOpen(true)}>
            <Icon name="flag" size={18} />
            {t('Пожаловаться')}
          </button>
        </div>
      )}

      {isOwner && (
        <section className="responses">
          <h2 className="list-title">
            {t('Отклики')}
            {job.responses?.length ? ` · ${job.responses.length}` : ''}
          </h2>
          {job.workers_needed != null && job.accepted_count >= job.workers_needed && state === 'open' && (
            <div className="note note--accent">{t('Вы выбрали всех, кого нужно. Закройте набор, чтобы заявка ушла из ленты.')}</div>
          )}
          {!job.responses ? (
            <div className="center pad">
              <Spinner />
            </div>
          ) : job.responses.length === 0 ? (
            <EmptyState icon="inbox" title={t('Откликов пока нет')} text={t('Бот напишет, как только кто-то откликнется. Обычно это занимает минуты.')} />
          ) : (
            <div className="list">
              {job.responses.map((r) => (
                <div key={r.id} className={`resp-card${r.status === 'rejected' || r.status === 'withdrawn' ? ' resp-card--dim' : ''}`}>
                  <UserRow
                    user={r.worker}
                    onOpen={onOpenUser}
                    right={<StatusChip tone={RESPONSE_TONE[r.status]}>{t(RESPONSE_LABEL_OWNER[r.status])}</StatusChip>}
                  />
                  {!!r.worker.skills?.length && <SkillChips ids={r.worker.skills} meta={meta} highlight={job.category} />}
                  {r.worker.about && <div className="resp-card__about">{r.worker.about}</div>}
                  {r.message && <p className="quote">{r.message}</p>}
                  <div className="hint small">{formatAge(r.created_at)}</div>
                  {r.status === 'pending' && (
                    <div className="row-gap resp-card__actions">
                      <button type="button" className="btn btn--sm btn--secondary btn--grow" disabled={!!busy} onClick={() => decide(r, 'rejected')}>
                        {t('Отклонить')}
                      </button>
                      <button type="button" className="btn btn--sm btn--primary btn--grow" disabled={!!busy} onClick={() => decide(r, 'accepted')}>
                        <Icon name="check" size={18} />
                        {busy === `resp-${r.id}` ? '…' : t('Принять')}
                      </button>
                    </div>
                  )}
                  {r.status === 'accepted' && (
                    <div className="row-gap resp-card__actions">
                      {r.contact && <ContactButton contact={r.contact} />}
                      <button type="button" className="btn btn--sm btn--secondary" onClick={() => setReview(reviewFor(r, r.worker.first_name))}>
                        <Icon name="star" size={16} filled={!!r.my_review} />
                        {r.my_review ? t('Ваш отзыв: {rating}', { rating: r.my_review.rating }) : t('Отзыв')}
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {respondOpen && (
        <Sheet
          title={t('Отклик')}
          onClose={() => setRespondOpen(false)}
          footer={
            !mainButtonSupported && (
              <button type="button" className="btn btn--primary btn--wide" onClick={submitResponse} disabled={busy === 'respond'}>
                {busy === 'respond' ? t('Отправляем…') : t('Отправить отклик')}
              </button>
            )
          }
        >
          <div className="respond-form">
            <div className="hint small">
              {t('{name} увидит ваше имя, рейтинг и «О себе». Контакты откроются обоим, когда вас примут.', { name: job.employer.first_name })}
            </div>
            <textarea
              className="input textarea"
              rows={4}
              maxLength={500}
              placeholder={t('Сообщение заказчику (необязательно): когда сможете приехать, есть ли опыт')}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
            <div className="hint small right">{message.length}/500</div>
            {!me.about && <div className="hint small">{t('Совет: расскажите о себе в профиле, так вас выберут охотнее.')}</div>}
            {respondError && <div className="form-error">{respondError}</div>}
          </div>
        </Sheet>
      )}

      {review && <ReviewSheet target={review} onClose={() => setReview(null)} onSaved={(rv) => savedReview(review.responseId, rv)} />}
      {reportOpen && (
        <ReportSheet
          jobId={job.id}
          jobTitle={job.title}
          onClose={() => setReportOpen(false)}
          onSent={() => {
            setReportOpen(false);
            toast(t('Жалоба отправлена. Спасибо, модераторы проверят заявку.'));
          }}
        />
      )}
      {help && <HelpSheet topic={help} onClose={() => setHelp(null)} />}
    </div>
  );
}
