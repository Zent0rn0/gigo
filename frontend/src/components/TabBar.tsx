export type Tab = 'feed' | 'map' | 'subs';

const TABS: { id: Tab; label: string; icon: JSX.Element }[] = [
  {
    id: 'feed',
    label: 'Лента',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M4 6h16M4 12h16M4 18h10" />
      </svg>
    ),
  },
  {
    id: 'map',
    label: 'Карта',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" />
        <circle cx="12" cy="9.5" r="2.5" />
      </svg>
    ),
  },
  {
    id: 'subs',
    label: 'Подписки',
    icon: (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15L6 16z" />
        <path d="M10 20.5a2.2 2.2 0 0 0 4 0" />
      </svg>
    ),
  },
];

export function TabBar({ tab, onChange }: { tab: Tab; onChange(t: Tab): void }) {
  return (
    <nav className="tabbar" aria-label="Разделы">
      {TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          className={`tabbar__item${tab === t.id ? ' tabbar__item--on' : ''}`}
          aria-current={tab === t.id ? 'page' : undefined}
          onClick={() => onChange(t.id)}
        >
          {t.icon}
          <span>{t.label}</span>
        </button>
      ))}
    </nav>
  );
}
