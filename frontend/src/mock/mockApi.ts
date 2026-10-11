// Имитация бэкенда для VITE_MOCK=1: всё как в docs/api.md, состояние живёт в памяти до перезагрузки.
// Пользователь мока один (ME_ID); его роль меняется через PATCH /api/me, как в настоящем приложении.
import { ApiError } from '../api';
import { haversineKm } from '../geo';
import { mskDay } from '../format';
import type {
  Contact,
  Job,
  JobIn,
  JobResponse,
  JobStatus,
  JobsPage,
  JobsQuery,
  Me,
  MePatch,
  Meta,
  MyResponse,
  ResponseStatus,
  ReviewIn,
  ReviewMine,
  Subscription,
  SubscriptionInput,
  UserProfile,
  UserStub,
} from '../types';
import { ME_ID, buildWorld, initialSubscriptions, m, meta, metro, msk, users, type JobRec, type ResponseRec, type UserRec } from './fixture';

const delay = <T>(v: T, ms = 250) => new Promise<T>((r) => setTimeout(() => r(structuredClone(v)), ms));
const fail = (status: number, detail: string) => Promise.reject(new ApiError(status, detail));

const world = buildWorld();
let subs: Subscription[] = initialSubscriptions.map((s) => ({ ...s }));
let seq = 1000;
const now = () => Date.now();

// ——— вычисляемые поля ———

const user = (id: number): UserRec => users.find((u) => u.id === id)!;
const me = () => user(ME_ID);

function ratingOf(id: number): { rating: number | null; reviews_count: number } {
  const rs = world.reviews.filter((r) => r.target_id === id);
  if (!rs.length) return { rating: null, reviews_count: 0 };
  return { rating: Math.round((rs.reduce((s, r) => s + r.rating, 0) / rs.length) * 10) / 10, reviews_count: rs.length };
}

function stub(id: number, withAbout = false): UserStub {
  const u = user(id);
  return { id: u.id, first_name: u.first_name, ...(withAbout ? { about: u.about } : {}), ...ratingOf(id) };
}

function contactOf(id: number): Contact {
  const u = user(id);
  return { first_name: u.first_name, username: u.username, url: u.username ? `https://t.me/${u.username}` : `tg://user?id=${u.id}` };
}

const jobRec = (id: number) => world.jobs.find((j) => j.id === id);
const expired = (j: JobRec) => new Date(j.expires_at).getTime() < now();

function serializeResponse(r: ResponseRec): JobResponse {
  const job = jobRec(r.job_id)!;
  const viewerIsWorker = r.worker_id === ME_ID;
  const mine = world.reviews.find((x) => x.response_id === r.id && x.author_id === ME_ID);
  return {
    id: r.id,
    job_id: r.job_id,
    status: r.status,
    message: r.message,
    created_at: r.created_at,
    worker: stub(r.worker_id, true),
    contact: r.status === 'accepted' ? contactOf(viewerIsWorker ? job.employer_id : r.worker_id) : null,
    my_review: mine ? { rating: mine.rating, text: mine.text } : null,
  };
}

function serializeJob(j: JobRec, here: { lat: number; lng: number } | null = null, full = false): Job {
  const rs = world.responses.filter((r) => r.job_id === j.id);
  const mineResp = rs.find((r) => r.worker_id === ME_ID);
  const isMine = j.employer_id === ME_ID;
  const { employer_id, ...rest } = j;
  const job: Job = {
    ...rest,
    status: j.status,
    distance_km: here && j.lat != null && j.lng != null ? Math.round(haversineKm(here, { lat: j.lat, lng: j.lng }) * 10) / 10 : null,
    employer: stub(employer_id),
    responses_count: rs.filter((r) => r.status !== 'withdrawn').length,
    accepted_count: rs.filter((r) => r.status === 'accepted').length,
    is_mine: isMine,
    my_response: mineResp ? serializeResponse(mineResp) : null,
  };
  if (isMine && full) job.responses = rs.sort((a, b) => b.created_at.localeCompare(a.created_at)).map(serializeResponse);
  return job;
}

