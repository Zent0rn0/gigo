// Набор иконок Gigo: 24×24, линия 1.9, currentColor. Без библиотек — только inline SVG.
import type { CSSProperties } from 'react';

const P: Record<string, string> = {
  // навигация
  feed: 'M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01',
  map: 'M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4zM9 4v14M15 6v14',
  inbox: 'M4 13.5V18a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4.5M4 13.5 6.3 5.6A2 2 0 0 1 8.2 4h7.6a2 2 0 0 1 1.9 1.6l2.3 7.9M4 13.5h4.5l1.2 2.5h4.6l1.2-2.5H20',
  clipboard: 'M9 4.5H7a2 2 0 0 0-2 2V19a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6.5a2 2 0 0 0-2-2h-2M9 3h6v3H9zM9 11h6M9 15h4',
  'plus-circle': 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8v8M8 12h8',
  plus: 'M12 5v14M5 12h14',
  user: 'M12 4.4a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2zM5 20c.9-3.6 3.6-5.5 7-5.5s6.1 1.9 7 5.5',
  users:
    'M9 5.5a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM3.5 19c.6-3 2.7-4.6 5.5-4.6s4.9 1.6 5.5 4.6M16.5 7.1a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8zM16.5 14.5c2.2 0 3.6 1.4 4.1 4',
  'chevron-right': 'M9.5 5.5 16 12l-6.5 6.5',
  'chevron-left': 'M14.5 5.5 8 12l6.5 6.5',
  'chevron-down': 'M6.5 9.5 12 15l5.5-5.5',
  x: 'M6.5 6.5l11 11M17.5 6.5l-11 11',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  // факты
  pin: 'M12 21s-6.5-5.8-6.5-11a6.5 6.5 0 0 1 13 0c0 5.2-6.5 11-6.5 11zM12 7.7a2.3 2.3 0 1 0 0 4.6 2.3 2.3 0 0 0 0-4.6z',
  clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7.5V12l3 2',
  calendar: 'M5.5 5h13a2 2 0 0 1 2 2v11.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2zM3.5 10h17M8 3v4M16 3v4',
  metro: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM7.5 16V8.5l4.5 6 4.5-6V16',
  ruble: 'M8.5 20V4h5a4 4 0 0 1 0 8H6.5M6.5 16H14',
  wallet: 'M4 7.5A2.5 2.5 0 0 1 6.5 5H17v3M4 7.5V17a2 2 0 0 0 2 2h13a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1H6.5A2.5 2.5 0 0 1 4 7.5zM16.5 13.5h.01',
  navigation: 'M20 4 4 11l7 2 2 7z',
  locate: 'M12 5a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM12 2v3M12 19v3M2 12h3M19 12h3M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z',
  star: 'M12 3.6l2.6 5.2 5.7.8-4.1 4 1 5.7L12 16.6l-5.2 2.7 1-5.7-4.1-4 5.7-.8z',
  // действия
  bell: 'M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15zM10 20.5a2 2 0 0 0 4 0',
  'bell-check': 'M6 16v-5a6 6 0 0 1 9-5.2M18 11v5l1.5 2h-15M10 20.5a2 2 0 0 0 4 0M15 7.5l2 2 4-4',
  search: 'M11 4.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM20 20l-4.3-4.3',
  refresh: 'M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4v4.5H15',
  sliders: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 5a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM9 15a2 2 0 1 0 0 4 2 2 0 0 0 0-4z',
  share: 'M12 3.5v11M8 7.5l4-4 4 4M5.5 11.5V18a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-6.5',
  flag: 'M5.5 21V4M5.5 4.5h11.5l-2.5 4 2.5 4H5.5',
  shield: 'M12 3l7.5 3v5.5c0 4.6-3.2 8.2-7.5 9.5-4.3-1.3-7.5-4.9-7.5-9.5V6zM9 12l2 2 4-4',
  help: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM9.6 9.3a2.5 2.5 0 0 1 4.8 1c0 1.7-2.4 2.2-2.4 3.7M12 17.2h.01',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v5.5M12 7.8h.01',
  alert: 'M10.3 4.3 2.6 17.6a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0zM12 9.5v4M12 17h.01',
  message: 'M20 11.5a7.5 7.5 0 0 1-11 6.6L4 19.5l1.4-4.6A7.5 7.5 0 1 1 20 11.5z',
  send: 'M20.5 3.5 10 14M20.5 3.5 14 21l-4-7-6.5-3.5z',
  edit: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
  trash: 'M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13',
  copy: 'M10 8h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-8a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2zM16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2',
  bookmark: 'M7 3.5h10a1.5 1.5 0 0 1 1.5 1.5v15.5L12 16.5l-6.5 4V5A1.5 1.5 0 0 1 7 3.5z',
  eye: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
  ban: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM5.7 5.7l12.6 12.6',
  briefcase: 'M5.5 7h13a2 2 0 0 1 2 2v8.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2zM9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7M3.5 12.5h17',
  zap: 'M13 2.5 4.5 13.5H12l-1 8 8.5-11H12z',
  logout: 'M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 8l-4 4 4 4M6 12h10',
  swap: 'M7 4 4 7l3 3M4 7h12M17 20l3-3-3-3M20 17H8',
  // категории
  loader: 'M12 3 20 7.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9M8 5.3l8 4.5',
  courier: 'M11 6.5h7.5a1.5 1.5 0 0 1 1.5 1.5v8a1.5 1.5 0 0 1-1.5 1.5H11A1.5 1.5 0 0 1 9.5 16V8A1.5 1.5 0 0 1 11 6.5zM13.5 6.5v4h3v-4M3 9.5h4M4 13h3M5 16.5h2',
  warehouse: 'M3 20V9l9-5 9 5v11M7 20v-7h10v7M7 16.5h10',
  cleaning: 'M8.5 10.5H14l1.5 2.5v7a1 1 0 0 1-1 1H8.5a1 1 0 0 1-1-1v-8.5a1 1 0 0 1 1-1zM9.5 10.5V7h3.5v3.5M9.5 7 8.5 4.5h6.5M18 4.5h.01M20.5 7h.01M18 9.5h.01',
  construction: 'M3 17h18v2.5H3zM5 17v-2.5a7 7 0 0 1 14 0V17M10 8.6V6.5h4v2.1M12 6.5v4',
  promo: 'M4 10v4h3l8 4.5v-13L7 10zM18.5 9a3.5 3.5 0 0 1 0 6M7 14l1.5 5.5H11L10 15.5',
  kitchen: 'M7 17.5h10V21H7zM7 17.5v-4.3A4 4 0 0 1 8.5 5.6a4 4 0 0 1 7 0 4 4 0 0 1 1.5 7.6v4.3',
  driver: 'M4.5 13.5 6.4 8a2 2 0 0 1 1.9-1.4h7.4a2 2 0 0 1 1.9 1.4l1.9 5.5M3.5 13.5h17v4a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1zM6 18.5V20M18 18.5V20M7 16h.01M17 16h.01',
  event: 'M3.5 8.5v-2a1 1 0 0 1 1-1h15a1 1 0 0 1 1 1v2a3.5 3.5 0 0 0 0 7v2a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1v-2a3.5 3.5 0 0 0 0-7zM14.5 5.5v13',
  other: 'M5.5 4h3.5A1.5 1.5 0 0 1 10.5 5.5V9A1.5 1.5 0 0 1 9 10.5H5.5A1.5 1.5 0 0 1 4 9V5.5A1.5 1.5 0 0 1 5.5 4zM15 4h3.5A1.5 1.5 0 0 1 20 5.5V9a1.5 1.5 0 0 1-1.5 1.5H15A1.5 1.5 0 0 1 13.5 9V5.5A1.5 1.5 0 0 1 15 4zM5.5 13.5H9a1.5 1.5 0 0 1 1.5 1.5v3.5A1.5 1.5 0 0 1 9 20H5.5A1.5 1.5 0 0 1 4 18.5V15a1.5 1.5 0 0 1 1.5-1.5zM16.75 13.5a3.25 3.25 0 1 0 0 6.5 3.25 3.25 0 0 0 0-6.5z',
};

export type IconName = keyof typeof P;

const CATEGORY_ICONS = new Set(['loader', 'courier', 'warehouse', 'cleaning', 'construction', 'promo', 'kitchen', 'driver', 'event', 'other']);

/** Иконка категории по её id; неизвестная категория — «Другое». */
export function categoryIcon(id: string | null | undefined): IconName {
  return id && CATEGORY_ICONS.has(id) ? id : 'other';
}

interface Props {
  name: IconName;
  size?: number;
  /** Залить фигуру (звезда). */
  filled?: boolean;
  className?: string;
  style?: CSSProperties;
  /** Подпись для одиночной смысловой иконки; без неё иконка скрыта от скринридеров. */
  label?: string;
  strokeWidth?: number;
}

export function Icon({ name, size = 24, filled, className, style, label, strokeWidth = 1.9 }: Props) {
  return (
    <svg
      className={`icon${className ? ` ${className}` : ''}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={style}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <path d={P[name]} />
    </svg>
  );
}
