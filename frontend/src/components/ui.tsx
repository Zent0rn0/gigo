import { useState, type ReactNode } from 'react';
import { formatRating, initial, type Tone } from '../format';
import { openContact } from '../telegram';
import type { Contact, UserStub } from '../types';

export function StatusChip({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`status status--${tone}`}>{children}</span>;
}

export function Avatar({ name, size = 40 }: { name: string; size?: number }) {
  // цвет от имени, чтобы у разных людей аватарки различались
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return (
    <span className="avatar" style={{ width: size, height: size, fontSize: size * 0.42, background: `hsl(${h} 55% 55%)` }} aria-hidden="true">
      {initial(name)}
    </span>
  );
}

/** Строка «аватар · имя · рейтинг», по нажатию — профиль. */
export function UserRow({ user, caption, onOpen, right }: { user: UserStub; caption?: string; onOpen?(id: number): void; right?: ReactNode }) {
  const body = (
    <>
      <Avatar name={user.first_name} />
      <span className="user-row__text">
        <span className="user-row__name">{user.first_name}</span>
        <span className="hint small">
          {caption ? `${caption} · ` : ''}
          {formatRating(user.rating, user.reviews_count)}
        </span>
      </span>
    </>
  );
  return (
    <div className="user-row">
      {onOpen ? (
        <button type="button" className="user-row__main" onClick={() => onOpen(user.id)}>
          {body}
          <span className="user-row__chev" aria-hidden="true">
            ›
          </span>
        </button>
      ) : (
        <div className="user-row__main">{body}</div>
      )}
      {right}
    </div>
  );
}

export function ContactButton({ contact, wide }: { contact: Contact; wide?: boolean }) {
  return (
    <button
      type="button"
      className={`btn btn--primary${wide ? ' btn--wide' : ' btn--sm'}`}
      title={contact.username ? `@${contact.username}` : contact.first_name}
      onClick={() => openContact(contact.url)}
    >
      💬 Написать{wide ? ` ${contact.username ? `@${contact.username}` : contact.first_name}` : ''}
    </button>
  );
}

export function Stars({ value, onChange, size = 'md' }: { value: number; onChange?(v: number): void; size?: 'sm' | 'md' | 'lg' }) {
  return (
    <span className={`stars stars--${size}`} role={onChange ? 'radiogroup' : undefined} aria-label={`Оценка ${value} из 5`}>
      {[1, 2, 3, 4, 5].map((n) =>
        onChange ? (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={value === n}
            aria-label={`${n}`}
            className={`star${n <= value ? ' star--on' : ''}`}
            onClick={() => onChange(n)}
          >
            ★
          </button>
        ) : (
          <span key={n} className={`star${n <= value ? ' star--on' : ''}`} aria-hidden="true">
            ★
          </span>
        ),
      )}
    </span>
  );
}

/** Кнопка с подтверждением вторым нажатием (без системных диалогов). */
export function ConfirmButton({
  label,
  confirm,
  busy,
  onConfirm,
  className = 'btn btn--secondary btn--wide',
}: {
  label: string;
  confirm: string;
  busy?: boolean;
  onConfirm(): void;
  className?: string;
}) {
  const [asking, setAsking] = useState(false);
  if (!asking)
    return (
      <button type="button" className={className} onClick={() => setAsking(true)} disabled={busy}>
        {label}
      </button>
    );
  return (
    <div className="confirm">
      <span className="confirm__q">{confirm}</span>
      <div className="row-gap">
        <button type="button" className="btn btn--sm btn--secondary" onClick={() => setAsking(false)}>
          Нет
        </button>
        <button
          type="button"
          className="btn btn--sm btn--danger"
          onClick={() => {
            setAsking(false);
            onConfirm();
          }}
        >
          Да
        </button>
      </div>
    </div>
  );
}
