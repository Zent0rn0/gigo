import { useEffect, useRef, useState } from 'react';
import type { Meta } from '../types';
import { EMPTY_FILTERS, PAY_PRESETS, isEmptyFilter, type Filters } from '../filters';
import { MetroPicker } from './MetroPicker';
import { MetroDot } from './MetroDot';

interface Props {
  meta: Meta;
  filters: Filters;
  locating: boolean;
  onChange(f: Filters): void;
  onToggleNear(): void;
}

export function FilterBar({ meta, filters, locating, onChange, onToggleNear }: Props) {
  const [metroOpen, setMetroOpen] = useState(false);
  const [payText, setPayText] = useState(filters.payMin != null ? String(filters.payMin) : '');
  const latest = useRef(filters);
  latest.current = filters;

  // внешнее изменение (пресет, сброс) → поле ввода
  useEffect(() => {
    setPayText(filters.payMin != null ? String(filters.payMin) : '');
  }, [filters.payMin]);

  // ввод руками применяется с задержкой
  useEffect(() => {
    const n = payText.trim() === '' ? null : Number(payText.replace(/\D/g, '')) || null;
    if (n === latest.current.payMin) return;
    const t = window.setTimeout(() => onChange({ ...latest.current, payMin: n }), 600);
    return () => window.clearTimeout(t);
  }, [payText]);

  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const toggleCat = (id: string) =>
    set({ categories: filters.categories.includes(id) ? filters.categories.filter((c) => c !== id) : [...filters.categories, id] });

  const selectedMetro = filters.metro.map((id) => meta.metro.find((m) => m.id === id)).filter(Boolean);
  const metroLabel =
    selectedMetro.length === 0
      ? 'Метро'
      : selectedMetro.length === 1
        ? selectedMetro[0]!.name
        : `Метро · ${selectedMetro.length}`;

  return (
    <div className="filters">
      <div className="chips chips--scroll" role="group" aria-label="Категории">
        <button
          type="button"
          className={`chip${filters.categories.length === 0 ? ' chip--on' : ''}`}
          onClick={() => set({ categories: [] })}
        >
          Все
        </button>
        {meta.categories.map((c) => (
          <button
            key={c.id}
            type="button"
            className={`chip${filters.categories.includes(c.id) ? ' chip--on' : ''}`}
            onClick={() => toggleCat(c.id)}
            aria-pressed={filters.categories.includes(c.id)}
          >
            <span aria-hidden="true">{c.emoji}</span> {c.label}
          </button>
        ))}
      </div>

      <div className="chips chips--scroll">
        <button
          type="button"
          className={`chip${filters.nearMe ? ' chip--on' : ''}`}
          onClick={onToggleNear}
          aria-pressed={filters.nearMe}
          disabled={locating}
        >
          <span aria-hidden="true">{locating ? '⏳' : '📍'}</span> {locating ? 'Определяем…' : 'Рядом со мной'}
        </button>
        <button
          type="button"
          className={`chip${filters.today ? ' chip--on' : ''}`}
          onClick={() => set({ today: !filters.today })}
          aria-pressed={filters.today}
        >
          Сегодня
        </button>
        <button type="button" className={`chip${filters.metro.length ? ' chip--on' : ''}`} onClick={() => setMetroOpen(true)}>
          {selectedMetro.length === 1 ? <MetroDot color={selectedMetro[0]!.color} /> : <span aria-hidden="true">Ⓜ️</span>}{' '}
          {metroLabel} <span className="chip__caret">▾</span>
        </button>
        {!isEmptyFilter(filters) && (
          <button type="button" className="chip chip--ghost" onClick={() => onChange(EMPTY_FILTERS)}>
            Сбросить
          </button>
        )}
      </div>

      <div className="pay-row">
        <label className="pay-input">
          <span className="pay-input__label">₽/час от</span>
          <input
            className="input"
            inputMode="numeric"
            pattern="[0-9]*"
            placeholder="любая"
            value={payText}
            maxLength={5}
            onChange={(e) => setPayText(e.target.value.replace(/\D/g, ''))}
          />
        </label>
        <div className="chips">
          {PAY_PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              className={`chip chip--sm${filters.payMin === p ? ' chip--on' : ''}`}
              onClick={() => set({ payMin: filters.payMin === p ? null : p })}
            >
              {p}
            </button>
          ))}
        </div>
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
    </div>
  );
}
