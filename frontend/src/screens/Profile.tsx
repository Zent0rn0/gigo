import { useEffect, useState } from 'react';
import { api, errorText } from '../api';
import { HelpSheet, type HelpTopic } from '../components/HelpSheet';
import { Icon, type IconName } from '../components/Icon';
import { Logo } from '../components/Logo';
import { Avatar, Stars } from '../components/ui';
import { plural } from '../format';
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

const ROLES: { id: Role; label: string; icon: IconName }[] = [
  { id: 'worker', label: 'Исполнитель', icon: 'briefcase' },
  { id: 'employer', label: 'Заказчик', icon: 'users' },
];

function MenuRow({ icon, title, text, onClick }: { icon: IconName; title: string; text: string; onClick(): void }) {
  return (
    <button type="button" className="menu-row" onClick={onClick}>
      <span className="menu-row__icon">
        <Icon name={icon} size={20} />
      </span>
      <span className="menu-row__text">
        <span className="menu-row__title">{title}</span>
        <span className="hint small">{text}</span>
      </span>
      <Icon name="chevron-right" size={20} className="user-row__chev" />
    </button>
  );
}

export function Profile({ me, onMeChange, onSwitchRole, onOpenUser, onOpenSubs, toast }: Props) {
  const [about, setAbout] = useState(me.about ?? '');
  const [saving, setSaving] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [help, setHelp] = useState<HelpTopic | null>(null);
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
          <div className="profile-head__rating">
            {me.rating != null && me.reviews_count > 0 ? (
              <>
                <b>{me.rating.toFixed(1).replace('.', ',')}</b>
                <Stars value={Math.round(me.rating)} size="sm" />
                <span className="hint small">
                  {me.reviews_count} {plural(me.reviews_count, ['отзыв', 'отзыва', 'отзывов'])}
                </span>
              </>
            ) : (
              <span className="hint small">Отзывов пока нет</span>
            )}
          </div>
        </div>
      </header>

      <section className="panel">
        <div className="field__label" id="role-label">
          Я сейчас
        </div>
        <div className="segmented" role="radiogroup" aria-labelledby="role-label">
          {ROLES.map((r) => (
            <button
              key={r.id}
              type="button"
              role="radio"
              aria-checked={me.role === r.id}
              className={`segmented__item${me.role === r.id ? ' segmented__item--on' : ''}`}
              disabled={switching}
              onClick={() => switchTo(r.id)}
            >
              <Icon name={r.icon} size={18} />
              {r.label}
            </button>
          ))}
        </div>
        <div className="hint small">
          {me.role === 'employer' ? 'Создаёте заявки и выбираете исполнителей.' : 'Смотрите заявки и откликаетесь.'} Роль можно менять в
          любой момент.
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

      <section className="panel panel--menu">
        <MenuRow icon="user" title="Мой профиль" text="Так вас видят другие: рейтинг и отзывы" onClick={() => onOpenUser(me.id)} />
        {me.role === 'worker' && (
          <MenuRow icon="bell" title="Подписки на заявки" text="Бот пришлёт новые заявки под ваш фильтр" onClick={onOpenSubs} />
        )}
        <MenuRow icon="help" title="Как это работает" text="Отклики, контакты, отзывы" onClick={() => setHelp('how')} />
        <MenuRow icon="shield" title="Безопасность" text="Не платите вперёд и не передавайте карты" onClick={() => setHelp('safety')} />
        <MenuRow icon="flag" title="Как пожаловаться" text="На заявку или заказчика" onClick={() => setHelp('report')} />
      </section>

      <footer className="app-foot">
        <Logo height={22} />
        <span className="hint small">Альфа-версия · подработка в Москве</span>
      </footer>

      {help && <HelpSheet topic={help} onClose={() => setHelp(null)} />}
    </div>
  );
}