function meOut(): Me {
  const u = me();
  return { id: u.id, username: u.username, first_name: u.first_name, role: u.role, about: u.about, ...ratingOf(u.id) };
}

function needRole(role: 'worker' | 'employer'): Promise<never> | null {
  if (me().role !== role) return fail(403, role === 'worker' ? 'Это действие для исполнителей' : 'Это действие для заказчиков');
  return null;
}

/** Через несколько секунд на новую заявку откликаются, чтобы было что принять. */
function simulateResponses(jobId: number) {
  const plan: [number, number, string | null][] = [
    [777, 4000, 'Здравствуйте! Свободен, могу подъехать к началу.'],
    [778, 9000, null],
  ];
  for (const [worker, ms, message] of plan) {
    setTimeout(() => {
      const j = jobRec(jobId);
      if (!j || j.status !== 'open') return;
      world.responses.push({ id: seq++, job_id: jobId, worker_id: worker, status: 'pending', message, created_at: msk(new Date()) });
    }, ms);
  }
}

const FRAUD = /закладк|кладмен|оформлени[а-яё]* карт|дроп|предоплат[а-яё]* за обучени|обнал/i;

function perHour(amount: number, unit: JobIn['pay_unit'], hours: number | null): { v: number | null; est: boolean } {
  if (unit === 'hour') return { v: amount, est: false };
  if (hours) return { v: Math.round(amount / hours), est: false };
  if (unit === 'shift' || unit === 'day') return { v: Math.round(amount / 8), est: true };
  return { v: null, est: false };
}

