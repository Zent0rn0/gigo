import { useMemo, useState } from 'react';
import type { MetroStation } from '../types';
import { Sheet } from './Sheet';
import { MetroDot } from './MetroDot';
import { Icon } from './Icon';

interface Props {
  stations: MetroStation[];
  selected: string[];
  onApply(ids: string[]): void;
  onClose(): void;
  /** Выбор одной станции: нажатие сразу применяет выбор. */
  single?: boolean;
}

const norm = (s: string) => s.toLowerCase().replace(/ё/g, 'е');

export function MetroPicker({ stations, selected, onApply, onClose, single }: Props) {
  const [picked, setPicked] = useState<string[]>(selected);
  const [query, setQuery] = useState('');

  const list = useMemo(() => {
    const q = norm(query.trim());
    const sorted = [...stations].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
    const found = q ? sorted.filter((s) => norm(s.name).includes(q) || norm(s.line).includes(q)) : sorted;
    // выбранные — сверху (порядок фиксируется при открытии и поиске, а не на каждый клик)
    return [...found.filter((s) => picked.includes(s.id)), ...found.filter((s) => !picked.includes(s.id))];
  }, [stations, query]);

  const toggle = (id: string) => {
    if (single) onApply([id]);
    else setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  };

  return (
    <Sheet
      title={single ? 'Станция метро' : 'Метро'}
      onClose={onClose}
      footer={
        single ? (
          picked.length > 0 && (
            <button type="button" className="btn btn--secondary btn--wide" onClick={() => onApply([])}>
              Без метро
            </button>
          )
        ) : (
        <div className="row-gap">
          <button type="button" className="btn btn--secondary" onClick={() => setPicked([])} disabled={!picked.length}>
            Сбросить
          </button>
          <button type="button" className="btn btn--primary btn--grow" onClick={() => onApply(picked)}>
            {picked.length ? `Показать · ${picked.length}` : 'Любая станция'}
          </button>
        </div>
        )
      }
    >
      <label className="search-box">
        <Icon name="search" size={18} />
        <input
          className="input input--search"
          type="search"
          placeholder="Найти станцию или линию"
          aria-label="Найти станцию или линию"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus={false}
        />
      </label>
      <ul className="metro-list">
        {list.map((s) => {
          const on = picked.includes(s.id);
          return (
            <li key={s.id}>
              <label className={`metro-row${on ? ' metro-row--on' : ''}`}>
                <input type={single ? 'radio' : 'checkbox'} name="metro" checked={on} onChange={() => toggle(s.id)} />
                <MetroDot color={s.color} />
                <span className="metro-row__name">{s.name}</span>
                <span className="metro-row__line">{s.line}</span>
              </label>
            </li>
          );
        })}
        {!list.length && <li className="hint pad">Ничего не нашлось</li>}
      </ul>
    </Sheet>
  );
}
