// Тестовые данные для VITE_MOCK=1. Время считается от текущего момента, чтобы «сегодня»/«13 мин назад» были живыми.
import type { Category, Job, JobMetro, Meta, MetroStation, Subscription } from '../types';
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

export const meta: Meta = {
  categories,
  metro,
  city: { id: 'moscow', name: 'Москва', lat: 55.7558, lng: 37.6176 },
};

function m(id: string): JobMetro {
  const s = metro.find((x) => x.id === id)!;
  return { id: s.id, name: s.name, line: s.line, color: s.color };
}

/** ISO со смещением +03:00, как отдаёт бэкенд. */
function msk(d: Date): string {
  return new Date(d.getTime() + 3 * 3600e3).toISOString().slice(0, 19) + '+03:00';
}

export function buildJobs(now = new Date()): Job[] {
  const hourStart = new Date(Math.ceil(now.getTime() / 3600e3) * 3600e3);
  const at = (h: number) => new Date(hourStart.getTime() + h * 3600e3);
  const ago = (min: number) => new Date(now.getTime() - min * 60e3);
  const day = (d: number) => mskDay(new Date(now.getTime() + d * 864e5));

  type Seed = Partial<Job> & Pick<Job, 'id' | 'category' | 'title'> & { seenMin: number; startH?: number; stationId?: string };

  const seeds: Seed[] = [
    {
      id: 42, category: 'loader', title: 'Грузчики ×2 · переезд офиса', workers_needed: 2,
      pay_amount: 500, pay_unit: 'hour', pay_per_hour: 500, pay_estimated: false, pay_total: 2000, pay_timing: 'сразу',
      startH: 1, duration_hours: 4, stationId: '7.1', address: 'Большая Коммунистическая ул., 15',
      description: 'Переезд офиса, нужны 2 человека на ~4 часа. Мебель и коробки, есть лифт. Оплата сразу на карту.',
      phone: '79001234567', seenMin: 13,
      posts: [
        { link: 'https://t.me/gruzchiki_msk/123', chat: 'Грузчики Москва', sent_at: '' },
        { link: 'https://t.me/podrabotka_moskva/5567', chat: 'Подработка Москва', sent_at: '' },
      ],
    },
    {
      id: 43, category: 'courier', title: 'Пеший курьер · документы по центру', workers_needed: 1,
      pay_amount: 3000, pay_unit: 'day', pay_per_hour: 375, pay_estimated: true, pay_total: 3000, pay_timing: 'в конце дня',
      startH: 2, duration_hours: 8, stationId: '2.1',
      description: 'Разнос документов по офисам в пределах Садового кольца. Проездной компенсируем.',
      phone: '79157654321', seenMin: 27,
    },
    {
      id: 44, category: 'warehouse', title: 'Комплектовщик на склад · ночная смена', workers_needed: 5,
      pay_amount: 3500, pay_unit: 'shift', pay_per_hour: 292, pay_estimated: true, pay_total: 3500, pay_timing: 'еженедельно',
      startH: 30, duration_hours: 12, stationId: '7.3', address: 'Рязанский пр-т, 2, склад №4',
      description: 'Сборка заказов на складе маркетплейса. Смена 20:00–08:00, питание за счёт компании. Паспорт РФ/ЕАЭС.',
      phone: '74951112233', seenMin: 64,
    },
    {
      id: 45, category: 'cleaning', title: 'Уборка квартиры после ремонта', workers_needed: 1,
      pay_amount: 4000, pay_unit: 'task', pay_per_hour: 667, pay_estimated: true, pay_total: 4000, pay_timing: 'сразу',
      startH: 3, duration_hours: 6, stationId: '10.1',
      description: '2-комнатная квартира, строительная пыль, мытьё окон. Инвентарь и химия есть.',
      phone: '79264445566', seenMin: 95,
    },
    {
      id: 46, category: 'construction', title: 'Разнорабочие на стройку частного дома', workers_needed: 3,
      pay_amount: 600, pay_unit: 'hour', pay_per_hour: 600, pay_estimated: false, pay_total: 4800, pay_timing: 'сразу',
      startH: 20, duration_hours: 8, stationId: '3.3',
      description: 'Подсобные работы: разгрузка блоков, уборка мусора. Перчатки выдаём. Сбор у метро, довезём.',
      phone: '79035550011', seenMin: 140,
    },
    {
      id: 47, category: 'promo', title: 'Промоутер у метро · листовки', workers_needed: 2,
      pay_amount: 400, pay_unit: 'hour', pay_per_hour: 400, pay_estimated: false, pay_total: 1200, pay_timing: 'сразу',
      startH: 22, duration_hours: 3, stationId: '3.1',
      description: 'Раздача листовок у выхода из метро. 3 часа, форма не нужна.',
      phone: null, seenMin: 180,
      posts: [{ link: 'https://t.me/rabota_promo_msk/8812', chat: 'Промоутеры Москвы', sent_at: '' }],
    },
    {
      id: 48, category: 'kitchen', title: 'Помощник повара в кафе', workers_needed: 1,
      pay_amount: 3200, pay_unit: 'shift', pay_per_hour: 320, pay_estimated: true, pay_total: null, pay_timing: 'в конце смены',
      startH: 4, duration_hours: 10, stationId: '2.2',
      description: 'Заготовки, нарезка, мойка. Медкнижка желательна.',
      phone: '79991234500', seenMin: 210,
    },
    {
      id: 49, category: 'driver', title: 'Водитель с личной «Газелью» · вывоз мебели', workers_needed: 1,
      pay_amount: 1200, pay_unit: 'hour', pay_per_hour: 1200, pay_estimated: false, pay_total: 3600, pay_timing: 'сразу',
      startH: 5, duration_hours: 3, stationId: '1.1',
      description: 'Нужна «Газель» с тентом, вывоз старой мебели на дачу в Подмосковье.',
      phone: '79167778899', seenMin: 7,
    },
    {
      id: 50, category: 'event', title: 'Монтаж сцены на концерт', workers_needed: 6,
      pay_amount: 700, pay_unit: 'hour', pay_per_hour: 700, pay_estimated: false, pay_total: 4200, pay_timing: 'после мероприятия',
      duration_hours: 6, stationId: '6.2', starts_on: day(3),
      description: 'Монтаж и демонтаж конструкций сцены. Опыт приветствуется, не обязателен.',
      phone: '79250001122', seenMin: 300,
    },
    {
      id: 51, category: 'loader', title: 'Грузчик · разгрузка фуры', workers_needed: 4,
      pay_amount: 450, pay_unit: 'hour', pay_per_hour: 450, pay_estimated: false, pay_total: 1800, pay_timing: 'сразу',
      startH: 1, duration_hours: 4, stationId: '7.2',
      description: 'Разгрузка 20-тонника с коробками (бытовая химия). Тяжёлого нет.',
      phone: null, seenMin: 40,
      posts: [
        { link: 'https://t.me/gruzchiki_msk/130', chat: 'Грузчики Москва', sent_at: '' },
        { link: 'https://t.me/podrabotka_moskva/5590', chat: 'Подработка Москва', sent_at: '' },
        { link: 'https://t.me/rabota_segodnya_msk/2201', chat: 'Работа сегодня', sent_at: '' },
      ],
    },
    {
      id: 52, category: 'other', title: 'Расклейка объявлений по району', workers_needed: null,
      pay_amount: null, pay_unit: null, pay_per_hour: null, pay_estimated: null, pay_total: null, pay_timing: null,
      duration_hours: null, starts_on: day(1),
      description: 'Расклейка объявлений по подъездам, район уточняйте в личке.',
      phone: null, seenMin: 400,
    },
    {
      id: 53, category: 'courier', title: 'Курьер на своём авто · 1 день', workers_needed: 1,
      pay_amount: 4500, pay_unit: 'day', pay_per_hour: 450, pay_estimated: true, pay_total: 4500, pay_timing: 'сразу',
      startH: 18, duration_hours: 10, stationId: '9.1',
      description: 'Доставка заказов интернет-магазина, 15–20 точек. Бензин компенсируем.',
      phone: '79031230000', seenMin: 520,
    },
  ];

  return seeds.map(({ seenMin, startH, stationId, ...s }) => {
    const seen = ago(seenMin);
    const st = stationId ? metro.find((x) => x.id === stationId) ?? null : null;
    const starts = startH != null ? at(startH) : null;
    const jitter = (s.id % 7) * 0.0009;
    const posts = (s.posts ?? [{ link: `https://t.me/podrabotka_moskva/${5000 + s.id}`, chat: 'Подработка Москва', sent_at: '' }]).map(
      (p, i) => ({ ...p, sent_at: msk(new Date(seen.getTime() + i * 4 * 60e3)) }),
    );
    const expires = starts ? new Date(starts.getTime() + 3600e3) : new Date(now.getTime() + 36 * 3600e3);
    const job: Job = {
      workers_needed: null, pay_amount: null, pay_unit: null, pay_per_hour: null, pay_estimated: null, pay_total: null,
      pay_timing: null, duration_hours: null, address: null, description: null, phone: null,
      ...s,
      starts_at: starts ? msk(starts) : null,
      starts_on: starts ? mskDay(starts) : s.starts_on ?? null,
      metro: st ? m(st.id) : null,
      lat: st ? st.lat + jitter : null,
      lng: st ? st.lng - jitter : null,
      distance_km: null,
      posts,
      first_seen_at: msk(seen),
      expires_at: msk(expires),
    };
    return job;
  });
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
