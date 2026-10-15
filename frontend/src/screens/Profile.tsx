import { useEffect, useState } from 'react';
import { api, errorText } from '../api';
import { HelpSheet, type HelpTopic } from '../components/HelpSheet';
import { Icon, categoryIcon, type IconName } from '../components/Icon';
import { Logo } from '../components/Logo';
import { Sheet } from '../components/Sheet';
import { Avatar, Stars } from '../components/ui';
import { plural } from '../format';
import { LANGUAGES, N_, setLang, t, useLang, type Lang } from '../i18n';
import { haptic } from '../telegram';
import type { Me, Meta, Role } from '../types';

interface Props {
  me: Me;
  meta: Meta;
  onMeChange(me: Me): void;
  onSwitchRole(role: Role): Promise<void>;
  onOpenUser(id: number): void;
  onOpenSubs(): void;
  toast(text: string): void;
}

const MAX_ABOUT = 500;

const ROLES: { id: Role; label: string; icon: IconName }[] = [
  { id: 'worker', label: N_('Исполнитель'), icon: 'briefcase' },
  { id: 'employer', label: N_('Заказчик'), icon: 'users' },
];

function MenuRow({ icon, glyph, title, text, onClick }: { icon?: IconName; glyph?: string; title: string; text: string; onClick(): void }) {
  return (
    <button type="button" className="menu-row" onClick={onClick}>
      <span className="menu-row__icon" aria-hidden={glyph ? true : undefined}>
        {glyph ? <span style={{ fontSize: 20, lineHeight: 1 }}>{glyph}</span> : icon && <Icon name={icon} size={20} />}
      </span>
      <span className="menu-row__text">
        <span className="menu-row__title">{title}</span>
        <span className="hint small">{text}</span>
      </span>
      <Icon name="chevron-right" size={20} className="user-row__chev" />
    </button>
  );
}

