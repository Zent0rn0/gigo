// Тестовые данные для VITE_MOCK=1. Время считается от текущего момента, чтобы «сегодня»/«13 мин назад» были живыми.
import type { Category, Job, JobMetro, Meta, MetroStation, PayUnitOption, Role, Subscription } from '../types';
import { mskDay } from '../format';

export const categories: Category[] = [
  { id: 'loader', label: 'Грузчики', emoji: '📦' },
  { id: 'courier', label: 'Курьеры', emoji: '🚶' },
  { id: 'warehouse', label: 'Склад', emoji: '🏭' },
  { id: 'cleaning', label: 'Уборка', emoji: '🧹' },
  { id: 'construction', label: 'Стройка', emoji: '🔨' },
  { id: 'promo', label: 'Промоутеры', emoji: '📣' },
  { id: 'kitchen', label: 'Общепит', emoji: '🍳' },
  { id: 'driver', label: 'Водители', emoji: '🚗' },
  { id: 'event', label: 'Мероприятия', emoji: '🎪' },
  { id: 'other', label: 'Другое', emoji: '🧩' },
];

const L = {
  1: ['Сокольническая', '#D41317'],
  2: ['Замоскворецкая', '#4BAF4F'],
  3: ['Арбатско-Покровская', '#0072BA'],
  5: ['Кольцевая', '#915133'],
  6: ['Калужско-Рижская', '#F07E24'],
  7: ['Таганско-Краснопресненская', '#943E90'],
  8: ['Калининская', '#FFCD1C'],
  9: ['Серпуховско-Тимирязевская', '#ADACAC'],
  10: ['Люблинско-Дмитровская', '#BED12C'],
} as const;

function st(id: string, name: string, line: keyof typeof L, lat: number, lng: number): MetroStation {
  return { id, name, line: L[line][0], color: L[line][1], lat, lng };
}

export const metro: MetroStation[] = [
  st('1.1', 'Сокольники', 1, 55.7893, 37.68),
  st('1.2', 'Комсомольская', 1, 55.7757, 37.6553),
  st('1.3', 'Парк культуры', 1, 55.7353, 37.5934),
  st('2.1', 'Тверская', 2, 55.7652, 37.604),
  st('2.2', 'Белорусская', 2, 55.7771, 37.5822),
  st('3.1', 'Курская', 3, 55.7586, 37.6611),
  st('3.2', 'Киевская', 3, 55.7432, 37.5654),
  st('3.3', 'Митино', 3, 55.8462, 37.3618),
  st('6.1', 'Октябрьская', 6, 55.7293, 37.6111),
  st('6.2', 'ВДНХ', 6, 55.8196, 37.6413),
  st('6.3', 'Китай-город', 6, 55.7564, 37.6314),
  st('7.1', 'Таганская', 7, 55.7393, 37.6533),
  st('7.2', 'Кузьминки', 7, 55.7055, 37.7656),
  st('7.3', 'Выхино', 7, 55.7159, 37.8174),
  st('7.4', 'Тушинская', 7, 55.8256, 37.4369),
  st('8.1', 'Новогиреево', 8, 55.7519, 37.8165),
  st('9.1', 'Савёловская', 9, 55.794, 37.5872),
  st('9.2', 'Чертановская', 9, 55.6406, 37.6064),
  st('10.1', 'Марьино', 10, 55.6497, 37.7437),
];

export const payUnits: PayUnitOption[] = [
  { id: 'hour', label: 'за час' },
  { id: 'shift', label: 'за смену' },
  { id: 'day', label: 'за день' },
  { id: 'task', label: 'за работу' },
];

export const meta: Meta = {
  categories,
  pay_units: payUnits,
  metro,
  city: { id: 'moscow', name: 'Москва', lat: 55.7558, lng: 37.6176 },
};

export function m(id: string): JobMetro {
  const s = metro.find((x) => x.id === id)!;
  return { id: s.id, name: s.name, line: s.line, color: s.color };
}

/** ISO со смещением +03:00, как отдаёт бэкенд. */
export function msk(d: Date): string {
  return new Date(d.getTime() + 3 * 3600e3).toISOString().slice(0, 19) + '+03:00';
}


