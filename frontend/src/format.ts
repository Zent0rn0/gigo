import { getLang, intlLocale, N_, pluralForms, t, type Lang } from './i18n';
import type { Job, JobResponse, PayUnit, ResponseStatus } from './types';

const TZ = 'Europe/Moscow';

const dayFmt = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' });

type Fmts = { time: Intl.DateTimeFormat; date: Intl.DateTimeFormat; weekday: Intl.DateTimeFormat; num: Intl.NumberFormat; rating: Intl.NumberFormat };
const fmtCache = new Map<Lang, Fmts>();

/** Форматтеры дат и чисел под текущий язык (если браузер не знает локаль, Intl возьмёт ближайшую). */
function fmts(): Fmts {
  const lang = getLang();
  let f = fmtCache.get(lang);
  if (!f) {
    const loc = intlLocale(lang);
    f = {
      time: new Intl.DateTimeFormat(loc, { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false }),
      date: new Intl.DateTimeFormat(loc, { timeZone: TZ, day: 'numeric', month: 'short' }),
      weekday: new Intl.DateTimeFormat(loc, { timeZone: TZ, weekday: 'short' }),
      num: new Intl.NumberFormat(loc, { maximumFractionDigits: 0 }),
      rating: new Intl.NumberFormat(loc, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
    };
    fmtCache.set(lang, f);
  }
  return f;
}
const timeFmt = { format: (d: Date) => fmts().time.format(d) };
const dateFmt = { format: (d: Date) => fmts().date.format(d) };
const weekdayFmt = { format: (d: Date) => fmts().weekday.format(d) };
const numFmt = { format: (n: number) => fmts().num.format(n) };

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
    const time = timeFmt.format(d);
    if (rel === 'today') return t('сегодня {time}', { time });
    if (rel === 'tomorrow') return t('завтра {time}', { time });
    if (rel === 'yesterday') return t('вчера {time}', { time });
    return `${shortDate(d)}, ${time}`;
  }
  if (job.starts_on) {
    const rel = dayRelation(job.starts_on);
    if (rel === 'today') return t('сегодня');
    if (rel === 'tomorrow') return t('завтра');
    if (rel === 'yesterday') return t('вчера');
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
  const ts = new Date(iso).getTime();
  if (Number.isNaN(ts)) return '';
  const min = Math.max(0, Math.floor((now - ts) / 60000));
  if (min < 1) return t('только что');
  if (min < 60) return t('{n} мин назад', { n: min });
  const h = Math.floor(min / 60);
  if (h < 24) return t('{n} ч назад', { n: h });
  const d = Math.floor(h / 24);
  if (d === 1) return t('вчера');
  return t('{n} {days} назад', { n: d, days: plural(d, ['день', 'дня', 'дней']) });
}

/** «до 15:00» или «до завтра 15:00». */
export function formatUntil(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const rel = dayRelation(mskDay(d));
  const time = timeFmt.format(d);
  if (rel === 'today') return t('до {time}', { time });
  if (rel === 'tomorrow') return t('до завтра {time}', { time });
  return t('до {date} {time}', { date: dateFmt.format(d).replace('.', ''), time });
}

export function rub(n: number): string {
  return `${numFmt.format(n)} ₽`;
}

const UNIT_SUFFIX: Record<PayUnit, string> = {
  hour: N_('/ч'),
  shift: N_('/смена'),
  day: N_('/день'),
  task: N_(' за работу'),
};

/** Подписи единиц оплаты (русские ключи): показывать через t(). */
export const UNIT_LABEL: Record<PayUnit, string> = {
  hour: N_('в час'),
  shift: N_('за смену'),
  day: N_('за день'),
  task: N_('за работу'),
};

/** Главная цифра оплаты: «500 ₽/ч», «≈375 ₽/ч», либо по единице объявления. */
export function formatPay(job: Job): string | null {
  if (job.pay_per_hour != null) return `${job.pay_estimated ? '≈' : ''}${rub(job.pay_per_hour)}${t('/ч')}`;
  if (job.pay_amount != null) return `${rub(job.pay_amount)}${job.pay_unit ? t(UNIT_SUFFIX[job.pay_unit]) : ''}`;
  return null;
}

