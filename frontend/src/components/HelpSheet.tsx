import { useState, type ReactNode } from 'react';
import { t } from '../i18n';
import { Icon, type IconName } from './Icon';
import { Sheet } from './Sheet';

export type HelpTopic = 'how' | 'safety' | 'report';

/** Текст перевода с <b>…</b> внутри: жирные куски — элементами, чтобы порядок слов задавал перевод. */
function rich(text: string): ReactNode {
  const parts = text.split(/<b>(.*?)<\/b>/);
  return parts.map((p, i) => (i % 2 ? <b key={i}>{p}</b> : p));
}

/** Темы справки; функция, а не константа: тексты переводятся при показе. */
function topics(): { id: HelpTopic; icon: IconName; title: string; body: ReactNode }[] {
  return [
    {
      id: 'how',
      icon: 'info',
      title: t('Как это работает'),
      body: (
        <>
          <p>
            {rich(
              t(
                '<b>Исполнитель</b> смотрит заявки в ленте или на карте и откликается. <b>Заказчик</b> получает отклик в боте и выбирает, кого принять.',
              ),
            )}
          </p>
          <p>
            {t(
              'Когда отклик принят, обоим приходят Telegram-контакты друг друга: договоритесь о деталях напрямую. После работы оставьте отзыв — по нему другие поймут, с кем стоит работать.',
            )}
          </p>
          <p>{t('Gigo бесплатный. Мы не берём комиссию и не участвуем в оплате.')}</p>
        </>
      ),
    },
    {
      id: 'safety',
      icon: 'shield',
      title: t('Безопасность'),
      body: (
        <ul className="help-list">
          <li>
            {rich(
              t(
                '<b>Не платите вперёд</b> — ни за «оформление», ни за обучение, форму или пропуск. Настоящий заказчик платит вам, а не наоборот.',
              ),
            )}
          </li>
          <li>
            {rich(
              t(
                '<b>Не передавайте карты и коды.</b> Никому не сообщайте коды из SMS, данные карты, пароли, не оформляйте на себя карты и счета.',
              ),
            )}
          </li>
          <li>{rich(t('<b>Закладки, «курьер с наличными», обнал</b> — это преступление, а не подработка. Сразу жалуйтесь.'))}</li>
          <li>{t('Смотрите на рейтинг и отзывы заказчика. Договаривайтесь об оплате до начала работы.')}</li>
          <li>{t('Встречайтесь в людных местах и скажите близким, куда едете.')}</li>
        </ul>
      ),
    },
    {
      id: 'report',
      icon: 'flag',
      title: t('Как пожаловаться'),
      body: (
        <>
          <p>
            {rich(
              t(
                'Откройте заявку и нажмите <b>«Пожаловаться»</b> внизу карточки. Выберите причину и, если нужно, коротко опишите, что не так.',
              ),
            )}
          </p>
          <p>{t('Жалобы читают модераторы. Заявки с несколькими жалобами скрываются из ленты до проверки, нарушителей блокируем.')}</p>
        </>
      ),
    },
  ];
}

/** Короткая справка: как работает, безопасность, жалобы. */
export function HelpSheet({ onClose, topic = 'how' }: { onClose(): void; topic?: HelpTopic }) {
  const [open, setOpen] = useState<HelpTopic | null>(topic);
  return (
    <Sheet title={t('Помощь')} onClose={onClose}>
      <div className="help">
        {topics().map((item) => {
          const on = open === item.id;
          return (
            <section key={item.id} className={`help-item${on ? ' help-item--open' : ''}`}>
              <button type="button" className="help-item__head" aria-expanded={on} onClick={() => setOpen(on ? null : item.id)}>
                <span className={`help-item__icon help-item__icon--${item.id}`}>
                  <Icon name={item.icon} size={20} />
                </span>
                <span className="help-item__title">{item.title}</span>
                <Icon name="chevron-down" size={20} className="help-item__chev" />
              </button>
              {on && <div className="help-item__body">{item.body}</div>}
            </section>
          );
        })}
      </div>
    </Sheet>
  );
}
