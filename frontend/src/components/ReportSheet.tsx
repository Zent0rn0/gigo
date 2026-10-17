import { useState } from 'react';
import { api, errorText } from '../api';
import { haptic } from '../telegram';
import type { ReportReason } from '../types';
import { Icon, type IconName } from './Icon';
import { Sheet } from './Sheet';
import { t, N_ } from '../i18n';

const REASONS: { id: ReportReason; label: string; hint: string; icon: IconName }[] = [
  { id: 'scam', label: N_('Мошенничество'), hint: N_('Просят оплату, данные карты, коды из SMS'), icon: 'shield' },
  { id: 'spam', label: N_('Спам или реклама'), hint: N_('Не работа, а продажа или реклама'), icon: 'ban' },
  { id: 'rude', label: N_('Грубость'), hint: N_('Оскорбления, дискриминация'), icon: 'message' },
  { id: 'other', label: N_('Другое'), hint: N_('Опишите, что не так'), icon: 'help' },
];

const MAX = 500;

interface Props {
  jobId: number;
  jobTitle: string;
  onClose(): void;
  onSent(): void;
}

/** Жалоба на чужую заявку: POST /api/jobs/{id}/report. */
export function ReportSheet({ jobId, jobTitle, onClose, onSent }: Props) {
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (!reason) {
      setError(t('Выберите причину'));
      haptic('error');
      return;
    }
    if (reason === 'other' && !text.trim()) {
      setError(t('Коротко опишите, что не так'));
      haptic('error');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await api.reportJob(jobId, reason, text.trim() || null);
      haptic('success');
      onSent();
    } catch (e) {
      haptic('error');
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      title={t('Пожаловаться')}
      onClose={onClose}
      footer={
        <button type="button" className="btn btn--danger btn--wide" onClick={submit} disabled={busy}>
          <Icon name="flag" size={18} />
          {busy ? t('Отправляем…') : t('Отправить жалобу')}
        </button>
      }
    >
      <div className="report-form">
        <p className="hint small report-form__job">«{jobTitle}»</p>
        <div className="radio-list" role="radiogroup" aria-label={t('Причина')}>
          {REASONS.map((r) => (
            <label key={r.id} className={`radio-row${reason === r.id ? ' radio-row--on' : ''}`}>
              <input
                type="radio"
                name="report-reason"
                value={r.id}
                checked={reason === r.id}
                onChange={() => {
                  haptic('select');
                  setReason(r.id);
                  setError('');
                }}
              />
              <span className="radio-row__icon">
                <Icon name={r.icon} size={20} />
              </span>
              <span className="radio-row__text">
                <span className="radio-row__label">{t(r.label)}</span>
                <span className="hint small">{t(r.hint)}</span>
              </span>
            </label>
          ))}
        </div>
        <label className="field">
          <span className="field__label">{t('Подробности')} {reason === 'other' ? '' : t('(необязательно)')}</span>
          <textarea
            className="input textarea"
            rows={3}
            maxLength={MAX}
            placeholder={t('Что именно не так с заявкой')}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setError('');
            }}
          />
          <span className="hint small right">
            {text.length}/{MAX}
          </span>
        </label>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <p className="hint small">{t('Жалобу увидят модераторы. Заказчик не узнает, кто пожаловался.')}</p>
      </div>
    </Sheet>
  );
}
