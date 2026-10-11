import { useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, errorText } from '../api';
import { Icon, categoryIcon, type IconName } from '../components/Icon';
import { JobCard } from '../components/JobCard';
import { MetroPicker } from '../components/MetroPicker';
import { MetroDot } from '../components/MetroDot';
import { PointPicker, type Point } from '../components/PointPicker';
import { estimatePerHour, mskDay, rub } from '../format';
import { useMainButton } from '../mainButton';
import { backButtonSupported, haptic, mainButtonSupported } from '../telegram';
import type { Job, JobIn, Me, Meta, PayUnit } from '../types';
import { YMAPS_KEY } from '../ymaps';

interface Props {
  meta: Meta;
  me: Me;
  active: boolean;
  onCreated(job: Job): void;
  toast(text: string): void;
  /**
   * edit: правка открытой заявки (форма поверх вкладок, сохраняет PUT).
   * repeat: новая заявка по образцу старой.
   */
  source?: { mode: 'edit' | 'repeat'; job: Job } | null;
  /** Закрыть форму (только для source). */
  onBack?(): void;
}

type DateMode = 'today' | 'tomorrow' | 'pick';

interface Form {
  category: string | null;
  title: string;
  description: string;
  workers: number;
  payAmount: string;
  payUnit: PayUnit;
  payTiming: string;
  dateMode: DateMode;
  date: string;
  time: string;
  duration: string;
  metroId: string | null;
  address: string;
  point: Point | null;
}

const EMPTY: Form = {
  category: null,
  title: '',
  description: '',
  workers: 1,
  payAmount: '',
  payUnit: 'hour',
  payTiming: '',
  dateMode: 'today',
  date: '',
  time: '',
  duration: '',
  metroId: null,
  address: '',
  point: null,
};

/** Что запоминаем с прошлой заявки: категория, метро, единица оплаты, когда платят. */
type Remembered = Pick<Form, 'category' | 'metroId' | 'payUnit' | 'payTiming'>;
const LAST_KEY = 'gigo.create.last.v1';
const UNITS: PayUnit[] = ['hour', 'shift', 'day', 'task'];

function loadLast(meta: Meta): Partial<Remembered> {
  try {
    const v = JSON.parse(localStorage.getItem(LAST_KEY) || 'null') as Partial<Remembered> | null;
    if (!v || typeof v !== 'object') return {};
    const out: Partial<Remembered> = {};
    if (typeof v.category === 'string' && meta.categories.some((c) => c.id === v.category)) out.category = v.category;
    if (typeof v.metroId === 'string' && meta.metro.some((m) => m.id === v.metroId)) out.metroId = v.metroId;
    if (typeof v.payUnit === 'string' && UNITS.includes(v.payUnit)) out.payUnit = v.payUnit;
    if (typeof v.payTiming === 'string') out.payTiming = v.payTiming.slice(0, 60);
    return out;
  } catch {
    return {};
  }
}

function saveLast(f: Form): void {
  try {
    const v: Remembered = { category: f.category, metroId: f.metroId, payUnit: f.payUnit, payTiming: f.payTiming };
    localStorage.setItem(LAST_KEY, JSON.stringify(v));
  } catch {
    /* приватный режим */
  }
}

const freshForm = (meta: Meta): Form => ({ ...EMPTY, ...loadLast(meta) });

const hmFmt = new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit' });

/** Форма из существующей заявки. При повторе дата — сегодня, а если время сегодня уже прошло, завтра. */
function formFromJob(job: Job, mode: 'edit' | 'repeat', now = new Date()): Form {
  const time = job.starts_at ? hmFmt.format(new Date(job.starts_at)) : '';
  const today = mskDay(now);
  const tomorrow = mskDay(new Date(now.getTime() + 864e5));
  let dateMode: DateMode = 'today';
  let date = '';
  if (mode === 'edit' && job.starts_on) {
    if (job.starts_on === tomorrow) dateMode = 'tomorrow';
    else if (job.starts_on !== today) {
      dateMode = 'pick';
      date = job.starts_on;
    }
  } else if (mode === 'repeat' && time && time < hmFmt.format(now)) {
    dateMode = 'tomorrow';
  }
  // точку берём, только если её ставили сами или она от адреса: иначе сервер заново возьмёт координаты метро
  const point = job.lat != null && job.lng != null && (!job.metro || job.address) ? { lat: job.lat, lng: job.lng } : null;
  return {
    category: job.category,
    title: job.title,
    description: job.description ?? '',
    workers: job.workers_needed ?? 1,
    payAmount: job.pay_amount != null ? String(Math.round(job.pay_amount)) : '',
    payUnit: job.pay_unit ?? 'hour',
    payTiming: job.pay_timing ?? '',
    dateMode,
    date,
    time,
    duration: job.duration_hours != null ? String(job.duration_hours).replace('.', ',') : '',
    metroId: job.metro?.id ?? null,
    address: job.address ?? '',
    point,
  };
}

