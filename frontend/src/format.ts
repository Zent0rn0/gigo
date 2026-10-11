import type { Job, PayUnit } from './types';

const TZ = 'Europe/Moscow';

const dayFmt = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' });
const timeFmt = new Intl.DateTimeFormat('ru-RU', { timeZone: TZ, hour: '2-digit', minute: '2-digit' });
const dateFmt = new Intl.DateTimeFormat('ru-RU', { timeZone: TZ, day: 'numeric', month: 'short' });
const weekdayFmt = new Intl.DateTimeFormat('ru-RU', { timeZone: TZ, weekday: 'short' });
const numFmt = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });

/** Дата YYYY-MM-DD по Москве. */
export function mskDay(d: Date): string {
  return dayFmt.format(d);
}

function dayRelation(key: string, now = new Date()): 'today' | 'tomorrow' | 'yesterday' | null {
  if (key === mskDay(now)) return 'today';
  if (key === mskDay(new Date(now.getTime() + 864e5))) return 'tomorrow';
  if (key === mskDay(new Date(now.getTime() - 864e5))) return 'yesterday';
  return null;
}

function shortDate(d: Date): string {
  return `${weekdayFmt.format(d)}, ${dateFmt.format(d).replace('.', '')}`;
}

/** «сегодня 14:00», «завтра», «пт, 16 окт». */
export function formatWhen(job: Pick<Job, 'starts_at' | 'starts_on'>): string | null {
  if (job.starts_at) {
    const d = new Date(job.starts_at);
    if (Number.isNaN(d.getTime())) return null;
    const rel = dayRelation(mskDay(d));
    const t = timeFmt.format(d);
    if (rel === 'today') return `сегодня ${t}`;
    if (rel === 'tomorrow') return `завтра ${t}`;
    if (rel === 'yesterday') return `вчера ${t}`;
    return `${shortDate(d)}, ${t}`;
  }
  if (job.starts_on) {
    const rel = dayRelation(job.starts_on);
    if (rel === 'today') return 'сегодня';
    if (rel === 'tomorrow') return 'завтра';
    if (rel === 'yesterday') return 'вчера';
    const d = new Date(`${job.starts_on}T12:00:00+03:00`);
    return Number.isNaN(d.getTime()) ? null : shortDate(d);
  }
  return null;
}

export function formatTime(iso: string): string {
  return timeFmt.format(new Date(iso));
}

/** «13 мин назад». */
export function formatAge(iso: string, now = Date.now()): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const min = Math.max(0, Math.floor((now - t) / 60000));
  if (min < 1) return 'только что';
  if (min < 60) return `${min} мин назад`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} ч назад`;
  const d = Math.floor(h / 24);
  if (d === 1) return 'вчера';
  return `${d} ${plural(d, ['день', 'дня', 'дней'])} назад`;
}

/** «до 15:00» или «до завтра 15:00». */
export function formatUntil(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const rel = dayRelation(mskDay(d));
  const t = timeFmt.format(d);
  if (rel === 'today') return `до ${t}`;
  if (rel === 'tomorrow') return `до завтра ${t}`;
  return `до ${dateFmt.format(d).replace('.', '')} ${t}`;
}

export function rub(n: number): string {
  return `${numFmt.format(n)} ₽`;
}

const UNIT_SUFFIX: Record<PayUnit, string> = {
  hour: '/ч',
  shift: '/смена',
  day: '/день',
  task: ' за заказ',
  month: '/мес',
};

export const UNIT_LABEL: Record<PayUnit, string> = {
  hour: 'в час',
  shift: 'за смену',
  day: 'за день',
  task: 'за заказ',
  month: 'в месяц',
};

/** Главная цифра оплаты: «500 ₽/ч», «≈375 ₽/ч», либо по единице объявления. */
export function formatPay(job: Job): string | null {
  if (job.pay_per_hour != null) return `${job.pay_estimated ? '≈' : ''}${rub(job.pay_per_hour)}/ч`;
  if (job.pay_amount != null) return `${rub(job.pay_amount)}${job.pay_unit ? UNIT_SUFFIX[job.pay_unit] : ''}`;
  return null;
}

/** «≈2 000 ₽» за весь заказ. */
export function formatPayTotal(job: Job): string | null {
  return job.pay_total != null ? `≈${rub(job.pay_total)}` : null;
}

export function formatDistance(km: number): string {
  if (km < 1) return `${Math.max(10, Math.round((km * 1000) / 10) * 10)} м`;
  if (km < 10) return `${km.toFixed(1).replace('.', ',')} км`;
  return `${Math.round(km)} км`;
}

export function formatHours(h: number): string {
  const v = Number.isInteger(h) ? String(h) : h.toFixed(1).replace('.', ',');
  return `${v} ${plural(Math.ceil(h), ['час', 'часа', 'часов'])}`;
}

/** 79001234567 → +7 900 123-45-67 */
export function formatPhone(digits: string): string {
  const d = digits.replace(/\D/g, '');
  if (d.length === 11 && (d[0] === '7' || d[0] === '8')) {
    return `+7 ${d.slice(1, 4)} ${d.slice(4, 7)}-${d.slice(7, 9)}-${d.slice(9)}`;
  }
  return `+${d}`;
}

export function telHref(digits: string): string {
  return `tel:+${digits.replace(/\D/g, '')}`;
}

export function plural(n: number, forms: [string, string, string]): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return forms[2];
  if (b > 1 && b < 5) return forms[1];
  if (b === 1) return forms[0];
  return forms[2];
}

export function lineColor(color: string | null | undefined): string {
  if (!color) return '#9e9e9e';
  return color.startsWith('#') ? color : `#${color}`;
}