/** «≈2 000 ₽» за весь заказ. */
export function formatPayTotal(job: Job): string | null {
  return job.pay_total != null ? `≈${rub(job.pay_total)}` : null;
}

export function formatDistance(km: number): string {
  if (km < 1) return t('{n} м', { n: Math.max(10, Math.round((km * 1000) / 10) * 10) });
  if (km < 10) return t('{n} км', { n: km.toFixed(1).replace('.', ',') });
  return t('{n} км', { n: Math.round(km) });
}

export function formatHours(h: number): string {
  const v = Number.isInteger(h) ? String(h) : h.toFixed(1).replace('.', ',');
  return `${v} ${plural(Math.ceil(h), ['час', 'часа', 'часов'])}`;
}

/** Форма слова для числа. forms — русские формы; перевод берётся из словаря по ключу «a|b|c». */
export function plural(n: number, forms: [string, string, string]): string {
  const tr = pluralForms(forms);
  if (tr.length === 1) return tr[0];
  if (tr.length === 2) return Math.abs(n) === 1 ? tr[0] : tr[1];
  return russianPlural(n, tr as [string, string, string]);
}

function russianPlural(n: number, forms: [string, string, string]): string {
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


/** «★ 4,8 · 12 отзывов» или «нет отзывов». */
export function formatRating(rating: number | null, count: number): string {
  if (rating == null || !count) return t('нет отзывов');
  return `★ ${fmts().rating.format(rating)} · ${count} ${plural(count, ['отзыв', 'отзыва', 'отзывов'])}`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : dateFmt.format(d).replace('.', '');
}

/** Статус заявки с учётом срока: open, но просрочена → expired. */
export type JobState = 'open' | 'closed' | 'cancelled' | 'expired';

export function jobState(job: Pick<Job, 'status' | 'expires_at'>, now = Date.now()): JobState {
  if (job.status === 'closed' || job.status === 'cancelled') return job.status;
  const exp = new Date(job.expires_at).getTime();
  if (job.status === 'open' && !Number.isNaN(exp) && exp < now) return 'expired';
  return job.status === 'open' ? 'open' : 'closed';
}

/** Русские ключи: показывать через t(). */
export const JOB_STATE_LABEL: Record<JobState, string> = {
  open: N_('Идёт набор'),
  closed: N_('Набор закрыт'),
  cancelled: N_('Отменена'),
  expired: N_('Срок вышел'),
};

export const JOB_STATE_TONE: Record<JobState, Tone> = { open: 'ok', closed: 'muted', cancelled: 'bad', expired: 'muted' };

export type Tone = 'ok' | 'wait' | 'bad' | 'muted';

/** Как статус отклика видит исполнитель. */
export const RESPONSE_LABEL_WORKER: Record<ResponseStatus, string> = {
  pending: N_('Ждёт ответа'),
  accepted: N_('Вас выбрали'),
  rejected: N_('Не выбрали'),
  withdrawn: N_('Вы отозвали'),
};

/** Как статус отклика видит заказчик. */
export const RESPONSE_LABEL_OWNER: Record<ResponseStatus, string> = {
  pending: N_('Новый'),
  accepted: N_('Принят'),
  rejected: N_('Отклонён'),
  withdrawn: N_('Отозван'),
};

export const RESPONSE_TONE: Record<ResponseStatus, Tone> = { pending: 'wait', accepted: 'ok', rejected: 'bad', withdrawn: 'muted' };

export function isActiveResponse(r: JobResponse | null | undefined): boolean {
  return !!r && (r.status === 'pending' || r.status === 'accepted');
}

/**
 * Ставка в час для подсказки в форме, как считает сервер:
 * смена и день — на длительность, без неё за 8 часов (≈); работа — только при известной длительности.
 */
export function estimatePerHour(amount: number, unit: PayUnit, hours: number | null): { value: number; approx: boolean } | null {
  if (!(amount > 0)) return null;
  if (unit === 'hour') return { value: amount, approx: false };
  if (unit === 'task') return hours && hours > 0 ? { value: Math.round(amount / hours), approx: true } : null;
  if (hours && hours > 0) return { value: Math.round(amount / hours), approx: true };
  return { value: Math.round(amount / 8), approx: true };
}

/** Первая буква имени для аватарки. */
export function initial(name: string): string {
  return (name.trim()[0] ?? '?').toUpperCase();
}
