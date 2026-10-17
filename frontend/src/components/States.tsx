import type { ReactNode } from 'react';
import { Icon, type IconName } from './Icon';
import { useOnReconnect } from '../network';
import { t } from '../i18n';

export function EmptyState({
  icon,
  title,
  text,
  action,
  tone = 'neutral',
}: {
  icon: IconName;
  title: string;
  text?: ReactNode;
  action?: ReactNode;
  tone?: 'neutral' | 'danger' | 'brand';
}) {
  return (
    <div className="state">
      <div className={`state__icon state__icon--${tone}`}>
        <Icon name={icon} size={30} />
      </div>
      <div className="state__title">{title}</div>
      {text && <div className="state__text">{text}</div>}
      {action}
    </div>
  );
}

export function ErrorState({ text, onRetry }: { text: string; onRetry(): void }) {
  useOnReconnect(onRetry);
  return (
    <EmptyState
      icon="alert"
      tone="danger"
      title={t('Не удалось загрузить')}
      text={text}
      action={
        <button type="button" className="btn btn--primary" onClick={onRetry}>
          <Icon name="refresh" size={18} />
          {t('Повторить')}
        </button>
      }
    />
  );
}

export function Spinner() {
  return <span className="spinner" role="status" aria-label={t('Загрузка')} />;
}
