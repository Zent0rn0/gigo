import { useEffect, useState } from 'react';
import { api, errorText } from '../api';
import { Avatar } from '../components/ui';
import { formatRating } from '../format';
import { haptic } from '../telegram';
import type { Me, Role } from '../types';

interface Props {
  me: Me;
  onMeChange(me: Me): void;
  onSwitchRole(role: Role): Promise<void>;
  onOpenUser(id: number): void;
  onOpenSubs(): void;
  toast(text: string): void;
}

const MAX_ABOUT = 500;

export function Profile({ me, onMeChange, onSwitchRole, onOpenUser, onOpenSubs, toast }: Props) {
  const [about, setAbout] = useState(me.about ?? '');
  const [saving, setSaving] = useState(false);
  const [switching, setSwitching] = useState(false);
  useEffect(() => setAbout(me.about ?? ''), [me.about]);
  const dirty = about.trim() !== (me.about ?? '').trim();

  const save = async () => {
    setSaving(true);
    try {
      const upd = await api.updateMe({ about: about.trim() });
      haptic('success');
      onMeChange(upd);
      toast('Сохранено');
    } catch (e) {
      haptic('error');
      toast(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  const switchTo = async (role: Role) => {
    if (role === me.role || switching) return;
    setSwitching(true);
    try {
      await onSwitchRole(role);
    } finally {
      setSwitching(false);
    }
  };

  return (
    <div className="screen">
      <header className="profile-head">
        <Avatar name={me.first_name} size={64} />
        <div className="profile-head__text">
          <h1 className="app-title">{me.first_name}</h1>
          {me.username && <div className="hint">@{me.username}</div>}
          <button type="button" className="link-btn" onClick={() => onOpenUser(me.id)}>
            {formatRating(me.rating, me.reviews_count)} · мой профиль ›
          </button>
        </div>
      </header>

      <section className="panel">
        <div className="field__label">Я сейчас</div>
        <div className="segmented" role="radiogroup" aria-label="Роль">
          {(
            [
              ['worker', '🙋 Исполнитель'],
              ['employer', '📋 Заказчик'],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={me.role === id}
              className={`segmented__item${me.role === id ? ' segmented__item--on' : ''}`}
              disabled={switching}
              onClick={() => switchTo(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="hint small">
          {me.role === 'employer' ? 'Создаёте заявки и выбираете исполнителей.' : 'Смотрите заявки и откликаетесь.'}
        </div>
      </section>

      <section className="panel">
        <label className="field">
          <span className="field__label">О себе</span>
          <textarea
            className="input textarea"
            rows={4}
            maxLength={MAX_ABOUT}
            placeholder={
              me.role === 'employer'
                ? 'Кто вы и какие задачи обычно бывают'
                : 'Опыт, что умеете, есть ли машина или инструмент. Заказчик увидит это в отклике.'
            }
            value={about}
            onChange={(e) => setAbout(e.target.value)}
          />
        </label>
        <div className="row-between">
          <span className="hint small">
            {about.length}/{MAX_ABOUT}
          </span>
          <button type="button" className="btn btn--sm btn--primary" onClick={save} disabled={!dirty || saving}>
            {saving ? 'Сохраняем…' : 'Сохранить'}
          </button>
        </div>
      </section>

      {me.role === 'worker' && (
        <section className="panel panel--link">
          <button type="button" className="menu-row" onClick={onOpenSubs}>
            <span aria-hidden="true">🔔</span>
            <span className="menu-row__text">
              <span>Подписки на заявки</span>
              <span className="hint small">Бот пришлёт новые заявки под ваш фильтр</span>
            </span>
            <span className="user-row__chev" aria-hidden="true">
              ›
            </span>
          </button>
        </section>
      )}
    </div>
  );
}
