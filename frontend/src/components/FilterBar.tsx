import { useState } from 'react';
import type { Meta } from '../types';
import { EMPTY_FILTERS, PAY_PRESETS, isEmptyFilter, type Filters } from '../filters';
import { rub } from '../format';
import { haptic } from '../telegram';
import { Icon, categoryIcon } from './Icon';
import { MetroDot } from './MetroDot';
import { MetroPicker } from './MetroPicker';
import { Sheet } from './Sheet';

interface Props {
  meta: Meta;
  filters: Filters;
  locating: boolean;
  onChange(f: Filters): void;
  onToggleNear(): void;
}

/** Фильтры ленты: категории и быстрые переключатели в две компактные строки. */
export function FilterBar({ meta, filters, locating, onChange, onToggleNear }: Props) {
  const [metroOpen, setMetroOpen] = useState(false);
  const [payOpen, setPayOpen] = useState(false);

  const set = (patch: Partial<Filters>) => {
    haptic('select');
    onChange({ ...filters, ...patch });
  };
  const toggleCat = (id: string) =>
    set({ categories: filters.categories.includes(id) ? filters.categories.filter((c) => c !== id) : [...filters.categories, id] });

  const selectedMetro = filters.metro.map((id) => meta.metro.find((m) => m.id === id)).filter(Boolean);
  const metroLabel =
    selectedMetro.length === 0 ? 'Метро' : selectedMetro.length === 1 ? selectedMetro[0]!.name : `Метро · ${selectedMetro.length}`;

  return (
    <div className="filters">
      <div className="chips chips--scroll" role="group" aria-label="Категории">
        <button
          type="button"
          className={`chip${filters.categories.length === 0 ? ' chip--on' : ''}`}
          aria-pressed={filters.categories.length === 0}
          onClick={() => set({ categories: [] })}
        >
          Все
        </button>
        {meta.categories.map((c) => {
          const on = filters.categories.includes(c.id);
          return (
            <button key={c.id} type="button" className={`chip${on ? ' chip--on' : ''}`} onClick={() => toggleCat(c.id)} aria-pressed={on}>
              <Icon name={categoryIcon(c.id)} size={16} />
              {c.label}
            </button>
          );
        })}
      </div>

      <div className="chips chips--scroll" role="group" aria-label="Фильтры">
        <button
          type="button"
          className={`chip${filters.nearMe ? ' chip--on' : ''}`}
          onClick={onToggleNear}
          aria-pressed={filters.nearMe}
          disabled={locating}
        >
          {locating ? <span className="spinner spinner--xs" aria-hidden="true" /> : <Icon name="locate" size={16} />}
          {locating ? 'Ищем вас…' : 'Рядом'}
        </button>
        <button type="button" className={`chip${filters.today ? ' chip--on' : ''}`} onClick={() => set({ today: !filters.today })} aria-pressed={filters.today}>
          <Icon name="calendar" size={16} />
          Сегодня
        </button>
        <button
          type="button"
          className={`chip${filters.metro.length ? ' chip--on' : ''}`}
          onClick={() => setMetroOpen(true)}
          aria-haspopup="dialog"
        >
          {selectedMetro.length === 1 ? <MetroDot color={selectedMetro[0]!.color} /> : <Icon name="metro" size={16} />}
          {metroLabel}
          <Icon name="chevron-down" size={14} className="chip__caret" />
        </button>
        <button type="button" className={`chip${filters.payMin != null ? ' chip--on' : ''}`} onClick={() => setPayOpen(true)} aria-haspopup="dialog">
          <Icon name="ruble" size={16} />
          {filters.payMin != null ? `от ${rub(filters.payMin)}/ч` : 'Оплата'}
          <Icon name="chevron-down" size={14} className="chip__caret" />
        </button>
        {!isEmptyFilter(filters) && (
          <button type="button" className="chip chip--ghost" onClick={() => set(EMPTY_FILTERS)}>
            <Icon name="x" size={14} />
            Сбросить
          </button>
        )}
      </div>

      {metroOpen && (
        <MetroPicker
          stations={meta.metro}
          selected={filters.metro}
          onClose={() => setMetroOpen(false)}
          onApply={(ids) => {
            setMetroOpen(false);
            set({ metro: ids });
          }}
        />
      )}
      {payOpen && (
        <PaySheet
          value={filters.payMin}
          onClose={() => setPayOpen(false)}
          onApply={(v) => {
            setPayOpen(false);
            set({ payMin: v });
          }}
        />
      )}
    </div>
  );
}

function PaySheet({ value, onApply, onClose }: { value: number | null; onApply(v: number | null): void; onClose(): void }) {
  const [text, setText] = useState(value != null ? String(value) : '');
  const n = text.trim() === '' ? null : Number(text) || null;
  return (
    <Sheet
      title="Оплата в час"
      onClose={onClose}
      footer={
        <div className="row-gap">
          <button type="button" className="btn btn--secondary" onClick={() => onApply(null)}>
            Любая
          </button>
          <button type="button" className="btn btn--primary btn--grow" onClick={() => onApply(n)}>
            {n ? `Показать от ${rub(n)}/ч` : 'Показать все'}
          </button>
        </div>
      }
    >
      <div className="pay-sheet">
        <p className="hint small">Смену и оплату за работу пересчитываем в рубли за час, чтобы заявки было легко сравнить.</p>
        <div className="chips chips--wrap">
          {PAY_PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              className={`chip${n === p ? ' chip--on' : ''}`}
              aria-pressed={n === p}
              onClick={() => setText(n === p ? '' : String(p))}
            >
              от {p} ₽
            </button>
          ))}
        </div>
        <label className="field">
          <span className="field__label">Своя сумма, ₽/ч от</span>
          <input
            className="input"
            inputMode="numeric"
            pattern="[0-9]*"
            placeholder="Любая"
            value={text}
            maxLength={5}
            onChange={(e) => setText(e.target.value.replace(/\D/g, ''))}
            onKeyDown={(e) => e.key === 'Enter' && onApply(n)}
          />
        </label>
      </div>
    </Sheet>
  );
}
