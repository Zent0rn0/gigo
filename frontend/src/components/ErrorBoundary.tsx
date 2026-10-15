import { Component, Fragment, type ErrorInfo, type ReactNode } from 'react';
import { EmptyState } from './States';
import { Icon } from './Icon';
import { t } from '../i18n';

type Props = {
  children: ReactNode;
  /** Где упало: для сообщения в консоли. */
  name: string;
  /** Экран поверх вкладок: кроме «Повторить» показать «Назад». */
  onBack?(): void;
  /** Корень приложения: «Перезапустить» перезагружает страницу. */
  root?: boolean;
};

type State = { error: Error | null; resets: number };

/** Ошибка при отрисовке экрана не роняет всё приложение: вместо экрана — заглушка с «Повторить». */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, resets: 0 };

  static getDerivedStateFromError(error: unknown): Partial<State> {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error(`[gigo] экран «${this.props.name}» упал`, error, info.componentStack);
  }

  private retry = () => {
    // новый key у детей: экран монтируется заново и сам перезагружает данные
    this.setState((s) => ({ error: null, resets: s.resets + 1 }));
  };

  private restart = () => {
    try {
      window.location.reload();
    } catch {
      this.retry();
    }
  };

  render() {
    if (!this.state.error) return <Fragment key={this.state.resets}>{this.props.children}</Fragment>;
    const { root, onBack } = this.props;
    return (
      <div className={root ? 'app' : 'screen'} role="alert">
        <EmptyState
          icon="alert"
          tone="danger"
          title={t('Что-то сломалось')}
          text={
            root
              ? t('Приложение споткнулось. Перезапустите его, ваши данные на месте.')
              : t('Этот экран не открылся. Попробуйте ещё раз, остальное приложение работает.')
          }
          action={
            <div className="state__actions">
              <button type="button" className="btn btn--primary" onClick={root ? this.restart : this.retry}>
                <Icon name="refresh" size={18} />
                {root ? t('Перезапустить') : t('Повторить')}
              </button>
              {onBack && (
                <button type="button" className="btn btn--secondary" onClick={onBack}>
                  {t('Назад')}
                </button>
              )}
            </div>
          }
        />
      </div>
    );
  }
}
