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

interface TgMainButton {
  isVisible: boolean;
  setText(text: string): void;
  show(): void;
  hide(): void;
  enable(): void;
  disable(): void;
  showProgress(leaveActive?: boolean): void;
  hideProgress(): void;
  onClick(cb: () => void): void;
  offClick(cb: () => void): void;
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
  MainButton?: TgMainButton;
  HapticFeedback?: TgHaptic;
  openTelegramLink(url: string): void;
  showAlert?(message: string): void;
  openLink(url: string): void;
  onEvent?(event: string, cb: () => void): void;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  disableVerticalSwipes?(): void;
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

/** Светлая/тёмная тема Telegram → data-theme на <html>: от неё зависят цвета, которых нет в --tg-theme-*. */
function applyScheme(): void {
  try {
    if (tg?.colorScheme) document.documentElement.dataset.theme = tg.colorScheme;
  } catch {
    /* ignore */
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
  if (!inTelegram) return;
  applyScheme();
  try {
    tg.onEvent?.('themeChanged', applyScheme);
    // шапка и фон Telegram того же цвета, что и фон приложения
    if (atLeast('6.1')) {
      tg.setHeaderColor?.('secondary_bg_color');
      tg.setBackgroundColor?.('secondary_bg_color');
    }
    // своё «потяните, чтобы обновить» в ленте: системный свайп вниз не должен сворачивать приложение
    if (atLeast('7.7')) tg.disableVerticalSwipes?.();
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

export const mainButtonSupported = inTelegram && !!tg?.MainButton;

/** Открыть контакт второй стороны: https://t.me/… — внутри Telegram, tg://… и прочее — window.open. */
export function openContact(url: string): void {
  haptic('light');
  if (/^https:\/\/t\.me\//i.test(url) && inTelegram && tg) {
    try {
      tg.openTelegramLink(url);
      return;
    } catch {
      /* fallback ниже */
    }
  }
  if (/^tg:/i.test(url) && inTelegram && tg?.showAlert) {
    // Mini App не открывает tg://user?id=…: у человека нет username, ссылка на профиль есть в сообщении бота.
    tg.showAlert('У этого человека нет имени пользователя в Telegram. Ссылка на его профиль пришла вам в чат с ботом Gigo.');
    return;
  }
  window.open(url, '_blank', 'noopener');
}

const startParam = (): string => tg?.initDataUnsafe?.start_param ?? '';

/** id заявки из ?job=<id> или start_param «job_<id>». */
export function deepLinkJobId(): number | null {
  const m = /^job_(\d+)$/.exec(startParam());
  if (m) return Number(m[1]);
  try {
    const q = new URLSearchParams(window.location.search).get('job');
    if (q && /^\d+$/.test(q)) return Number(q);
  } catch {
    /* ignore */
  }
  return null;
}

export type DeepTab = 'responses' | 'my' | 'create' | 'profile';
const DEEP_TABS: readonly string[] = ['responses', 'my', 'create', 'profile'];

/** Вкладка из ?tab=responses|my|create|profile или start_param «tab_responses» и т.п. */
export function deepLinkTab(): DeepTab | null {
  const ok = (v: string | null | undefined): DeepTab | null => (v && DEEP_TABS.includes(v) ? (v as DeepTab) : null);
  const m = /^tab_(\w+)$/.exec(startParam());
  if (m && ok(m[1])) return ok(m[1]);
  try {
    return ok(new URLSearchParams(window.location.search).get('tab'));
  } catch {
    return null;
  }
}

const BOT = (import.meta.env.VITE_BOT_USERNAME ?? '').trim().replace(/^@/, '');
const APP_NAME = (import.meta.env.VITE_MINIAPP_NAME ?? '').trim();

/** Ссылка на заявку, которая откроет Mini App у получателя; null, если имя бота не задано. */
export function jobShareLink(jobId: number): string | null {
  if (!BOT) return null;
  // С коротким именем Mini App ссылка открывает приложение сразу; без него открывает бота, и он присылает кнопку.
  return APP_NAME ? `https://t.me/${BOT}/${APP_NAME}?startapp=job_${jobId}` : `https://t.me/${BOT}?start=job_${jobId}`;
}

/**
 * Поделиться: в Telegram — окно выбора чата (t.me/share/url), в браузере — системное «Поделиться»,
 * иначе текст копируется. Возвращает, что произошло, чтобы показать подсказку.
 */
export async function shareText(text: string, url: string | null): Promise<'shared' | 'copied' | 'failed'> {
  haptic('light');
  if (inTelegram && tg && url) {
    try {
      tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`);
      return 'shared';
    } catch {
      /* ниже */
    }
  }
  const full = url ? `${text}\n${url}` : text;
  if (!inTelegram && typeof navigator.share === 'function') {
    try {
      await navigator.share({ text: full });
      return 'shared';
    } catch {
      /* отменили или не умеет — копируем */
    }
  }
  try {
    await navigator.clipboard.writeText(full);
    return 'copied';
  } catch {
    return 'failed';
  }
}