const TIMING_PRESETS = ['сразу', 'в конце дня', 'на следующий день'];
const MAX_WORKERS = 50;

type Errors = Partial<Record<'category' | 'title' | 'pay' | 'date' | 'time' | 'duration' | 'place', string>>;

const num = (s: string): number | null => {
  const v = Number(s.replace(',', '.').replace(/\s/g, ''));
  return s.trim() && Number.isFinite(v) ? v : null;
};

function startDay(f: Form, now = new Date()): string | null {
  if (f.dateMode === 'today') return mskDay(now);
  if (f.dateMode === 'tomorrow') return mskDay(new Date(now.getTime() + 864e5));
  return f.date || null;
}

function validate(f: Form): Errors {
  const e: Errors = {};
  const now = new Date();
  if (!f.category) e.category = 'Выберите категорию';
  if (f.title.trim().length < 3) e.title = 'Коротко напишите, что нужно сделать';
  const pay = num(f.payAmount);
  if (pay == null || pay <= 0) e.pay = 'Укажите оплату';
  else if (pay > 1_000_000) e.pay = 'Слишком большая сумма';
  if (f.dateMode === 'pick') {
    if (!f.date) e.date = 'Выберите дату';
    else if (f.date < mskDay(now)) e.date = 'Эта дата уже прошла';
  }
  if (f.time && startDay(f) === mskDay(now)) {
    const nowHm = new Intl.DateTimeFormat('ru-RU', { timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit' }).format(now);
    if (f.time < nowHm) e.time = 'Это время сегодня уже прошло';
  }
  const dur = num(f.duration);
  if (f.duration.trim() && (dur == null || dur < 0.5 || dur > 24)) e.duration = 'От 0,5 до 24 часов';
  if (!f.metroId && !f.address.trim() && !f.point) e.place = 'Укажите метро, адрес или точку на карте';
  return e;
}

function toBody(f: Form): JobIn {
  return {
    category: f.category!,
    title: f.title.trim(),
    description: f.description.trim() || null,
    workers_needed: f.workers,
    pay_amount: num(f.payAmount)!,
    pay_unit: f.payUnit,
    pay_timing: f.payTiming.trim() || null,
    starts_on: startDay(f),
    start_time: f.time || null,
    duration_hours: num(f.duration),
    metro_id: f.metroId,
    address: f.address.trim() || null,
    lat: f.point?.lat ?? null,
    lng: f.point?.lng ?? null,
  };
}

function Section({ icon, title, children }: { icon: IconName; title: string; children: ReactNode }) {
  return (
    <section className="form-section">
      <h2 className="form-section__title">
        <Icon name={icon} size={18} />
        {title}
      </h2>
      <div className="form-section__body">{children}</div>
    </section>
  );
}

export function CreateJob({ meta, me, active, onCreated, toast, source, onBack }: Props) {
  const editing = source?.mode === 'edit' ? source.job : null;
  const catLabelId = useId();
  const [form, setForm] = useState<Form>(() => (source ? formFromJob(source.job, source.mode) : freshForm(meta)));
  const [tried, setTried] = useState(false);
  const [touched, setTouched] = useState<Set<keyof Errors>>(() => new Set());
  const touch = (k: keyof Errors) => setTouched((t) => (t.has(k) ? t : new Set(t).add(k)));
  const [busy, setBusy] = useState(false);
  const [serverError, setServerError] = useState('');
  const [metroOpen, setMetroOpen] = useState(false);
  const [pointOpen, setPointOpen] = useState(false);
  const errorRef = useRef<HTMLDivElement | null>(null);

  const set = (patch: Partial<Form>) => {
    setForm((f) => ({ ...f, ...patch }));
    setServerError('');
  };
  const errors = validate(form);
  // ошибка видна после попытки отправить или когда поле уже трогали и ушли с него
  const shown: Errors = tried ? errors : Object.fromEntries(Object.entries(errors).filter(([k]) => touched.has(k as keyof Errors)));
  const station = form.metroId ? meta.metro.find((m) => m.id === form.metroId) : undefined;

  const pay = num(form.payAmount);
  const est = pay != null ? estimatePerHour(pay, form.payUnit, num(form.duration)) : null;

  const submit = async () => {
    if (busy) return;
    setTried(true);
    if (Object.keys(errors).length) {
      haptic('error');
      // прокрутить к первой ошибке
      window.setTimeout(() => document.querySelector('.field--error')?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0);
      return;
    }
    setBusy(true);
    setServerError('');
    try {
      if (editing) {
        const job = await api.updateJob(editing.id, toBody(form));
        haptic('success');
        toast(editing.responses_count ? 'Сохранено. Откликнувшимся пришлём сообщение об изменениях.' : 'Изменения сохранены');
        onCreated(job);
        return;
      }
      const job = await api.createJob(toBody(form));
      haptic('success');
      toast('Заявка опубликована. Сообщим, когда кто-то откликнется.');
      saveLast(form);
      if (!source) {
        setForm(freshForm(meta));
        setTried(false);
        setTouched(new Set());
      }
      onCreated(job);
    } catch (e) {
      haptic('error');
      setServerError(errorText(e));
      window.setTimeout(() => errorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0);
    } finally {
      setBusy(false);
    }
  };

  const submitText = editing ? 'Сохранить изменения' : 'Опубликовать заявку';
  useMainButton(active && !metroOpen && !pointOpen ? { text: submitText, onClick: submit, progress: busy } : null);

  const cls = (k: keyof Errors) => `field${shown[k] ? ' field--error' : ''}`;
  const err = (k: keyof Errors) =>
    shown[k] && (
      <div className="field__error" role="alert">
        <Icon name="alert" size={14} strokeWidth={2.2} />
        {shown[k]}
      </div>
    );

  // так заявка будет выглядеть в ленте
  const preview = useMemo<Job | null>(() => {
    if (form.title.trim().length < 3 || !(pay && pay > 0)) return null;
    const day = startDay(form);
    const hours = num(form.duration);
    const st = station;
    return {
      id: 0,
      status: 'open',
      category: form.category ?? 'other',
      title: form.title.trim(),
      description: null,
      workers_needed: form.workers,
      pay_amount: pay,
      pay_unit: form.payUnit,
      pay_per_hour: est?.value ?? null,
      pay_estimated: est?.approx && form.payUnit !== 'hour' && !hours ? true : false,
      pay_total: form.payUnit === 'hour' ? (hours ? Math.round(pay * hours) : null) : pay,
      pay_timing: form.payTiming || null,
      starts_on: day,
      starts_at: day && form.time ? `${day}T${form.time}:00+03:00` : null,
      duration_hours: hours,
      metro: st ? { id: st.id, name: st.name, line: st.line, color: st.color } : null,
      address: form.address.trim() || null,
      lat: null,
      lng: null,
      distance_km: null,
      employer: { id: me.id, first_name: me.first_name, rating: me.rating, reviews_count: me.reviews_count },
      responses_count: 0,
      accepted_count: 0,
      is_mine: false,
      my_response: null,
      created_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 864e5).toISOString(),
    };
  }, [form, pay, est, station, me]);

  const timingCustom = TIMING_PRESETS.includes(form.payTiming) ? '' : form.payTiming;

  return (
    <div className={`screen${source ? ' screen--detail' : ''}`}>
      {source && !backButtonSupported && onBack && (
        <div className="topbar">
          <button type="button" className="topbar__back" onClick={onBack}>
            <Icon name="chevron-left" size={22} />
            Назад
          </button>
          <span />
        </div>
      )}
      <header className="feed-head">
        <h1 className="app-title">{editing ? 'Изменить заявку' : source ? 'Повторить заявку' : 'Новая заявка'}</h1>
        <p className="hint lead">
          {editing
            ? editing.responses_count
              ? 'Тем, кто уже откликнулся, бот пришлёт сообщение об изменениях.'
              : 'Заявка останется в ленте с новыми условиями.'
            : source
              ? 'Всё заполнено как в прошлый раз. Проверьте дату и время и опубликуйте.'
              : 'Исполнители увидят её в ленте и на карте. Обычно первые отклики приходят за минуты.'}
        </p>
      </header>

      <form
        className="form"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <Section icon="briefcase" title="Что за работа">
          <div className={cls('category')}>
            <div className="field__label" id={catLabelId}>
              Категория
            </div>
            <div className="chips chips--wrap" role="radiogroup" aria-labelledby={catLabelId}>
              {meta.categories.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  role="radio"
                  className={`chip${form.category === c.id ? ' chip--on' : ''}`}
                  aria-checked={form.category === c.id}
                  onClick={() => {
                    haptic('select');
                    set({ category: c.id });
                  }}
                >
                  <Icon name={categoryIcon(c.id)} size={16} />
                  {c.label}
                </button>
              ))}
            </div>
            {err('category')}
          </div>

          <label className={cls('title')}>
            <span className="field__label">Что нужно сделать</span>
            <input
              className="input"
              maxLength={80}
              placeholder="Например: грузчики на переезд офиса"
              value={form.title}
              onChange={(e) => set({ title: e.target.value })}
              onBlur={() => touch('title')}
              aria-invalid={!!shown.title}
            />
            {err('title')}
          </label>

          <label className="field">
            <span className="field__label">Подробности</span>
            <textarea
              className="input textarea"
              rows={3}
              maxLength={1000}
              placeholder="Что делать, что взять с собой, есть ли лифт, нужен ли паспорт"
              value={form.description}
              onChange={(e) => set({ description: e.target.value })}
            />
          </label>

          <div className="field field--row">
            <span className="field__label">Сколько человек</span>
            <div className="stepper">
              <button type="button" className="stepper__btn" aria-label="Меньше" disabled={form.workers <= 1} onClick={() => set({ workers: form.workers - 1 })}>
                −
              </button>
              <span className="stepper__value" aria-live="polite">
                {form.workers}
              </span>
              <button
                type="button"
                className="stepper__btn"
                aria-label="Больше"
                disabled={form.workers >= MAX_WORKERS}
                onClick={() => set({ workers: form.workers + 1 })}
              >
                +
              </button>
            </div>
          </div>
        </Section>

        <Section icon="ruble" title="Оплата">
          <div className={cls('pay')}>
            <span className="field__label">Сколько получит один человек</span>
            <div className="row-gap">
              <div className="input-wrap">
                <input
                  className="input input--pay"
                  inputMode="numeric"
                  placeholder="500"
                  maxLength={7}
                  value={form.payAmount}
                  onChange={(e) => set({ payAmount: e.target.value.replace(/[^\d]/g, '') })}
                  onBlur={() => touch('pay')}
                  aria-label="Сумма, ₽"
                  aria-invalid={!!shown.pay}
                />
                <span className="input-wrap__suffix">₽</span>
              </div>
              <select className="input select" value={form.payUnit} onChange={(e) => set({ payUnit: e.target.value as PayUnit })} aria-label="За что">
                {meta.pay_units.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.label}
                  </option>
                ))}
              </select>
            </div>
            {err('pay')}
            {!shown.pay && est && (
              <div className="field__hint">
                {est.approx ? '≈ ' : ''}
                {rub(est.value)}/ч
                {(form.payUnit === 'shift' || form.payUnit === 'day') && !num(form.duration) ? ' (смену считаем за 8 часов)' : ''}
                {' — так ставка выглядит в ленте'}
              </div>
            )}
            {!shown.pay && pay != null && pay > 0 && form.payUnit === 'task' && !est && (
              <div className="field__hint field__hint--muted">Укажите длительность, чтобы в ленте была ставка в час</div>
            )}
          </div>

          <div className="field">
            <span className="field__label">Когда платите</span>
            <div className="chips chips--wrap">
              {TIMING_PRESETS.map((t) => (
                <button
                  key={t}
                  type="button"
                  className={`chip${form.payTiming === t ? ' chip--on' : ''}`}
                  aria-pressed={form.payTiming === t}
                  onClick={() => set({ payTiming: form.payTiming === t ? '' : t })}
                >
                  {t}
                </button>
              ))}
            </div>
            <input
              className="input"
              maxLength={60}
              placeholder="или своими словами (необязательно)"
              aria-label="Когда платите, своими словами"
              value={timingCustom}
              onChange={(e) => set({ payTiming: e.target.value })}
            />
          </div>
        </Section>

        <Section icon="calendar" title="Когда">
          <div className={cls('date')}>
            <div className="segmented" role="radiogroup" aria-label="День">
              {(
                [
                  ['today', 'Сегодня'],
                  ['tomorrow', 'Завтра'],
                  ['pick', 'Другой день'],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={form.dateMode === id}
                  className={`segmented__item${form.dateMode === id ? ' segmented__item--on' : ''}`}
                  onClick={() => set({ dateMode: id })}
                >
                  {label}
                </button>
              ))}
            </div>
            {form.dateMode === 'pick' && (
              <input
                className="input"
                type="date"
                min={mskDay(new Date())}
                value={form.date}
                onChange={(e) => set({ date: e.target.value })}
                onBlur={() => touch('date')}
                aria-label="Дата"
              />
            )}
            {err('date')}
          </div>

          <div className="row-gap">
            <label className={`${cls('time')} grow`}>
              <span className="field__label">Начало</span>
              <input className="input" type="time" value={form.time} onChange={(e) => set({ time: e.target.value })} onBlur={() => touch('time')} />
              {err('time')}
            </label>
            <label className={`${cls('duration')} grow`}>
              <span className="field__label">Часов работы</span>
              <input
                className="input"
                inputMode="decimal"
                placeholder="4"
                maxLength={4}
                value={form.duration}
                onChange={(e) => set({ duration: e.target.value.replace(/[^\d.,]/g, '') })}
                onBlur={() => touch('duration')}
              />
              {err('duration')}
            </label>
          </div>
        </Section>

        <Section icon="pin" title="Где">
          <div className={cls('place')}>
            <button type="button" className="input picker" onClick={() => setMetroOpen(true)} aria-haspopup="dialog">
              {station ? (
                <>
                  <MetroDot color={station.color} /> {station.name}
                </>
              ) : (
                <>
                  <Icon name="metro" size={18} className="hint" />
                  <span className="hint">Станция метро</span>
                </>
              )}
              <Icon name="chevron-down" size={18} className="chip__caret" />
            </button>
            <input
              className="input"
              maxLength={200}
              placeholder={station ? 'Адрес (необязательно)' : 'Адрес'}
              aria-label="Адрес"
              value={form.address}
              onChange={(e) => set({ address: e.target.value })}
              onBlur={() => touch('place')}
            />
            {YMAPS_KEY &&
              (form.point ? (
                <div className="place-point">
                  <button type="button" className="btn btn--sm btn--secondary" onClick={() => setPointOpen(true)}>
                    <Icon name="check" size={16} />
                    Точка на карте выбрана
                  </button>
                  <button type="button" className="icon-btn" onClick={() => set({ point: null })} aria-label="Убрать точку" title="Убрать точку">
                    <Icon name="x" size={18} />
                  </button>
                </div>
              ) : (
                <button type="button" className="btn btn--sm btn--secondary" onClick={() => setPointOpen(true)}>
                  <Icon name="pin" size={16} />
                  Указать на карте
                </button>
              ))}
            {err('place')}
            {!shown.place && <div className="hint small">Достаточно метро или адреса. Точный адрес можно сообщить исполнителю в чате.</div>}
          </div>
        </Section>

        {preview && (
          <section className="form-section form-section--preview">
            <h2 className="form-section__title">
              <Icon name="eye" size={18} />
              Так заявку увидят в ленте
            </h2>
            <JobCard job={preview} category={meta.categories.find((c) => c.id === preview.category)} preview />
          </section>
        )}

        {serverError && (
          <div className="form-error" ref={errorRef} role="alert">
            {serverError}
          </div>
        )}
        {tried && Object.keys(errors).length > 0 && (
          <div className="form-error" role="alert">
            Проверьте поля, отмеченные красным.
          </div>
        )}

        {!mainButtonSupported && (
          <button type="submit" className="btn btn--primary btn--wide btn--lg" disabled={busy}>
            <Icon name={editing ? 'check' : 'send'} size={20} />
            {busy ? (editing ? 'Сохраняем…' : 'Публикуем…') : submitText}
          </button>
        )}
        <div className="hint small center form-foot">
          <Icon name="shield" size={16} />
          Заявки с предоплатой и «оформлением» не публикуем.
        </div>
      </form>

      {pointOpen && (
        <PointPicker
          center={form.point ?? (station ? { lat: station.lat, lng: station.lng } : { lat: meta.city.lat, lng: meta.city.lng })}
          zoom={form.point || station ? 16 : 11}
          onClose={() => setPointOpen(false)}
          onApply={(point, address) => {
            setPointOpen(false);
            set({ point, ...(address && !form.address.trim() ? { address } : {}) });
          }}
        />
      )}

      {metroOpen && (
        <MetroPicker
          single
          stations={meta.metro}
          selected={form.metroId ? [form.metroId] : []}
          onClose={() => setMetroOpen(false)}
          onApply={(ids) => {
            setMetroOpen(false);
            set({ metroId: ids[0] ?? null });
          }}
        />
      )}
    </div>
  );
}
