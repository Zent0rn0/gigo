import { useEffect, useState } from 'react';
import { api, errorText } from '../api';
import { EmptyState, ErrorState, Spinner } from '../components/States';
import { Icon, categoryIcon } from '../components/Icon';
import { MetroDot } from '../components/MetroDot';
import { rub } from '../format';
import { t } from '../i18n';
import { backButtonSupported, haptic } from '../telegram';
import type { Meta, Subscription } from '../types';

interface Props {
  meta: Meta | null;
  onBack(): void;
  onGoFeed(): void;
  toast(text: string): void;
}

const LIMIT = 10;

export function Subscriptions({ meta, onBack, onGoFeed, toast }: Props) {
  const [subs, setSubs] = useState<Subscription[]>([]);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    setStatus((s) => (s === 'ready' ? s : 'loading'));
    api
      .subscriptions()
      .then((list) => {
        if (!alive) return;
        setSubs(list);
        setStatus('ready');
      })
      .catch((e) => {
        if (!alive) return;
        setError(errorText(e));
        setStatus('error');
      });
    return () => {
      alive = false;
    };
  }, [attempt]);

  const remove = async (id: number) => {
    setDeleting(id);
    try {
      await api.deleteSubscription(id);
      setSubs((l) => l.filter((s) => s.id !== id));
      haptic('success');
      toast(t('Подписка удалена'));
    } catch (e) {
      haptic('error');
      toast(errorText(e));
    } finally {
      setDeleting(null);
      setConfirmId(null);
    }
  };

  return (
    <div className="screen screen--detail">
      {!backButtonSupported && (
        <div className="topbar">
          <button type="button" className="topbar__back" onClick={onBack}>
            <Icon name="chevron-left" size={22} />
            {t('Назад')}
          </button>
        </div>
      )}
      <header className="feed-head">
        <h1 className="app-title">{t('Подписки')}</h1>
        <p className="hint lead">{t('Новые заявки под ваши фильтры бот пришлёт сообщением в Telegram.')}</p>
      </header>

      {status === 'loading' && (
        <div className="center pad-xl">
          <Spinner />
        </div>
      )}
      {status === 'error' && <ErrorState text={error} onRetry={() => setAttempt((a) => a + 1)} />}

      {status === 'ready' && subs.length === 0 && (
        <EmptyState
          icon="bell"
          tone="brand"
          title={t('Подписок пока нет')}
          text={t('Настройте фильтр в ленте и нажмите «Подписаться на такие заявки».')}
          action={
            <button type="button" className="btn btn--primary" onClick={onGoFeed}>
              {t('Перейти в ленту')}
            </button>
          }
        />
      )}

      {status === 'ready' && subs.length > 0 && (
        <>
          <div className="list">
            {subs.map((s) => (
              <div key={s.id} className={`sub-card${s.enabled ? '' : ' sub-card--off'}`}>
                <div className="sub-card__head">
                  <span className="sub-card__name">
                    <Icon name="bell" size={18} className="sub-card__bell" />
                    {s.name}
                  </span>
                  {!s.enabled && <span className="badge">{t('выключена')}</span>}
                </div>
                <SubDetails sub={s} meta={meta} />
                <div className="sub-card__actions">
                  {confirmId === s.id ? (
                    <>
                      <button type="button" className="btn btn--sm btn--secondary" onClick={() => setConfirmId(null)} disabled={deleting === s.id}>
                        {t('Отмена')}
                      </button>
                      <button type="button" className="btn btn--sm btn--danger" onClick={() => remove(s.id)} disabled={deleting === s.id}>
                        {deleting === s.id ? t('Удаляем…') : t('Да, удалить')}
                      </button>
                    </>
                  ) : (
                    <button type="button" className="btn btn--sm btn--ghost-danger" onClick={() => setConfirmId(s.id)}>
                      <Icon name="trash" size={16} />
                      {t('Удалить')}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="hint center pad small">
            {t('{n} из {max}.', { n: subs.length, max: LIMIT })}{' '}
            {subs.length < LIMIT ? (
              <button type="button" className="link-btn" onClick={onGoFeed}>
                {t('Добавить ещё из ленты')}
              </button>
            ) : (
              t('Это максимум — удалите ненужную, чтобы добавить новую.')
            )}
          </div>
        </>
      )}
    </div>
  );
}

function SubDetails({ sub, meta }: { sub: Subscription; meta: Meta | null }) {
  const tags: JSX.Element[] = [];
  for (const id of sub.categories) {
    const c = meta?.categories.find((x) => x.id === id);
    tags.push(
      <span key={`c${id}`} className="tag">
        <Icon name={categoryIcon(id)} size={14} />
        {c ? c.label : id}
      </span>,
    );
  }
  if (!sub.categories.length) tags.push(<span key="all" className="tag">{t('Все категории')}</span>);
  if (sub.pay_min != null) tags.push(<span key="pay" className="tag"><Icon name="ruble" size={14} />{t('от {sum}/ч', { sum: rub(sub.pay_min) })}</span>);
  for (const id of sub.metro_ids) {
    const m = meta?.metro.find((x) => x.id === id);
    tags.push(
      <span key={`m${id}`} className="tag">
        <MetroDot color={m?.color} /> {m?.name ?? id}
      </span>,
    );
  }
  if (sub.radius_km != null && sub.lat != null) tags.push(<span key="r" className="tag"><Icon name="locate" size={14} />{t('до {km} км от вас', { km: sub.radius_km })}</span>);
  if (sub.today_only) tags.push(<span key="t" className="tag"><Icon name="calendar" size={14} />{t('только сегодня')}</span>);
  return <div className="tags">{tags}</div>;
}
