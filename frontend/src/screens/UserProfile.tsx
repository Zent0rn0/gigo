import { useEffect, useState } from 'react';
import { api, ApiError, errorText } from '../api';
import { EmptyState, ErrorState, Spinner } from '../components/States';
import { Icon } from '../components/Icon';
import { Avatar, SkillChips, Stars } from '../components/ui';
import { formatDate, formatRating, plural } from '../format';
import { backButtonSupported } from '../telegram';
import type { Meta, UserProfile as Profile } from '../types';

export function UserProfile({ userId, isMe, meta, onBack }: { userId: number; isMe: boolean; meta: Meta; onBack(): void }) {
  const [user, setUser] = useState<Profile | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'notfound' | 'error'>('loading');
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let alive = true;
    setStatus('loading');
    api
      .user(userId)
      .then((u) => {
        if (!alive) return;
        setUser(u);
        setStatus('ready');
      })
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) setStatus('notfound');
        else {
          setError(errorText(e));
          setStatus('error');
        }
      });
    return () => {
      alive = false;
    };
  }, [userId, attempt]);

  useEffect(() => window.scrollTo(0, 0), [userId]);

  return (
    <div className="screen screen--detail">
      {!backButtonSupported && (
        <div className="topbar">
          <button type="button" className="topbar__back" onClick={onBack}>
            <Icon name="chevron-left" size={22} />
            Назад
          </button>
        </div>
      )}
      {status === 'loading' && (
        <div className="center pad-xl">
          <Spinner />
        </div>
      )}
      {status === 'notfound' && <EmptyState icon="user" title="Профиль не найден" />}
      {status === 'error' && <ErrorState text={error} onRetry={() => setAttempt((a) => a + 1)} />}
      {status === 'ready' && user && (
        <>
          <div className="detail profile-card">
            <Avatar name={user.first_name} size={72} />
            <h1 className="detail__title">
              {user.first_name}
              {isMe && <span className="hint"> · это вы</span>}
            </h1>
            <div className="hint profile-card__role">
              <Icon name={user.role === 'employer' ? 'users' : 'briefcase'} size={16} />
              {user.role === 'employer' ? 'Заказчик' : user.role === 'worker' ? 'Исполнитель' : 'Новичок'}
              {' · '}
              {user.role === 'employer'
                ? `${user.jobs_count} ${plural(user.jobs_count, ['заявка', 'заявки', 'заявок'])}`
                : `${user.jobs_count} ${plural(user.jobs_count, ['работа', 'работы', 'работ'])}`}
            </div>
            <div className="profile-card__rating">
              {user.rating != null ? (
                <>
                  <span className="profile-card__score">{user.rating.toFixed(1).replace('.', ',')}</span>
                  <Stars value={Math.round(user.rating)} />
                  <span className="hint small">{formatRating(user.rating, user.reviews_count).replace(/^★ [\d,]+ · /, '')}</span>
                </>
              ) : (
                <span className="hint">Отзывов пока нет</span>
              )}
            </div>
            {user.role === 'worker' && !!user.skills?.length && <SkillChips ids={user.skills} meta={meta} />}
            {user.about && <p className="detail__desc profile-card__about">{user.about}</p>}
          </div>

          {user.reviews.length === 0 && user.rating == null && (
            <p className="hint small center pad">Отзывы появятся после первой работы через Gigo.</p>
          )}
          {user.reviews.length > 0 && (
            <section>
              <h2 className="list-title">Отзывы</h2>
              <div className="list">
                {user.reviews.map((r, i) => (
                  <div key={i} className="review-card">
                    <div className="row-between">
                      <Stars value={r.rating} size="sm" />
                      <span className="hint small">{formatDate(r.created_at)}</span>
                    </div>
                    {r.text && <p className="review-card__text">{r.text}</p>}
                    <div className="hint small">
                      {r.author.first_name}
                      {r.job_title ? ` · ${r.job_title}` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
