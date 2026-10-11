import type { Role } from '../types';
import { Icon, type IconName } from './Icon';

export type Tab = 'feed' | 'map' | 'responses' | 'my' | 'create' | 'workers' | 'profile';

export const ROLE_TABS: Record<Role, Tab[]> = {
  worker: ['feed', 'map', 'responses', 'profile'],
  employer: ['my', 'create', 'workers', 'profile'],
};

const TABS: Record<Tab, { label: string; icon: IconName }> = {
  feed: { label: 'Лента', icon: 'feed' },
  map: { label: 'Карта', icon: 'map' },
  responses: { label: 'Отклики', icon: 'inbox' },
  my: { label: 'Мои заявки', icon: 'clipboard' },
  create: { label: 'Создать', icon: 'plus-circle' },
  workers: { label: 'Исполнители', icon: 'users' },
  profile: { label: 'Профиль', icon: 'user' },
};

export function TabBar({ tabs, tab, onChange }: { tabs: Tab[]; tab: Tab; onChange(t: Tab): void }) {
  return (
    <nav className="tabbar" aria-label="Разделы">
      {tabs.map((id) => (
        <button
          key={id}
          type="button"
          className={`tabbar__item${tab === id ? ' tabbar__item--on' : ''}`}
          aria-current={tab === id ? 'page' : undefined}
          onClick={() => onChange(id)}
        >
          <span className="tabbar__icon">
            <Icon name={TABS[id].icon} size={24} strokeWidth={tab === id ? 2.2 : 1.9} />
          </span>
          <span>{TABS[id].label}</span>
        </button>
      ))}
    </nav>
  );
}
