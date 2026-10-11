import type { Role } from '../types';

export type Tab = 'feed' | 'map' | 'responses' | 'my' | 'create' | 'profile';

export const ROLE_TABS: Record<Role, Tab[]> = {
  worker: ['feed', 'map', 'responses', 'profile'],
  employer: ['my', 'create', 'profile'],
};

const svg = (d: JSX.Element) => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    {d}
  </svg>
);

const TABS: Record<Tab, { label: string; icon: JSX.Element }> = {
  feed: { label: 'Лента', icon: svg(<path d="M4 6h16M4 12h16M4 18h10" />) },
  map: {
    label: 'Карта',
    icon: svg(
      <>
        <path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" />
        <circle cx="12" cy="9.5" r="2.5" />
      </>,
    ),
  },
  responses: {
    label: 'Отклики',
    icon: svg(
      <>
        <rect x="3.5" y="5.5" width="17" height="13" rx="2" />
        <path d="M4 7l8 6 8-6" />
      </>,
    ),
  },
  my: {
    label: 'Мои заявки',
    icon: svg(
      <>
        <rect x="5" y="4" width="14" height="17" rx="2" />
        <path d="M9 9h6M9 13h6M9 17h3" />
      </>,
    ),
  },
  create: {
    label: 'Создать',
    icon: svg(
      <>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 8v8M8 12h8" />
      </>,
    ),
  },
  profile: {
    label: 'Профиль',
    icon: svg(
      <>
        <circle cx="12" cy="8.5" r="3.5" />
        <path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5" />
      </>,
    ),
  },
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
          {TABS[id].icon}
          <span>{TABS[id].label}</span>
        </button>
      ))}
    </nav>
  );
}