export const mockApi = {
  meta(): Promise<Meta> {
    return delay(meta, 150);
  },

  me(): Promise<Me> {
    return delay(meOut(), 150);
  },

  updateMe(body: MePatch): Promise<Me> {
    const u = me();
    if (body.role) u.role = body.role;
    if (body.about != null) u.about = body.about.trim() || null;
    return delay(meOut());
  },

  jobs(q: JobsQuery): Promise<JobsPage> {
    const today = mskDay(new Date());
    const here = q.lat != null && q.lng != null ? { lat: q.lat, lng: q.lng } : null;
    let list: Job[] = world.jobs
      .filter((j) => j.status === 'open' && !expired(j))
      .filter((j) => !q.category?.length || q.category.includes(j.category))
      .filter((j) => q.pay_min == null || (j.pay_per_hour != null && j.pay_per_hour >= q.pay_min))
      .filter((j) => !q.metro?.length || (j.metro != null && q.metro.includes(j.metro.id)))
      .filter((j) => !q.today || j.starts_on === today)
      .filter((j) => !q.with_location || (j.lat != null && j.lng != null))
      .map((j) => serializeJob(j, here))
      .filter((j) => q.radius_km == null || (j.distance_km != null && j.distance_km <= q.radius_km));

    if (q.sort === 'distance') list.sort((a, b) => (a.distance_km ?? 1e9) - (b.distance_km ?? 1e9));
    else if (q.sort === 'pay') list.sort((a, b) => (b.pay_per_hour ?? -1) - (a.pay_per_hour ?? -1));
    else list.sort((a, b) => b.created_at.localeCompare(a.created_at));

    const offset = q.offset ?? 0;
    const limit = Math.min(q.limit ?? 30, 500);
    const total = list.length;
    list = list.slice(offset, offset + limit);
    return delay({ total, items: list });
  },

  job(id: number): Promise<Job> {
    const j = jobRec(id);
    if (!j) return fail(404, 'Заявка не найдена');
    const visible = (j.status === 'open' && !expired(j)) || j.employer_id === ME_ID || world.responses.some((r) => r.job_id === id && r.worker_id === ME_ID);
    if (!visible) return fail(404, 'Заявка не найдена');
    return delay(serializeJob(j, null, true), 150);
  },

  createJob(b: JobIn): Promise<Job> {
    const denied = needRole('employer');
    if (denied) return denied;
    if (!b.category || !b.title?.trim() || !(b.pay_amount > 0) || !b.pay_unit) return fail(422, 'Заполните категорию, название и оплату');
    if (!b.metro_id && !b.address && (b.lat == null || b.lng == null)) return fail(422, 'Укажите метро или адрес');
    if (FRAUD.test(`${b.title} ${b.description ?? ''}`))
      return fail(422, 'Заявка похожа на мошенничество (закладки, оформление карт, предоплата). Такие мы не публикуем.');
    const openCount = world.jobs.filter((j) => j.employer_id === ME_ID && j.status === 'open' && !expired(j)).length;
    if (openCount >= 20) return fail(409, 'Не больше 20 открытых заявок. Закройте старые.');

    const st = b.metro_id ? metro.find((x) => x.id === b.metro_id) : undefined;
    const startsAt = b.starts_on && b.start_time ? new Date(`${b.starts_on}T${b.start_time}:00+03:00`) : null;
    const expires = startsAt
      ? new Date(startsAt.getTime() + 3600e3)
      : b.starts_on
        ? new Date(`${b.starts_on}T23:59:59+03:00`)
        : new Date(now() + 3 * 864e5);
    const hours = b.duration_hours ?? null;
    const ph = perHour(b.pay_amount, b.pay_unit, hours);
    const workers = b.workers_needed ?? 1;
    const jitter = () => (Math.random() - 0.5) * 0.01;
    const rec: JobRec = {
      id: seq++,
      employer_id: ME_ID,
      status: 'open',
      category: b.category,
      title: b.title.trim(),
      description: b.description ?? null,
      workers_needed: workers,
      pay_amount: b.pay_amount,
      pay_unit: b.pay_unit,
      pay_per_hour: ph.v,
      pay_estimated: ph.est,
      pay_total: b.pay_unit === 'hour' ? (hours ? Math.round(b.pay_amount * hours) : null) : b.pay_amount,
      pay_timing: b.pay_timing ?? null,
      starts_on: b.starts_on ?? null,
      starts_at: startsAt ? msk(startsAt) : null,
      duration_hours: hours,
      metro: st ? m(st.id) : null,
      address: b.address ?? null,
      lat: b.lat ?? (st ? st.lat + jitter() : meta.city.lat + jitter() * 5),
      lng: b.lng ?? (st ? st.lng + jitter() : meta.city.lng + jitter() * 5),
      created_at: msk(new Date()),
      expires_at: msk(expires),
    };
    world.jobs.unshift(rec);
    simulateResponses(rec.id);
    return delay(serializeJob(rec, null, true), 400);
  },

  setJobStatus(id: number, status: JobStatus): Promise<Job> {
    const j = jobRec(id);
    if (!j) return fail(404, 'Заявка не найдена');
    if (j.employer_id !== ME_ID) return fail(403, 'Это не ваша заявка');
    if (status === 'open' && expired(j)) return fail(409, 'Срок заявки прошёл. Создайте новую.');
    j.status = status;
    return delay(serializeJob(j, null, true));
  },

  myJobs(): Promise<Job[]> {
    const denied = needRole('employer');
    if (denied) return denied;
    const list = world.jobs
      .filter((j) => j.employer_id === ME_ID)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map((j) => ({
        ...serializeJob(j),
        pending_count: world.responses.filter((r) => r.job_id === j.id && r.status === 'pending').length,
      }));
    return delay(list);
  },

  respond(jobId: number, message: string | null): Promise<JobResponse> {
    const denied = needRole('worker');
    if (denied) return denied;
    const j = jobRec(jobId);
    if (!j) return fail(404, 'Заявка не найдена');
    if (j.employer_id === ME_ID) return fail(409, 'Нельзя откликнуться на свою заявку');
    if (j.status !== 'open' || expired(j)) return fail(409, 'Набор по заявке закрыт');
    if (message && message.length > 500) return fail(422, 'Сообщение длиннее 500 знаков');
    let r = world.responses.find((x) => x.job_id === jobId && x.worker_id === ME_ID);
    if (r && r.status !== 'withdrawn') return fail(409, 'Вы уже откликнулись');
    if (r) {
      r.status = 'pending';
      r.message = message;
      r.created_at = msk(new Date());
    } else {
      r = { id: seq++, job_id: jobId, worker_id: ME_ID, status: 'pending', message, created_at: msk(new Date()) };
      world.responses.push(r);
    }
    // для демо: через 6 секунд заказчик принимает отклик
    const rr = r;
    setTimeout(() => {
      if (rr.status === 'pending') rr.status = 'accepted';
    }, 6000);
    return delay(serializeResponse(r), 400);
  },

  setResponseStatus(id: number, status: Exclude<ResponseStatus, 'pending'>): Promise<JobResponse> {
    const r = world.responses.find((x) => x.id === id);
    if (!r) return fail(404, 'Отклик не найден');
    const j = jobRec(r.job_id)!;
    if (status === 'withdrawn') {
      if (r.worker_id !== ME_ID) return fail(403, 'Это не ваш отклик');
      if (r.status !== 'pending' && r.status !== 'accepted') return fail(409, 'Этот отклик уже нельзя отозвать');
    } else {
      if (j.employer_id !== ME_ID) return fail(403, 'Это не ваша заявка');
      if (r.status === 'withdrawn') return fail(409, 'Исполнитель отозвал отклик');
    }
    r.status = status;
    return delay(serializeResponse(r));
  },

  myResponses(): Promise<MyResponse[]> {
    const denied = needRole('worker');
    if (denied) return denied;
    const list = world.responses
      .filter((r) => r.worker_id === ME_ID)
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .map((r) => ({ ...serializeResponse(r), job: serializeJob(jobRec(r.job_id)!) }));
    return delay(list);
  },

  review(b: ReviewIn): Promise<ReviewMine> {
    const r = world.responses.find((x) => x.id === b.response_id);
    if (!r) return fail(404, 'Отклик не найден');
    const j = jobRec(r.job_id)!;
    if (r.status !== 'accepted') return fail(409, 'Отзыв можно оставить только по принятому отклику');
    let target: number;
    if (r.worker_id === ME_ID) target = j.employer_id;
    else if (j.employer_id === ME_ID) target = r.worker_id;
    else return fail(403, 'Вы не участвовали в этой работе');
    if (!(b.rating >= 1 && b.rating <= 5)) return fail(422, 'Оценка от 1 до 5');
    const text = b.text?.trim() || null;
    const old = world.reviews.find((x) => x.response_id === r.id && x.author_id === ME_ID);
    if (old) {
      old.rating = b.rating;
      old.text = text;
    } else {
      world.reviews.push({
        id: seq++, response_id: r.id, author_id: ME_ID, target_id: target, rating: b.rating, text, job_title: j.title, created_at: msk(new Date()),
      });
    }
    return delay({ rating: b.rating, text });
  },

  user(id: number): Promise<UserProfile> {
    const u = users.find((x) => x.id === id);
    if (!u) return fail(404, 'Пользователь не найден');
    const jobsCount =
      u.role === 'employer'
        ? world.jobs.filter((j) => j.employer_id === id).length
        : u.done_before + world.responses.filter((r) => r.worker_id === id && r.status === 'accepted').length;
    return delay({
      id: u.id,
      first_name: u.first_name,
      role: u.role,
      about: u.about,
      ...ratingOf(id),
      jobs_count: jobsCount,
      reviews: world.reviews
        .filter((r) => r.target_id === id)
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
        .map((r) => ({ rating: r.rating, text: r.text, author: { id: r.author_id, first_name: user(r.author_id).first_name }, job_title: r.job_title, created_at: r.created_at })),
    });
  },

  subscriptions(): Promise<Subscription[]> {
    return delay(subs);
  },

  createSubscription(body: SubscriptionInput): Promise<Subscription> {
    if (subs.length >= 10) return fail(409, 'Не больше 10 подписок');
    const s: Subscription = {
      id: seq++,
      name: body.name,
      categories: body.categories ?? [],
      pay_min: body.pay_min ?? null,
      metro_ids: body.metro_ids ?? [],
      lat: body.lat ?? null,
      lng: body.lng ?? null,
      radius_km: body.radius_km ?? null,
      today_only: body.today_only ?? false,
      enabled: true,
    };
    subs = [...subs, s];
    return delay(s);
  },

  deleteSubscription(id: number): Promise<void> {
    subs = subs.filter((s) => s.id !== id);
    return delay(undefined);
  },
};
