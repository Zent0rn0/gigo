import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from './Icon';

interface Props {
  title: string;
  onClose(): void;
  children: ReactNode;
  footer?: ReactNode;
}

/** Нижняя шторка поверх экрана. */
export function Sheet({ title, onClose, children, footer }: Props) {
  const titleId = useId();
  const box = useRef<HTMLDivElement | null>(null);
  // фокус внутрь шторки, после закрытия — обратно
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    box.current?.focus({ preventScroll: true });
    return () => prev?.focus?.({ preventScroll: true });
  }, []);
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  // в body: родитель с backdrop-filter/transform стал бы точкой отсчёта для position: fixed
  return createPortal(
    <div className="sheet-backdrop" onClick={onClose}>
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        ref={box}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet__grip" aria-hidden="true" />
        <div className="sheet__head">
          <h2 className="sheet__title" id={titleId}>
            {title}
          </h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Закрыть" title="Закрыть">
            <Icon name="x" size={20} />
          </button>
        </div>
        <div className="sheet__body">{children}</div>
        {footer && <div className="sheet__footer">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
