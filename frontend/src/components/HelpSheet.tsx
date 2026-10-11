import { useState, type ReactNode } from 'react';
import { Icon, type IconName } from './Icon';
import { Sheet } from './Sheet';

export type HelpTopic = 'how' | 'safety' | 'report';

const TOPICS: { id: HelpTopic; icon: IconName; title: string; body: ReactNode }[] = [
  {
    id: 'how',
    icon: 'info',
    title: 'Как это работает',
    body: (
      <>
        <p>
          <b>Исполнитель</b> смотрит заявки в ленте или на карте и откликается. <b>Заказчик</b> получает отклик в боте и
          выбирает, кого принять.
        </p>
        <p>
          Когда отклик принят, обоим приходят Telegram-контакты друг друга: договоритесь о деталях напрямую. После работы
          оставьте отзыв — по нему другие поймут, с кем стоит работать.
        </p>
        <p>Gigo бесплатный. Мы не берём комиссию и не участвуем в оплате.</p>
      </>
    ),
  },
  {
    id: 'safety',
    icon: 'shield',
    title: 'Безопасность',
    body: (
      <ul className="help-list">
        <li>
          <b>Не платите вперёд</b> — ни за «оформление», ни за обучение, форму или пропуск. Настоящий заказчик платит вам, а
          не наоборот.
        </li>
        <li>
          <b>Не передавайте карты и коды.</b> Никому не сообщайте коды из SMS, данные карты, пароли, не оформляйте на себя
          карты и счета.
        </li>
        <li>
          <b>Закладки, «курьер с наличными», обнал</b> — это преступление, а не подработка. Сразу жалуйтесь.
        </li>
        <li>Смотрите на рейтинг и отзывы заказчика. Договаривайтесь об оплате до начала работы.</li>
        <li>Встречайтесь в людных местах и скажите близким, куда едете.</li>
      </ul>
    ),
  },
  {
    id: 'report',
    icon: 'flag',
    title: 'Как пожаловаться',
    body: (
      <>
        <p>
          Откройте заявку и нажмите <b>«Пожаловаться»</b> внизу карточки. Выберите причину и, если нужно, коротко опишите,
          что не так.
        </p>
        <p>Жалобы читают модераторы. Заявки с несколькими жалобами скрываются из ленты до проверки, нарушителей блокируем.</p>
      </>
    ),
  },
];

/** Короткая справка: как работает, безопасность, жалобы. */
export function HelpSheet({ onClose, topic = 'how' }: { onClose(): void; topic?: HelpTopic }) {
  const [open, setOpen] = useState<HelpTopic | null>(topic);
  return (
    <Sheet title="Помощь" onClose={onClose}>
      <div className="help">
        {TOPICS.map((t) => {
          const on = open === t.id;
          return (
            <section key={t.id} className={`help-item${on ? ' help-item--open' : ''}`}>
              <button type="button" className="help-item__head" aria-expanded={on} onClick={() => setOpen(on ? null : t.id)}>
                <span className={`help-item__icon help-item__icon--${t.id}`}>
                  <Icon name={t.icon} size={20} />
                </span>
                <span className="help-item__title">{t.title}</span>
                <Icon name="chevron-down" size={20} className="help-item__chev" />
              </button>
              {on && <div className="help-item__body">{t.body}</div>}
            </section>
          );
        })}
      </div>
    </Sheet>
  );
}
