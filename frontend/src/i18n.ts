// Языки интерфейса. Ключ перевода — сам русский текст: t('Лента') вернёт перевод на выбранный язык,
// а если перевода нет — русский текст как есть. Переводы: src/locales/<язык>.json (грузятся по требованию).
// Подстановки: t('{n} мин назад', { n: 5 }). Константы на уровне модуля помечаются N_('…')
// и переводятся при показе через t(константа). Множественное число — plural() из format.ts.

import { useSyncExternalStore } from 'react';

export type Lang = 'ru' | 'en' | 'uz' | 'tg' | 'ky' | 'kk' | 'az' | 'hy';

export const DEFAULT_LANG: Lang = 'ru';

/** Порядок — как в списке выбора. Название — на самом языке. */
export const LANGUAGES: { id: Lang; name: string; flag: string }[] = [
  { id: 'ru', name: 'Русский', flag: '🇷🇺' },
  { id: 'en', name: 'English', flag: '🇬🇧' },
  { id: 'uz', name: 'Oʻzbekcha', flag: '🇺🇿' },
  { id: 'tg', name: 'Тоҷикӣ', flag: '🇹🇯' },
  { id: 'ky', name: 'Кыргызча', flag: '🇰🇬' },
  { id: 'kk', name: 'Қазақша', flag: '🇰🇿' },
  { id: 'az', name: 'Azərbaycanca', flag: '🇦🇿' },
  { id: 'hy', name: 'Հայերեն', flag: '🇦🇲' },
];

/** Локаль для Intl (даты, числа). */
const INTL_LOCALE: Record<Lang, string> = {
  ru: 'ru-RU', en: 'en-GB', uz: 'uz-Latn-UZ', tg: 'tg-TJ', ky: 'ky-KG', kk: 'kk-KZ', az: 'az-Latn-AZ', hy: 'hy-AM',
};

const STORE_KEY = 'gigo.lang';

type Dict = Record<string, string>;

const loaders = import.meta.glob<Dict>('./locales/*.json', { import: 'default' });

let lang: Lang = DEFAULT_LANG;
let dict: Dict = {};
const listeners = new Set<() => void>();

export function normalizeLang(code: string | null | undefined): Lang | null {
  if (!code) return null;
  const base = code.trim().toLowerCase().replace('_', '-').split('-')[0];
  return LANGUAGES.some((l) => l.id === base) ? (base as Lang) : null;
}

export function getLang(): Lang {
  return lang;
}

export function intlLocale(l: Lang = lang): string {
  return INTL_LOCALE[l];
}

/** Язык, сохранённый на этом устройстве (чтобы первый экран сразу был на нём, ещё до ответа сервера). */
export function storedLang(): Lang | null {
  try {
    return normalizeLang(localStorage.getItem(STORE_KEY));
  } catch {
    return null;
  }
}

async function loadDict(l: Lang): Promise<Dict> {
  if (l === DEFAULT_LANG) return {};
  const load = loaders[`./locales/${l}.json`];
  if (!load) return {};
  try {
    return await load();
  } catch (e) {
    console.error('[gigo] не загрузился перевод', l, e);
    return {};
  }
}

/** Переключает язык: грузит словарь и перерисовывает подписчиков. */
export async function setLang(next: Lang): Promise<void> {
  const d = await loadDict(next);
  lang = next;
  dict = d;
  try {
    localStorage.setItem(STORE_KEY, next);
  } catch {
    /* приватный режим: язык просто не запомнится на устройстве */
  }
  document.documentElement.lang = next;
  listeners.forEach((cb) => cb());
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Текущий язык; компонент перерисуется при смене. */
export function useLang(): Lang {
  return useSyncExternalStore(subscribe, getLang, getLang);
}

function fill(s: string, params?: Record<string, string | number>): string {
  if (!params) return s;
  return s.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m));
}

/** Перевод русского текста на текущий язык. */
export function t(ru: string, params?: Record<string, string | number>): string {
  return fill(dict[ru] || ru, params);
}

/** Помечает строку для перевода, не переводя: для констант, которые переводятся при показе через t(). */
export function N_(ru: string): string {
  return ru;
}

/** Варианты форм для множественного числа: в переводе 1, 2 (one|other) или 3 (как в русском) формы. */
export function pluralForms(ruForms: [string, string, string]): string[] {
  const key = ruForms.join('|');
  const tr = dict[key];
  return tr ? tr.split('|') : ruForms;
}
