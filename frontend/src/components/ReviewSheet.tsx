import { useState } from 'react';
import { api, errorText } from '../api';
import { haptic } from '../telegram';
import type { ReviewMine } from '../types';
import { Sheet } from './Sheet';
import { Stars } from './ui';
import { t, N_ } from '../i18n';

export interface ReviewTarget {
  responseId: number;
  name: string;
  jobTitle: string;
  initial: ReviewMine | null;
}

const HINTS = ['', N_('Плохо'), N_('Так себе'), N_('Нормально'), N_('Хорошо'), N_('Отлично')];

interface Props {
  target: ReviewTarget;
  onClose(): void;
  onSaved(review: ReviewMine): void;
}

export function ReviewSheet({ target, onClose, onSaved }: Props) {
  const [rating, setRating] = useState(target.initial?.rating ?? 0);
  const [text, setText] = useState(target.initial?.text ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (!rating) {
      setError(t('Поставьте оценку от 1 до 5'));
      return;
    }
    setBusy(true);
    setError('');
    try {
      const r = await api.review({ response_id: target.responseId, rating, text: text.trim() || null });
      haptic('success');
      onSaved(r);
    } catch (e) {
      haptic('error');
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet
      title={target.initial ? t('Изменить отзыв') : t('Отзыв')}
      onClose={onClose}
      footer={
        <button type="button" className="btn btn--primary btn--wide" onClick={submit} disabled={busy}>
          {busy ? t('Сохраняем…') : t('Отправить отзыв')}
        </button>
      }
    >
      <div className="review-form">
        <div className="review-form__who">
          <b>{target.name}</b>
          <div className="hint small">{target.jobTitle}</div>
        </div>
        <Stars value={rating} onChange={(v) => { haptic('select'); setRating(v); setError(''); }} size="lg" />
        <div className="hint small review-form__hint">{rating ? t(HINTS[rating]) : t('Как всё прошло?')}</div>
        <textarea
          className="input textarea"
          rows={3}
          maxLength={1000}
          placeholder={t('Пара слов о работе (необязательно)')}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {error && <div className="form-error">{error}</div>}
      </div>
    </Sheet>
  );
}