// ——— люди ———

export interface UserRec {
  id: number;
  first_name: string;
  username: string | null;
  role: Role | null;
  about: string | null;
  skills?: string[];
  /** Работ, сделанных до начала «истории» мока (для jobs_count исполнителя). */
  done_before: number;
}

/** Текущий пользователь мока. Роль не выбрана, чтобы показать онбординг. */
export const ME_ID = 1;

export const users: UserRec[] = [
  { id: ME_ID, first_name: 'Алексей', username: 'alexey_k', role: null, about: null, done_before: 0 },
  { id: 900000001, first_name: 'Ольга', username: 'olga_moves', role: 'employer', about: 'Офис-менеджер, часто нужны грузчики и курьеры.', done_before: 0 },
  { id: 900000002, first_name: 'Сергей', username: null, role: 'employer', about: 'Склад на Рязанке.', done_before: 0 },
  { id: 900000003, first_name: 'Марина', username: 'marina_cafe', role: 'employer', about: 'Кафе у Белорусской.', done_before: 0 },
  { id: 900000004, first_name: 'Дмитрий', username: 'dima_build', role: 'employer', about: null, done_before: 0 },
  { id: 777, first_name: 'Иван', username: 'ivan_work', role: 'worker', about: 'Опыт на складе 2 года, есть права B.', skills: ['loader', 'warehouse', 'driver'], done_before: 6 },
  { id: 778, first_name: 'Мария', username: 'masha_clean', role: 'worker', about: 'Уборка квартир и офисов, свои средства.', skills: ['cleaning'], done_before: 11 },
  { id: 779, first_name: 'Тимур', username: null, role: 'worker', about: 'Студент, свободен вечером и в выходные.', done_before: 1 },
  { id: 780, first_name: 'Павел', username: 'pavel_m', role: 'worker', about: 'Крепкий, без вредных привычек. Могу с инструментом.', done_before: 3 },
];

export interface ReviewRec {
  id: number;
  response_id: number | null;
  author_id: number;
  target_id: number;
  rating: number;
  text: string | null;
  job_title: string | null;
  created_at: string;
}

export interface ResponseRec {
  id: number;
  job_id: number;
  worker_id: number;
  status: 'pending' | 'accepted' | 'rejected' | 'withdrawn';
  message: string | null;
  created_at: string;
}

/** Заявка в «базе»: без полей, которые зависят от смотрящего. */
export type JobRec = Omit<Job, 'employer' | 'responses_count' | 'accepted_count' | 'is_mine' | 'my_response' | 'distance_km' | 'responses' | 'pending_count'> & {
  employer_id: number;
};

export interface World {
  jobs: JobRec[];
  responses: ResponseRec[];
  reviews: ReviewRec[];
}

