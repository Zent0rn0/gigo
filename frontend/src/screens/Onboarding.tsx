import { useState } from 'react';
import { api, errorText } from '../api';
import { HelpSheet } from '../components/HelpSheet';
import { Icon, type IconName } from '../components/Icon';
import { Logo } from '../components/Logo';
import { Sheet } from '../components/Sheet';
import { LANGUAGES, N_, setLang, t, useLang, type Lang } from '../i18n';
import { haptic } from '../telegram';
import type { Me, Role } from '../types';

const CHOICES: { role: Role; icon: IconName; title: string; text: string; next: string }[] = [
  {
    role: 'worker',
    icon: 'briefcase',
    title: N_('Ищу подработку'),
    text: N_('Заявки рядом с оплатой в час. Откликайтесь в один тап.'),
    next: N_('Дальше — лента и карта заявок'),
  },
  {
    role: 'employer',
    icon: 'users',
    title: N_('Ищу людей'),
    text: N_('Опишите задачу — исполнители откликнутся за минуты.'),
    next: N_('Дальше — первая заявка, займёт пару минут'),
  },
];

const STEPS: { icon: IconName; text: string }[] = [
  { icon: 'clipboard', text: N_('Заказчик публикует заявку') },
  { icon: 'send', text: N_('Исполнитель откликается') },
  { icon: 'message', text: N_('Договариваетесь в Telegram') },
];

export function Onboarding({ me, city, onDone }: { me: Me; city: string; onDone(me: Me): void }) {
  const [busy, setBusy] = useState<Role | null>(null);
  const [error, setError] = useState('');
  const [help, setHelp] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const lang = useLang();
  const current = LANGUAGES.find((l) => l.id === lang) ?? LANGUAGES[0];

  const pickLang = async (next: Lang) => {
    haptic('select');
    setLangOpen(false);
    if (next === lang) return;
    try {
      await api.updateMe({ lang: next });
    } catch (e) {
      console.error('[gigo] язык не сохранился на сервере', e);
    }
    await setLang(next);
  };

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
        <button
          type="button"
          className="hero__pill"
          style={{ left: 14, right: 'auto', background: 'none', font: 'inherit', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
          aria-label={t('Язык')}
          aria-haspopup="dialog"
          onClick={() => setLangOpen(true)}
        >
          {current.flag} {current.name}
        </button>
        <span className="hero__pill">{city}</span>
        <Logo height={48} />
        <p className="onboarding__tagline">{t('Подработка рядом')}</p>
        <span className="hero__badge">{t('бесплатно · отклик в один тап')}</span>
        <ol className="steps" aria-label={t('Как это работает')}>
          {STEPS.map((s, i) => (
            <li key={i} className="steps__item">
              <span className="steps__icon">
                <Icon name={s.icon} size={20} />
              </span>
              <span className="steps__text">{t(s.text)}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="onboarding__choices">
        <h1 className="onboarding__title">{me.first_name ? t('{name}, что вы ищете?', { name: me.first_name }) : t('Что вы ищете?')}</h1>
        {CHOICES.map((c) => (
          <button key={c.role} type="button" className="role-card" disabled={!!busy} onClick={() => choose(c.role)}>
            <span className={`role-card__icon role-card__icon--${c.role}`}>
              <Icon name={c.icon} size={26} />
            </span>
            <span className="role-card__text">
              <span className="role-card__title">{busy === c.role ? t('Секунду…') : t(c.title)}</span>
              <span className="role-card__desc">{t(c.text)}</span>
              <span className="role-card__next">{t(c.next)}</span>
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
          {t('Бесплатно. Мы не берём денег и никогда не просим данные карт.')}
        </p>
        <p className="hint small center">
          {t('Роль можно сменить в профиле.')}{' '}
          <button type="button" className="link-btn" onClick={() => setHelp(true)}>
            {t('Как это работает')}
          </button>
        </p>
      </div>
      {help && <HelpSheet onClose={() => setHelp(false)} />}
      {langOpen && (
        <Sheet title={t('Язык')} onClose={() => setLangOpen(false)}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {LANGUAGES.map((l) => (
              <button
                key={l.id}
                type="button"
                className="menu-row"
                lang={l.id}
                aria-current={l.id === lang ? 'true' : undefined}
                onClick={() => pickLang(l.id)}
              >
                <span className="menu-row__icon" aria-hidden="true" style={{ fontSize: 20 }}>
                  {l.flag}
                </span>
                <span className="menu-row__text">
                  <span className="menu-row__title">{l.name}</span>
                </span>
                {l.id === lang && <Icon name="check" size={20} />}
              </button>
            ))}
          </div>
        </Sheet>
      )}
    </div>
  );
}
