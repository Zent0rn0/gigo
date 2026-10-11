import { useEffect, useState } from 'react';
import { api, errorText } from '../api';
import { EmptyState, ErrorState, Spinner } from '../components/States';
import { MetroDot } from '../components/MetroDot';
import { rub } from '../format';
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
      toast('Подписка удалена');
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
          <button type="button" className="link-btn topbar__back" onClick={onBack}>
            ‹ Назад
          </button>
        </div>
      )}
      <header className="feed-head">
        <h1 className="app-title">Подписки</h1>
        <p className="hint lead">Новые заявки под ваши фильтры бот пришлёт сообщением в Telegram.</p>
      </header>

      {status === 'loading' && (
        <div className="center pad-xl">
          <Spinner />
        </div>
      )}
      {status === 'error' && <ErrorState text={error} onRetry={() => setAttempt((a) => a + 1)} />}

      {status === 'ready' && subs.length === 0 && (
        <EmptyState
          icon="🔔"
          title="Подписок пока нет"
          text="Настройте фильтр в ленте и нажмите «Подписаться на такие заявки»."
          action={
            <button type="button" className="btn btn--primary" onClick={onGoFeed}>
              Перейти в ленту
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
                  <span className="sub-card__name">{s.name}</span>
                  {!s.enabled && <span className="badge">выключена</span>}
                </div>
                <SubDetails sub={s} meta={meta} />
                <div className="sub-card__actions">
                  {confirmId === s.id ? (
                    <>
                      <button type="button" className="btn btn--sm btn--secondary" onClick={() => setConfirmId(null)} disabled={deleting === s.id}>
                        Отмена
                      </button>
                      <button type="button" className="btn btn--sm btn--danger" onClick={() => remove(s.id)} disabled={deleting === s.id}>
                        {deleting === s.id ? 'Удаляем…' : 'Да, удалить'}
                      </button>
                    </>
                  ) : (
                    <button type="button" className="btn btn--sm btn--ghost-danger" onClick={() => setConfirmId(s.id)}>
                      Удалить
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="hint center pad small">
            {subs.length} из {LIMIT}.{' '}
            {subs.length < LIMIT ? (
              <button type="button" className="link-btn" onClick={onGoFeed}>
                Добавить ещё из ленты
              </button>
            ) : (
              'Это максимум — удалите ненужную, чтобы добавить новую.'
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
        {c ? `${c.emoji} ${c.label}` : id}
      </span>,
    );
  }
  if (!sub.categories.length) tags.push(<span key="all" className="tag">Все категории</span>);
  if (sub.pay_min != null) tags.push(<span key="pay" className="tag">от {rub(sub.pay_min)}/ч</span>);
  for (const id of sub.metro_ids) {
    const m = meta?.metro.find((x) => x.id === id);
    tags.push(
      <span key={`m${id}`} className="tag">
        <MetroDot color={m?.color} /> {m?.name ?? id}
      </span>,
    );
  }
  if (sub.radius_km != null && sub.lat != null) tags.push(<span key="r" className="tag">📍 до {sub.radius_km} км</span>);
  if (sub.today_only) tags.push(<span key="t" className="tag">только сегодня</span>);
  return <div className="tags">{tags}</div>;
}
