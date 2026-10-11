import { useRef, useState } from 'react';
import { api, errorText } from '../api';
import { MetroPicker } from '../components/MetroPicker';
import { MetroDot } from '../components/MetroDot';
import { PointPicker, type Point } from '../components/PointPicker';
import { estimatePerHour, mskDay, rub } from '../format';
import { useMainButton } from '../mainButton';
import { haptic, mainButtonSupported } from '../telegram';
import type { Job, JobIn, Meta, PayUnit } from '../types';
import { YMAPS_KEY } from '../ymaps';

interface Props {
  meta: Meta;
  active: boolean;
  onCreated(job: Job): void;
  toast(text: string): void;
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

export function CreateJob({ meta, active, onCreated, toast }: Props) {
  const [form, setForm] = useState<Form>(EMPTY);
  const [tried, setTried] = useState(false);
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
  const shown: Errors = tried ? errors : {};
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
      const job = await api.createJob(toBody(form));
      haptic('success');
      toast('Заявка опубликована. Сообщим, когда кто-то откликнется.');
      setForm(EMPTY);
      setTried(false);
      onCreated(job);
    } catch (e) {
      haptic('error');
      setServerError(errorText(e));
      window.setTimeout(() => errorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 0);
    } finally {
      setBusy(false);
    }
  };

  useMainButton(active && !metroOpen && !pointOpen ? { text: 'Опубликовать заявку', onClick: submit, progress: busy } : null);

  const cls = (k: keyof Errors) => `field${shown[k] ? ' field--error' : ''}`;
  const err = (k: keyof Errors) => shown[k] && <div className="field__error">{shown[k]}</div>;

  return (
    <div className="screen">
      <header className="feed-head">
        <h1 className="app-title">Новая заявка</h1>
        <p className="hint lead">Исполнители увидят её в ленте и на карте и откликнутся.</p>
      </header>

      <form
        className="form"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className={cls('category')}>
          <div className="field__label">Категория</div>
          <div className="chips chips--wrap">
            {meta.categories.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`chip${form.category === c.id ? ' chip--on' : ''}`}
                aria-pressed={form.category === c.id}
                onClick={() => set({ category: c.id })}
              >
                <span aria-hidden="true">{c.emoji}</span> {c.label}
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
          />
          {err('title')}
        </label>

        <label className="field">
          <span className="field__label">Подробности</span>
          <textarea
            className="input textarea"
            rows={3}
            maxLength={1000}
            placeholder="Что делать, что взять с собой, есть ли лифт…"
            value={form.description}
            onChange={(e) => set({ description: e.target.value })}
          />
        </label>

        <div className="field">
          <span className="field__label">Сколько человек</span>
          <div className="stepper">
            <button type="button" className="stepper__btn" aria-label="Меньше" disabled={form.workers <= 1} onClick={() => set({ workers: form.workers - 1 })}>
              −
            </button>
            <span className="stepper__value">{form.workers}</span>
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

        <div className={cls('pay')}>
          <span className="field__label">Оплата одному человеку</span>
          <div className="row-gap">
            <div className="input-wrap">
              <input
                className="input"
                inputMode="numeric"
                placeholder="500"
                maxLength={7}
                value={form.payAmount}
                onChange={(e) => set({ payAmount: e.target.value.replace(/[^\d]/g, '') })}
                aria-label="Сумма, ₽"
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
            <div className="field__hint">Укажите длительность, чтобы в ленте была ставка в час</div>
          )}
        </div>

        <div className="field">
          <span className="field__label">Когда платите</span>
          <div className="chips chips--wrap">
            {TIMING_PRESETS.map((t) => (
              <button
                key={t}
                type="button"
                className={`chip chip--sm${form.payTiming === t ? ' chip--on' : ''}`}
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
            value={TIMING_PRESETS.includes(form.payTiming) ? '' : form.payTiming}
            onChange={(e) => set({ payTiming: e.target.value })}
          />
        </div>

        <div className={cls('date')}>
          <span className="field__label">Когда</span>
          <div className="segmented">
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
                className={`segmented__item${form.dateMode === id ? ' segmented__item--on' : ''}`}
                onClick={() => set({ dateMode: id })}
              >
                {label}
              </button>
            ))}
          </div>
          {form.dateMode === 'pick' && (
            <input className="input" type="date" min={mskDay(new Date())} value={form.date} onChange={(e) => set({ date: e.target.value })} aria-label="Дата" />
          )}
          {err('date')}
        </div>

        <div className="row-gap">
          <label className={`${cls('time')} grow`}>
            <span className="field__label">Начало</span>
            <input className="input" type="time" value={form.time} onChange={(e) => set({ time: e.target.value })} />
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
            />
            {err('duration')}
          </label>
        </div>

        <div className={cls('place')}>
          <span className="field__label">Где</span>
          <button type="button" className="input picker" onClick={() => setMetroOpen(true)}>
            {station ? (
              <>
                <MetroDot color={station.color} /> {station.name}
              </>
            ) : (
              <span className="hint">Ⓜ️ Станция метро</span>
            )}
            <span className="chip__caret">▾</span>
          </button>
          <input
            className="input"
            maxLength={200}
            placeholder="Адрес (необязательно, если указано метро)"
            value={form.address}
            onChange={(e) => set({ address: e.target.value })}
          />
          {YMAPS_KEY &&
            (form.point ? (
              <div className="place-point">
                <button type="button" className="btn btn--sm" onClick={() => setPointOpen(true)}>
                  📍 Точка на карте выбрана
                </button>
                <button type="button" className="icon-btn" onClick={() => set({ point: null })} aria-label="Убрать точку">
                  ✕
                </button>
              </div>
            ) : (
              <button type="button" className="btn btn--sm" onClick={() => setPointOpen(true)}>
                📍 Указать на карте
              </button>
            ))}
          {err('place')}
        </div>

        {serverError && (
          <div className="form-error" ref={errorRef} role="alert">
            {serverError}
          </div>
        )}
        {tried && Object.keys(errors).length > 0 && <div className="form-error">Проверьте поля, отмеченные красным.</div>}

        {!mainButtonSupported && (
          <button type="submit" className="btn btn--primary btn--wide" disabled={busy}>
            {busy ? 'Публикуем…' : 'Опубликовать заявку'}
          </button>
        )}
        <div className="hint small center">Без предоплат и «оформления»: такие заявки не пропускаем.</div>
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