export function Profile({ me, meta, onMeChange, onSwitchRole, onOpenUser, onOpenSubs, toast }: Props) {
  const [about, setAbout] = useState(me.about ?? '');
  const [saving, setSaving] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [help, setHelp] = useState<HelpTopic | null>(null);
  const lang = useLang();
  const curLang = LANGUAGES.find((l) => l.id === lang) ?? LANGUAGES[0];
  const [langOpen, setLangOpen] = useState(false);
  const [langBusy, setLangBusy] = useState(false);
  useEffect(() => setAbout(me.about ?? ''), [me.about]);
  const dirty = about.trim() !== (me.about ?? '').trim();

  const save = async () => {
    setSaving(true);
    try {
      const upd = await api.updateMe({ about: about.trim() });
      haptic('success');
      onMeChange(upd);
      toast(t('Сохранено'));
    } catch (e) {
      haptic('error');
      toast(errorText(e));
    } finally {
      setSaving(false);
    }
  };

  // навыки сохраняются сразу при нажатии; на экране — без ожидания сервера
  const [skills, setSkills] = useState<string[]>(me.skills ?? []);
  useEffect(() => setSkills(me.skills ?? []), [me.skills]);
  const toggleSkill = async (id: string) => {
    haptic('select');
    const prev = skills;
    const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
    setSkills(next);
    try {
      onMeChange(await api.updateMe({ skills: next }));
    } catch (e) {
      setSkills(prev);
      haptic('error');
      toast(errorText(e));
    }
  };

  // язык сохраняется на сервере (бот пишет на нём же), затем всё приложение перерисовывается на новом языке
  const chooseLang = async (next: Lang) => {
    if (langBusy) return;
    if (next === lang) {
      setLangOpen(false);
      return;
    }
    haptic('select');
    setLangBusy(true);
    try {
      onMeChange(await api.updateMe({ lang: next }));
    } catch (e) {
      haptic('error');
      toast(errorText(e));
      setLangBusy(false);
      return;
    }
    setLangOpen(false);
    setLangBusy(false);
    await setLang(next);
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
      <header className="profile-head hero">
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
              <span className="hint small">{t('Отзывов пока нет')}</span>
            )}
          </div>
        </div>
      </header>

      <section className="panel">
        <div className="field__label" id="role-label">
          {t('Я сейчас')}
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
              {t(r.label)}
            </button>
          ))}
        </div>
        <div className="hint small">
          {me.role === 'employer' ? t('Создаёте заявки и выбираете исполнителей.') : t('Смотрите заявки и откликаетесь.')}{' '}
          {t('Роль можно менять в любой момент.')}
        </div>
      </section>

      {me.role === 'worker' && (
        <section className="panel">
          <div className="field__label">{t('Что умею')}</div>
          <div className="chips chips--wrap" role="group" aria-label={t('Что умею')}>
            {meta.categories.map((c) => {
              const on = skills.includes(c.id);
              return (
                <button key={c.id} type="button" className={`chip${on ? ' chip--on' : ''}`} aria-pressed={on} onClick={() => toggleSkill(c.id)}>
                  <Icon name={categoryIcon(c.id)} size={16} />
                  {c.label}
                </button>
              );
            })}
          </div>
          <div className="hint small">{t('Заказчики увидят это в отклике и найдут вас в каталоге исполнителей, а в ленте появится фильтр «Только мои навыки».')}</div>
        </section>
      )}

      <section className="panel">
        <label className="field">
          <span className="field__label">{t('О себе')}</span>
          <textarea
            className="input textarea"
            rows={4}
            maxLength={MAX_ABOUT}
            placeholder={
              me.role === 'employer'
                ? t('Кто вы и какие задачи обычно бывают')
                : t('Опыт, что умеете, есть ли машина или инструмент. Заказчик увидит это в отклике.')
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
            {saving ? t('Сохраняем…') : t('Сохранить')}
          </button>
        </div>
      </section>

      <section className="panel panel--menu">
        <MenuRow glyph={curLang.flag} title={t('Язык')} text={curLang.name} onClick={() => setLangOpen(true)} />
      </section>

      <section className="panel panel--menu">
        <MenuRow icon="user" title={t('Мой профиль')} text={t('Так вас видят другие: рейтинг и отзывы')} onClick={() => onOpenUser(me.id)} />
        {me.role === 'worker' && (
          <MenuRow icon="bell" title={t('Подписки на заявки')} text={t('Бот пришлёт новые заявки под ваш фильтр')} onClick={onOpenSubs} />
        )}
        <MenuRow icon="help" title={t('Как это работает')} text={t('Отклики, контакты, отзывы')} onClick={() => setHelp('how')} />
        <MenuRow icon="shield" title={t('Безопасность')} text={t('Не платите вперёд и не передавайте карты')} onClick={() => setHelp('safety')} />
        <MenuRow icon="flag" title={t('Как пожаловаться')} text={t('На заявку или заказчика')} onClick={() => setHelp('report')} />
      </section>

      <footer className="app-foot">
        <Logo height={22} />
        <span className="hint small">{t('Альфа-версия · подработка в Москве')}</span>
      </footer>

      {help && <HelpSheet topic={help} onClose={() => setHelp(null)} />}
      {langOpen && (
        <Sheet title={t('Язык')} onClose={() => setLangOpen(false)}>
          <div role="radiogroup" aria-label={t('Язык')} style={{ display: 'flex', flexDirection: 'column', paddingBottom: 'calc(12px + var(--safe-bottom))' }}>
            {LANGUAGES.map((l) => (
              <button
                key={l.id}
                type="button"
                role="radio"
                aria-checked={l.id === lang}
                lang={l.id}
                className="menu-row"
                disabled={langBusy}
                onClick={() => chooseLang(l.id)}
              >
                <span className="menu-row__icon" aria-hidden="true">
                  <span style={{ fontSize: 20, lineHeight: 1 }}>{l.flag}</span>
                </span>
                <span className="menu-row__text">
                  <span className="menu-row__title">{l.name}</span>
                </span>
                {l.id === lang && <Icon name="check" size={20} className="user-row__chev" />}
              </button>
            ))}
          </div>
        </Sheet>
      )}
    </div>
  );
}
