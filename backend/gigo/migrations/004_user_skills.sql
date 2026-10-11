-- Что умеет исполнитель: id категорий из справочника. Видно заказчику в отклике и в профиле.
ALTER TABLE users ADD COLUMN skills TEXT[] NOT NULL DEFAULT '{}';
