import type { ReactNode } from 'react';

export function EmptyState({ icon, title, text, action }: { icon: string; title: string; text?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      <div className="state__icon" aria-hidden="true">
        {icon}
      </div>
      <div className="state__title">{title}</div>
      {text && <div className="state__text">{text}</div>}
      {action}
    </div>
  );
}

export function ErrorState({ text, onRetry }: { text: string; onRetry(): void }) {
  return (
    <EmptyState
      icon="⚠️"
      title="Не удалось загрузить"
      text={text}
      action={
        <button type="button" className="btn btn--primary" onClick={onRetry}>
          Повторить
        </button>
      }
    />
  );
}

export function Spinner() {
  return <span className="spinner" role="status" aria-label="Загрузка" />;
}
