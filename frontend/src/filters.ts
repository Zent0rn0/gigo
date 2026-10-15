import type { GeoPoint, JobsQuery, Meta, SubscriptionInput } from './types';
import { rub } from './format';
import { t } from './i18n';

export interface Filters {
  categories: string[];
  payMin: number | null;
  today: boolean;
  metro: string[];
  nearMe: boolean;
}

export const EMPTY_FILTERS: Filters = { categories: [], payMin: null, today: false, metro: [], nearMe: false };
export const PAY_PRESETS = [300, 400, 500, 700, 1000];
/** Радиус подписки «рядом со мной». */
export const NEAR_RADIUS_KM = 5;

const KEY = 'gigo.filters.v1';

export function loadFilters(): Filters {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return EMPTY_FILTERS;
    const v = JSON.parse(raw) as Partial<Filters>;
    return {
      categories: Array.isArray(v.categories) ? v.categories.filter((x) => typeof x === 'string') : [],
      payMin: typeof v.payMin === 'number' && v.payMin > 0 ? v.payMin : null,
      today: v.today === true,
      metro: Array.isArray(v.metro) ? v.metro.filter((x) => typeof x === 'string') : [],
      nearMe: v.nearMe === true,
    };
  } catch {
    return EMPTY_FILTERS;
  }
}

export function saveFilters(f: Filters): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(f));
  } catch {
    /* приватный режим и т.п. */
  }
}

export function isEmptyFilter(f: Filters): boolean {
  return !f.categories.length && f.payMin == null && !f.today && !f.metro.length && !f.nearMe;
}

/** Запрос к /api/jobs без пагинации. */
export function filtersToQuery(f: Filters, loc: GeoPoint | null): JobsQuery {
  const q: JobsQuery = {};
  if (f.categories.length) q.category = f.categories;
  if (f.payMin != null) q.pay_min = f.payMin;
  if (f.metro.length) q.metro = f.metro;
  if (f.today) q.today = true;
  if (loc) {
    q.lat = loc.lat;
    q.lng = loc.lng;
    if (f.nearMe) q.sort = 'distance';
  }
  return q;
}

/** «Грузчики · от 500 ₽/ч · Таганская» */
export function subscriptionName(f: Filters, meta: Meta | null): string {
  const parts: string[] = [];
  if (f.categories.length) {
    const labels = f.categories.map((id) => meta?.categories.find((c) => c.id === id)?.label ?? id);
    parts.push(labels.length > 2 ? `${labels.slice(0, 2).join(', ')} +${labels.length - 2}` : labels.join(', '));
  } else {
    parts.push(t('Все заказы'));
  }
  if (f.payMin != null) parts.push(t('от {pay}/ч', { pay: rub(f.payMin) }));
  if (f.metro.length) {
    const names = f.metro.map((id) => meta?.metro.find((m) => m.id === id)?.name ?? id);
    parts.push(names.length > 2 ? `${names.slice(0, 2).join(', ')} +${names.length - 2}` : names.join(', '));
  }
  if (f.nearMe) parts.push(t('до {km} км от меня', { km: NEAR_RADIUS_KM }));
  if (f.today) parts.push(t('сегодня'));
  return parts.join(' · ');
}

export function subscriptionBody(f: Filters, meta: Meta | null, loc: GeoPoint | null): SubscriptionInput {
  const near = f.nearMe && loc;
  return {
    name: subscriptionName(f, meta),
    categories: f.categories,
    pay_min: f.payMin,
    metro_ids: f.metro,
    lat: near ? loc.lat : null,
    lng: near ? loc.lng : null,
    radius_km: near ? NEAR_RADIUS_KM : null,
    today_only: f.today,
  };
}
