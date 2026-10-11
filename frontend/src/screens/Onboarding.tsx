import { useState } from 'react';
import { api, errorText } from '../api';
import { haptic } from '../telegram';
import type { Me, Role } from '../types';

const CHOICES: { role: Role; icon: string; title: string; text: string }[] = [
  { role: 'worker', icon: '🙋', title: 'Ищу подработку', text: 'Смотрю заявки рядом и откликаюсь' },
  { role: 'employer', icon: '📋', title: 'Ищу людей', text: 'Публикую заявку и выбираю исполнителей' },
];

export function Onboarding({ me, onDone }: { me: Me; onDone(me: Me): void }) {
  const [busy, setBusy] = useState<Role | null>(null);
  const [error, setError] = useState('');

  const choose = async (role: Role) => {
    haptic('select');
    setBusy(role);
    setError('');
    try {
      const upd = await api.updateMe({ role });
      haptic('success');
      onDone(upd);
    } catch (e) {
      haptic('error');
      setError(errorText(e));
      setBusy(null);
    }
  };

  return (
    <div className="onboarding">
      <div className="onboarding__head">
        <div className="onboarding__logo" aria-hidden="true">
          ⚡
        </div>
        <h1 className="onboarding__title">{me.first_name ? `${me.first_name}, кто вы?` : 'Кто вы?'}</h1>
        <p className="hint">Подработка в Москве без посредников. Роль можно сменить в профиле.</p>
      </div>
      <div className="onboarding__choices">
        {CHOICES.map((c) => (
          <button key={c.role} type="button" className="role-card" disabled={!!busy} onClick={() => choose(c.role)}>
            <span className="role-card__icon" aria-hidden="true">
              {c.icon}
            </span>
            <span className="role-card__text">
              <span className="role-card__title">{busy === c.role ? 'Секунду…' : c.title}</span>
              <span className="hint">{c.text}</span>
            </span>
            <span className="role-card__chev" aria-hidden="true">
              ›
            </span>
          </button>
        ))}
      </div>
      {error && <div className="form-error">{error}</div>}
    </div>
  );
}
