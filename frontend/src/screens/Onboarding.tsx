import { useState } from 'react';
import { api, errorText } from '../api';
import { HelpSheet } from '../components/HelpSheet';
import { Icon, type IconName } from '../components/Icon';
import { Logo } from '../components/Logo';
import { haptic } from '../telegram';
import type { Me, Role } from '../types';

const CHOICES: { role: Role; icon: IconName; title: string; text: string; next: string }[] = [
  {
    role: 'worker',
    icon: 'briefcase',
    title: 'Ищу подработку',
    text: 'Заявки рядом с оплатой в час. Откликайтесь в один тап.',
    next: 'Дальше — лента и карта заявок',
  },
  {
    role: 'employer',
    icon: 'users',
    title: 'Ищу людей',
    text: 'Опишите задачу — исполнители откликнутся за минуты.',
    next: 'Дальше — первая заявка, займёт пару минут',
  },
];

const STEPS: { icon: IconName; text: string }[] = [
  { icon: 'clipboard', text: 'Заказчик публикует заявку' },
  { icon: 'send', text: 'Исполнитель откликается' },
  { icon: 'message', text: 'Договариваетесь в Telegram' },
];

export function Onboarding({ me, city, onDone }: { me: Me; city: string; onDone(me: Me): void }) {
  const [busy, setBusy] = useState<Role | null>(null);
  const [error, setError] = useState('');
  const [help, setHelp] = useState(false);

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
      <div className="onboarding__head hero">
        <span className="hero__pill">{city}</span>
        <Logo height={48} />
        <p className="onboarding__tagline">Подработка рядом</p>
        <span className="hero__badge">бесплатно · отклик в один тап</span>
        <ol className="steps" aria-label="Как это работает">
          {STEPS.map((s, i) => (
            <li key={i} className="steps__item">
              <span className="steps__icon">
                <Icon name={s.icon} size={20} />
              </span>
              <span className="steps__text">{s.text}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="onboarding__choices">
        <h1 className="onboarding__title">{me.first_name ? `${me.first_name}, что вы ищете?` : 'Что вы ищете?'}</h1>
        {CHOICES.map((c) => (
          <button key={c.role} type="button" className="role-card" disabled={!!busy} onClick={() => choose(c.role)}>
            <span className={`role-card__icon role-card__icon--${c.role}`}>
              <Icon name={c.icon} size={26} />
            </span>
            <span className="role-card__text">
              <span className="role-card__title">{busy === c.role ? 'Секунду…' : c.title}</span>
              <span className="role-card__desc">{c.text}</span>
              <span className="role-card__next">{c.next}</span>
            </span>
            {busy === c.role ? <span className="spinner" aria-hidden="true" /> : <Icon name="chevron-right" size={22} className="role-card__chev" />}
          </button>
        ))}
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
      </div>

      <div className="onboarding__foot">
        <p className="hint small center">
          <Icon name="shield" size={16} />
          Бесплатно. Мы не берём денег и никогда не просим данные карт.
        </p>
        <p className="hint small center">
          Роль можно сменить в профиле.{' '}
          <button type="button" className="link-btn" onClick={() => setHelp(true)}>
            Как это работает
          </button>
        </p>
      </div>
      {help && <HelpSheet onClose={() => setHelp(false)} />}
    </div>
  );
}
