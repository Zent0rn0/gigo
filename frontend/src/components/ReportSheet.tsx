import { useState } from 'react';
import { api, errorText } from '../api';
import { haptic } from '../telegram';
import type { ReportReason } from '../types';
import { Icon, type IconName } from './Icon';
import { Sheet } from './Sheet';

const REASONS: { id: ReportReason; label: string; hint: string; icon: IconName }[] = [
  { id: 'scam', label: 'Мошенничество', hint: 'Просят оплату, данные карты, коды из SMS', icon: 'shield' },
  { id: 'spam', label: 'Спам или реклама', hint: 'Не работа, а продажа или реклама', icon: 'ban' },
  { id: 'rude', label: 'Грубость', hint: 'Оскорбления, дискриминация', icon: 'message' },
  { id: 'other', label: 'Другое', hint: 'Опишите, что не так', icon: 'help' },
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
      setError('Выберите причину');
      haptic('error');
      return;
    }
    if (reason === 'other' && !text.trim()) {
      setError('Коротко опишите, что не так');
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
      title="Пожаловаться"
      onClose={onClose}
      footer={
        <button type="button" className="btn btn--danger btn--wide" onClick={submit} disabled={busy}>
          <Icon name="flag" size={18} />
          {busy ? 'Отправляем…' : 'Отправить жалобу'}
        </button>
      }
    >
      <div className="report-form">
        <p className="hint small report-form__job">«{jobTitle}»</p>
        <div className="radio-list" role="radiogroup" aria-label="Причина">
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
                <span className="radio-row__label">{r.label}</span>
                <span className="hint small">{r.hint}</span>
              </span>
            </label>
          ))}
        </div>
        <label className="field">
          <span className="field__label">Подробности {reason === 'other' ? '' : '(необязательно)'}</span>
          <textarea
            className="input textarea"
            rows={3}
            maxLength={MAX}
            placeholder="Что именно не так с заявкой"
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
        <p className="hint small">Жалобу увидят модераторы. Заказчик не узнает, кто пожаловался.</p>
      </div>
    </Sheet>
  );
}
