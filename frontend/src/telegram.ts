// Тонкая обёртка над Telegram.WebApp: в обычном браузере всё безопасно ничего не делает.

interface TgBackButton {
  isVisible: boolean;
  show(): void;
  hide(): void;
  onClick(cb: () => void): void;
  offClick(cb: () => void): void;
}

interface TgHaptic {
  impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
  notificationOccurred(type: 'error' | 'success' | 'warning'): void;
  selectionChanged(): void;
}

export interface TgWebApp {
  initData: string;
  initDataUnsafe: { start_param?: string; user?: { id: number; first_name?: string } };
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  isVersionAtLeast(version: string): boolean;
  ready(): void;
  expand(): void;
  BackButton: TgBackButton;
  HapticFeedback?: TgHaptic;
  openTelegramLink(url: string): void;
  openLink(url: string): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TgWebApp };
  }
}

export const tg: TgWebApp | undefined = typeof window !== 'undefined' ? window.Telegram?.WebApp : undefined;

/** Строка initData для заголовка Authorization; пустая в обычном браузере. */
export const initData: string = tg?.initData ?? '';

/** Запущено ли внутри Telegram (есть подписанные данные). */
export const inTelegram = initData.length > 0;

function atLeast(v: string): boolean {
  try {
    return !!tg && tg.isVersionAtLeast(v);
  } catch {
    return false;
  }
}

export function initTelegram(): void {
  if (!tg) return;
  try {
    tg.ready();
    tg.expand();
  } catch {
    /* старый клиент */
  }
}

export const backButtonSupported = inTelegram && atLeast('6.1');

export function haptic(kind: 'light' | 'success' | 'error' | 'select'): void {
  if (!inTelegram || !atLeast('6.1')) return;
  const h = tg?.HapticFeedback;
  if (!h) return;
  try {
    if (kind === 'light') h.impactOccurred('light');
    else if (kind === 'select') h.selectionChanged();
    else h.notificationOccurred(kind);
  } catch {
    /* ignore */
  }
}

/** Открыть ссылку: t.me — внутри Telegram, остальное — во внешнем браузере. */
export function openLink(url: string): void {
  const isTme = /^https?:\/\/(t\.me|telegram\.me)\//i.test(url);
  if (inTelegram && tg) {
    try {
      if (isTme) tg.openTelegramLink(url);
      else tg.openLink(url);
      return;
    } catch {
      /* fallback ниже */
    }
  }
  window.open(url, '_blank', 'noopener');
}

/** id заказа из ?job=<id> или start_param «job_<id>». */
export function deepLinkJobId(): number | null {
  const fromStart = tg?.initDataUnsafe?.start_param;
  if (fromStart) {
    const m = /^job_(\d+)$/.exec(fromStart);
    if (m) return Number(m[1]);
  }
  try {
    const q = new URLSearchParams(window.location.search).get('job');
    if (q && /^\d+$/.test(q)) return Number(q);
  } catch {
    /* ignore */
  }
  return null;
}
