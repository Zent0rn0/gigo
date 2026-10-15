import { useEffect, useState } from 'react';
import { api, errorText } from '../api';
import { formatPay, formatWhen, jobState } from '../format';
import { haptic } from '../telegram';
import type { Job } from '../types';
import { Icon } from './Icon';
import { CategoryTile } from './JobCard';
import { Sheet } from './Sheet';
import { Spinner } from './States';
import { t } from '../i18n';

interface Props {
  workerId: number;
  workerName: string;
  /** Заявки, на которые уже приглашён. */
  invited: number[];
  onInvited(jobId: number): void;
  onCreate(): void;
  onClose(): void;
  toast(text: string): void;
}

/** Выбор своей открытой заявки, на которую позвать исполнителя. */
export function InviteSheet({ workerId, workerName, invited, onInvited, onCreate, onClose, toast }: Props) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    api
      .myJobs()
      .then((list) => setJobs(list.filter((j) => jobState(j) === 'open')))
      .catch((e) => setError(errorText(e)));
  }, []);

  const invite = async (job: Job) => {
    setBusy(job.id);
    try {
      await api.invite(job.id, workerId);
      haptic('success');
      onInvited(job.id);
      toast(t('Приглашение отправлено. {name} получит ссылку на заявку от бота.', { name: workerName }));
    } catch (e) {
      haptic('error');
      toast(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Sheet title={t('Пригласить: {name}', { name: workerName })} onClose={onClose}>
      {error && <div className="form-error">{error}</div>}
      {!error && jobs == null && (
        <div className="center pad">
          <Spinner />
        </div>
      )}
      {jobs?.length === 0 && (
        <div className="invite-empty">
          <p className="hint">{t('Открытых заявок нет. Создайте заявку, потом возвращайтесь сюда.')}</p>
          <button type="button" className="btn btn--primary btn--wide" onClick={onCreate}>
            <Icon name="plus" size={18} />
            {t('Создать заявку')}
          </button>
        </div>
      )}
      {!!jobs?.length && (
        <div className="invite-list">
          {jobs.map((j) => {
            const done = invited.includes(j.id);
            const sub = [formatPay(j), formatWhen(j)].filter(Boolean).join(' · ');
            return (
              <div key={j.id} className="invite-row">
                <CategoryTile id={j.category} size={36} />
                <span className="invite-row__text">
                  <span className="invite-row__title">{j.title}</span>
                  {sub && <span className="hint small">{sub}</span>}
                </span>
                {done ? (
                  <span className="status status--ok">
                    <Icon name="check" size={14} strokeWidth={2.4} />
                    {t('Приглашён')}
                  </span>
                ) : (
                  <button type="button" className="btn btn--sm btn--primary" disabled={busy != null} onClick={() => invite(j)}>
                    {busy === j.id ? '…' : t('Позвать')}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Sheet>
  );
}
