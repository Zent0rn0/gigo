import { useEffect, useRef } from 'react';
import { BRAND_COLOR, mainButtonSupported, tg } from './telegram';

export interface MainButtonConfig {
  text: string;
  onClick(): void;
  disabled?: boolean;
  progress?: boolean;
}

/**
 * Нижняя кнопка Telegram. cfg = null — кнопка не нужна этому экрану.
 * Вне Telegram ничего не делает: экран сам рисует обычную кнопку (см. mainButtonSupported).
 * Скрытый экран должен передавать null, чтобы не перехватывать кнопку у видимого.
 */
export function useMainButton(cfg: MainButtonConfig | null): void {
  const click = useRef<(() => void) | undefined>(cfg?.onClick);
  click.current = cfg?.onClick;
  const visible = !!cfg && mainButtonSupported;
  const mb = tg?.MainButton;

  useEffect(() => {
    if (!visible || !mb) return;
    const h = () => click.current?.();
    mb.onClick(h);
    try {
      mb.setParams?.({ color: BRAND_COLOR, text_color: '#FFFFFF' });
    } catch {
      /* старый клиент */
    }
    mb.show();
    return () => {
      mb.offClick(h);
      try {
        mb.hideProgress();
      } catch {
        /* старый клиент */
      }
      mb.hide();
    };
  }, [visible, mb]);

  const text = cfg?.text ?? '';
  const disabled = !!cfg?.disabled;
  const progress = !!cfg?.progress;
  useEffect(() => {
    if (!visible || !mb) return;
    try {
      mb.setText(text);
      if (disabled || progress) mb.disable();
      else mb.enable();
      if (progress) mb.showProgress(false);
      else mb.hideProgress();
    } catch {
      /* старый клиент */
    }
  }, [visible, mb, text, disabled, progress]);
}