export function buildWorld(now = new Date()): World {
  const hourStart = new Date(Math.ceil(now.getTime() / 3600e3) * 3600e3);
  const at = (h: number) => new Date(hourStart.getTime() + h * 3600e3);
  const ago = (min: number) => msk(new Date(now.getTime() - min * 60e3));
  const day = (d: number) => mskDay(new Date(now.getTime() + d * 864e5));

  type Seed = Partial<JobRec> & Pick<JobRec, 'id' | 'category' | 'title' | 'employer_id'> & { seenMin: number; startH?: number; stationId?: string };

  const OLGA = 900000001;
  const SERGEY = 900000002;
  const MARINA = 900000003;
  const DMITRY = 900000004;

  const seeds: Seed[] = [
    {
      id: 42, employer_id: OLGA, category: 'loader', title: 'Грузчики на переезд офиса', workers_needed: 2,
      pay_amount: 500, pay_unit: 'hour', pay_per_hour: 500, pay_estimated: false, pay_total: 2000, pay_timing: 'сразу',
      startH: 1, duration_hours: 4, stationId: '7.1', address: 'Большая Коммунистическая ул., 15',
      description: 'Переезд офиса, нужны 2 человека на ~4 часа. Мебель и коробки, есть лифт. Оплата сразу на карту.',
      seenMin: 13,
    },
    {
      id: 43, employer_id: OLGA, category: 'courier', title: 'Пеший курьер · документы по центру', workers_needed: 1,
      pay_amount: 3000, pay_unit: 'day', pay_per_hour: 375, pay_estimated: false, pay_total: 3000, pay_timing: 'в конце дня',
      startH: 2, duration_hours: 8, stationId: '2.1',
      description: 'Разнос документов по офисам в пределах Садового кольца. Проездной компенсируем.',
      seenMin: 27,
    },
    {
      id: 44, employer_id: SERGEY, category: 'warehouse', title: 'Комплектовщик на склад · ночная смена', workers_needed: 5,
      pay_amount: 3500, pay_unit: 'shift', pay_per_hour: 292, pay_estimated: false, pay_total: 3500, pay_timing: 'еженедельно',
      startH: 30, duration_hours: 12, stationId: '7.3', address: 'Рязанский пр-т, 2, склад №4',
      description: 'Сборка заказов на складе маркетплейса. Смена 20:00–08:00, питание за счёт компании. Паспорт РФ/ЕАЭС.',
      seenMin: 64,
    },
    {
      id: 45, employer_id: DMITRY, category: 'cleaning', title: 'Уборка квартиры после ремонта', workers_needed: 1,
      pay_amount: 4000, pay_unit: 'task', pay_per_hour: 667, pay_estimated: false, pay_total: 4000, pay_timing: 'сразу',
      startH: 3, duration_hours: 6, stationId: '10.1',
      description: '2-комнатная квартира, строительная пыль, мытьё окон. Инвентарь и химия есть.',
      seenMin: 95,
    },
    {
      id: 46, employer_id: DMITRY, category: 'construction', title: 'Разнорабочие на стройку частного дома', workers_needed: 3,
      pay_amount: 600, pay_unit: 'hour', pay_per_hour: 600, pay_estimated: false, pay_total: 4800, pay_timing: 'сразу',
      startH: 20, duration_hours: 8, stationId: '3.3',
      description: 'Подсобные работы: разгрузка блоков, уборка мусора. Перчатки выдаём. Сбор у метро, довезём.',
      seenMin: 140,
    },
    {
      id: 47, employer_id: MARINA, category: 'promo', title: 'Промоутер у метро · листовки', workers_needed: 2,
      pay_amount: 400, pay_unit: 'hour', pay_per_hour: 400, pay_estimated: false, pay_total: 1200, pay_timing: 'сразу',
      startH: 22, duration_hours: 3, stationId: '3.1',
      description: 'Раздача листовок у выхода из метро. 3 часа, форма не нужна.',
      seenMin: 180,
    },
    {
      id: 48, employer_id: MARINA, category: 'kitchen', title: 'Помощник повара в кафе', workers_needed: 1,
      pay_amount: 3200, pay_unit: 'shift', pay_per_hour: 400, pay_estimated: true, pay_total: 3200, pay_timing: 'в конце смены',
      startH: 4, stationId: '2.2',
      description: 'Заготовки, нарезка, мойка. Медкнижка желательна.',
      seenMin: 210,
    },
    {
      id: 49, employer_id: OLGA, category: 'driver', title: 'Водитель с «Газелью» · вывоз мебели', workers_needed: 1,
      pay_amount: 1200, pay_unit: 'hour', pay_per_hour: 1200, pay_estimated: false, pay_total: 3600, pay_timing: 'сразу',
      startH: 5, duration_hours: 3, stationId: '1.1',
      description: 'Нужна «Газель» с тентом, вывоз старой мебели на дачу в Подмосковье.',
      seenMin: 7,
    },
    {
      id: 50, employer_id: SERGEY, category: 'event', title: 'Монтаж сцены на концерт', workers_needed: 6,
      pay_amount: 700, pay_unit: 'hour', pay_per_hour: 700, pay_estimated: false, pay_total: 4200, pay_timing: 'после мероприятия',
      duration_hours: 6, stationId: '6.2', starts_on: day(3),
      description: 'Монтаж и демонтаж конструкций сцены. Опыт приветствуется, не обязателен.',
      seenMin: 300,
    },
    {
      id: 51, employer_id: SERGEY, category: 'loader', title: 'Грузчик · разгрузка фуры', workers_needed: 4,
      pay_amount: 450, pay_unit: 'hour', pay_per_hour: 450, pay_estimated: false, pay_total: 1800, pay_timing: 'сразу',
      startH: 1, duration_hours: 4, stationId: '7.2',
      description: 'Разгрузка 20-тонника с коробками (бытовая химия). Тяжёлого нет.',
      seenMin: 40,
    },
    {
      id: 52, employer_id: DMITRY, category: 'other', title: 'Расклейка объявлений по району', workers_needed: 1,
      pay_amount: 1500, pay_unit: 'task', pay_per_hour: null, pay_estimated: null, pay_total: 1500, pay_timing: null,
      starts_on: day(1), address: 'Район Марьино',
      description: 'Расклейка объявлений по подъездам, 40 домов. Объявления и клей дадим.',
      seenMin: 400,
    },
    {
      id: 53, employer_id: OLGA, category: 'courier', title: 'Курьер на своём авто · 1 день', workers_needed: 1,
      pay_amount: 4500, pay_unit: 'day', pay_per_hour: 563, pay_estimated: true, pay_total: 4500, pay_timing: 'сразу',
      startH: 18, stationId: '9.1',
      description: 'Доставка заказов интернет-магазина, 15–20 точек. Бензин компенсируем.',
      seenMin: 520,
    },
    // заявки самого пользователя мока (видны, когда он заказчик)
    {
      id: 60, employer_id: ME_ID, category: 'loader', title: 'Помочь с переездом квартиры', workers_needed: 2,
      pay_amount: 600, pay_unit: 'hour', pay_per_hour: 600, pay_estimated: false, pay_total: 2400, pay_timing: 'сразу',
      startH: 26, duration_hours: 4, stationId: '6.1', address: 'ул. Шаболовка, 10',
      description: 'Однушка, 5 этаж без лифта. Коробки уже собраны, нужно спустить и погрузить в машину.',
      seenMin: 55,
    },
    {
      id: 61, employer_id: ME_ID, category: 'cleaning', title: 'Уборка после праздника', workers_needed: 1, status: 'closed',
      pay_amount: 3000, pay_unit: 'task', pay_per_hour: 750, pay_estimated: false, pay_total: 3000, pay_timing: 'сразу',
      startH: -30, duration_hours: 4, stationId: '6.3',
      description: 'Квартира 60 м², посуда, полы.',
      seenMin: 60 * 30,
    },
  ];

  const jobs: JobRec[] = seeds.map(({ seenMin, startH, stationId, ...s }) => {
    const st = stationId ? metro.find((x) => x.id === stationId) ?? null : null;
    const starts = startH != null ? at(startH) : null;
    const jitter = (s.id % 7) * 0.0009;
    const expires = starts
      ? new Date(starts.getTime() + 3600e3)
      : s.starts_on
        ? new Date(`${s.starts_on}T23:59:59+03:00`)
        : new Date(now.getTime() + 3 * 864e5);
    return {
      status: 'open',
      description: null, workers_needed: null, pay_amount: null, pay_unit: null, pay_per_hour: null, pay_estimated: null,
      pay_total: null, pay_timing: null, duration_hours: null, address: null,
      ...s,
      starts_at: starts ? msk(starts) : null,
      starts_on: starts ? mskDay(starts) : s.starts_on ?? null,
      metro: st ? m(st.id) : null,
      lat: st ? st.lat + jitter : s.address ? 55.6497 + jitter : null,
      lng: st ? st.lng - jitter : s.address ? 37.7437 - jitter : null,
      created_at: ago(seenMin),
      expires_at: msk(expires),
    } as JobRec;
  });

  const responses: ResponseRec[] = [
    // отклики пользователя мока как исполнителя
    { id: 1, job_id: 42, worker_id: ME_ID, status: 'accepted', message: 'Могу через час, есть опыт переездов.', created_at: ago(10) },
    { id: 2, job_id: 44, worker_id: ME_ID, status: 'pending', message: null, created_at: ago(50) },
    { id: 3, job_id: 47, worker_id: ME_ID, status: 'rejected', message: 'Свободен весь день.', created_at: ago(170) },
    // отклики на заявки пользователя мока как заказчика
    { id: 4, job_id: 60, worker_id: 777, status: 'pending', message: 'Здравствуйте! Могу к назначенному времени, опыт переездов есть.', created_at: ago(40) },
    { id: 5, job_id: 60, worker_id: 780, status: 'pending', message: 'Будем вдвоём с братом, если нужно.', created_at: ago(25) },
    { id: 6, job_id: 60, worker_id: 779, status: 'withdrawn', message: null, created_at: ago(45) },
    { id: 7, job_id: 61, worker_id: 778, status: 'accepted', message: 'Свои средства есть.', created_at: ago(60 * 29) },
    // фон: чужие отклики на чужие заявки
    { id: 8, job_id: 42, worker_id: 777, status: 'accepted', message: null, created_at: ago(11) },
    { id: 9, job_id: 42, worker_id: 780, status: 'pending', message: null, created_at: ago(9) },
    { id: 10, job_id: 44, worker_id: 777, status: 'pending', message: null, created_at: ago(30) },
    { id: 11, job_id: 46, worker_id: 780, status: 'pending', message: null, created_at: ago(100) },
    { id: 12, job_id: 51, worker_id: 779, status: 'pending', message: null, created_at: ago(20) },
  ];

  const r = (id: number, author: number, target: number, rating: number, text: string | null, job: string, min: number, resp: number | null = null): ReviewRec => ({
    id, response_id: resp, author_id: author, target_id: target, rating, text, job_title: job, created_at: ago(min),
  });
  const reviews: ReviewRec[] = [
    r(1, 777, OLGA, 5, 'Всё чётко, оплатили сразу после работы.', 'Грузчики на склад', 60 * 24 * 3),
    r(2, 780, OLGA, 5, 'Адекватная, объяснила задачу заранее.', 'Переезд офиса', 60 * 24 * 9),
    r(3, 779, OLGA, 4, 'Задержались на час, но доплатили.', 'Разгрузка мебели', 60 * 24 * 20),
    r(4, 777, SERGEY, 4, 'Смена тяжёлая, но платят как обещали.', 'Ночная смена на складе', 60 * 24 * 5),
    r(5, 778, DMITRY, 5, null, 'Уборка после ремонта', 60 * 24 * 12),
    r(6, OLGA, 777, 5, 'Работал быстро и аккуратно.', 'Грузчики на склад', 60 * 24 * 3),
    r(7, SERGEY, 777, 4, null, 'Ночная смена на складе', 60 * 24 * 5),
    r(8, DMITRY, 778, 5, 'Квартира блестит, рекомендую.', 'Уборка после ремонта', 60 * 24 * 12),
    r(9, OLGA, 780, 5, 'Сильный и пунктуальный.', 'Переезд офиса', 60 * 24 * 9),
    r(10, ME_ID, 778, 5, 'Убрала всё за 3 часа.', 'Уборка после праздника', 60 * 24, 7),
    r(11, MARINA, ME_ID, 5, 'Пришёл вовремя, помог с разгрузкой.', 'Разгрузка продуктов', 60 * 24 * 7),
  ];

  return { jobs, responses, reviews };
}

export const initialSubscriptions: Subscription[] = [
  {
    id: 1, name: 'Грузчики · от 500 ₽/ч', categories: ['loader'], pay_min: 500, metro_ids: [],
    lat: null, lng: null, radius_km: null, today_only: false, enabled: true,
  },
  {
    id: 2, name: 'Курьеры, Склад · Таганская, Курская · сегодня', categories: ['courier', 'warehouse'], pay_min: null,
    metro_ids: ['7.1', '3.1'], lat: null, lng: null, radius_km: null, today_only: true, enabled: true,
  },
];
