// Типизированный клиент API (docs/api.md). При VITE_MOCK=1 запросы обслуживает src/mock.
import { initData } from './telegram';
import type {
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
  ReportReason,
  ReviewIn,
  ReviewMine,
  Subscription,
  SubscriptionInput,
  UserProfile,
  WorkerCard,
  WorkersQuery,
} from './types';

export const MOCK = import.meta.env.VITE_MOCK === '1';
const BASE = '/api';

/** network: запрос не дошёл; timeout: сервер не ответил вовремя; http: ответ с ошибкой; parse: ответ не разобрать. */
export type ApiErrorKind = 'network' | 'timeout' | 'http' | 'parse';

export class ApiError extends Error {
  readonly status: number;
  readonly kind: ApiErrorKind;
  /** Запрос менял данные (не GET): после обрыва неизвестно, применился ли он. */
  readonly unsafe: boolean;
  constructor(status: number, message: string, kind: ApiErrorKind = 'http', unsafe = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.kind = kind;
    this.unsafe = unsafe;
  }
}

/** Аккаунт заблокирован модератором: App показывает экран блокировки вместо приложения. */
type BlockedListener = (detail: string) => void;
const blockedListeners = new Set<BlockedListener>();

export function onBlocked(cb: BlockedListener): () => void {
  blockedListeners.add(cb);
  return () => blockedListeners.delete(cb);
}

/** 403 «Аккаунт заблокирован…» отличается от 403 «не та роль» текстом detail. */
export function isBlockedError(status: number, detail: string): boolean {
  return status === 403 && /заблокирован/i.test(detail);
}

/** Сообщить о блокировке (из request и из мока). */
export function reportBlocked(detail: string): void {
  blockedListeners.forEach((cb) => cb(detail));
}

/**
 * Только для разработки: войти другим пользователем. Сервер учитывает заголовок лишь при DEV_AUTH=1.
 * ?devUser=2 в адресе важнее localStorage.gigoDevUser, так в двух вкладках можно держать двух пользователей.
 */
function devUser(): string | null {
  try {
    const q = new URLSearchParams(window.location.search).get('devUser');
    if (q && /^\d+$/.test(q)) return q;
  } catch {
    /* ignore */
  }
  try {
    const v = localStorage.getItem('gigoDevUser');
    if (v && /^\d+$/.test(v)) return v;
  } catch {
    /* приватный режим */
  }
  return null;
}

function headers(json: boolean): HeadersInit {
  const h: Record<string, string> = { Accept: 'application/json' };
  if (json) h['Content-Type'] = 'application/json';
  if (initData) h.Authorization = `tma ${initData}`;
  const dev = devUser();
  if (dev) h['X-Dev-User'] = dev;
  return h;
}

/** Сколько ждём ответа сервера. Чтение — меньше: его можно тихо повторить. */
const TIMEOUT_READ_MS = 15_000;
const TIMEOUT_WRITE_MS = 25_000;
/** Паузы перед повторами GET при обрыве связи или 502/503/504 (перезапуск сервера при обновлении). */
const RETRY_DELAYS_MS = [700, 2000];
const RETRY_STATUSES = new Set([502, 503, 504]);

function abortError(): DOMException {
  return new DOMException('Aborted', 'AbortError');
}

function sleep(ms: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const t = window.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      window.clearTimeout(t);
      reject(abortError());
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

/** Текст ошибки из тела ответа: FastAPI отдаёт detail строкой, списком {msg} (валидация) или объектом. */
export function detailOf(body: unknown): string {
  if (!body || typeof body !== 'object') return '';
  const b = body as Record<string, unknown>;
  const d = b.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    const first = d[0] as Record<string, unknown> | undefined;
    if (first && typeof first.msg === 'string') return first.msg;
  }
  if (d && typeof d === 'object') {
    const o = d as Record<string, unknown>;
    if (typeof o.message === 'string') return o.message;
    if (typeof o.detail === 'string') return o.detail;
  }
  if (typeof b.message === 'string') return b.message;
  return '';
}

/** Одна попытка: fetch с тайм-аутом, разбор ответа. */
async function attempt<T>(path: string, init: RequestInit, unsafe: boolean): Promise<T> {
  const outer = init.signal;
  if (outer?.aborted) throw abortError();
  const ctrl = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(
    () => {
      timedOut = true;
      ctrl.abort();
    },
    unsafe ? TIMEOUT_WRITE_MS : TIMEOUT_READ_MS,
  );
  const onOuterAbort = () => ctrl.abort();
  outer?.addEventListener('abort', onOuterAbort, { once: true });
  try {
    let res: Response;
    try {
      res = await fetch(BASE + path, { ...init, signal: ctrl.signal, headers: headers(init.body != null) });
    } catch {
      if (outer?.aborted) throw abortError();
      if (timedOut) throw new ApiError(0, 'Сервер не ответил вовремя', 'timeout', unsafe);
      throw new ApiError(0, 'Нет связи с сервером', 'network', unsafe);
    }
    if (!res.ok) {
      let detail = '';
      try {
        detail = detailOf(await res.json());
      } catch {
        /* тело не JSON: например, страница прокси при перезапуске сервера */
      }
      if (isBlockedError(res.status, detail)) reportBlocked(detail);
      throw new ApiError(res.status, detail || `Ошибка ${res.status}`, 'http', unsafe);
    }
    if (res.status === 204) return undefined as T;
    try {
      const text = await res.text();
      return (text ? JSON.parse(text) : undefined) as T;
    } catch {
      if (outer?.aborted) throw abortError();
      if (timedOut) throw new ApiError(0, 'Сервер не ответил вовремя', 'timeout', unsafe);
      throw new ApiError(res.status, 'Непонятный ответ сервера', 'parse', unsafe);
    }
  } finally {
    window.clearTimeout(timer);
    outer?.removeEventListener('abort', onOuterAbort);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const unsafe = method !== 'GET';
  for (let i = 0; ; i++) {
    try {
      return await attempt<T>(path, init, unsafe);
    } catch (e) {
      // Менять данные повторно не пытаемся: запрос мог дойти, и повтор создал бы дубль.
      const retriable =
        !unsafe &&
        e instanceof ApiError &&
        (e.kind === 'network' || e.kind === 'timeout' || RETRY_STATUSES.has(e.status)) &&
        i < RETRY_DELAYS_MS.length;
      if (!retriable) throw e;
      await sleep(RETRY_DELAYS_MS[i], init.signal);
    }
  }
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

/** Параметры GET /api/jobs: массивы повторяются (category=a&category=b). */
export function jobsSearchParams(q: JobsQuery): URLSearchParams {
  const p = new URLSearchParams();
  q.category?.forEach((c) => p.append('category', c));
  if (q.pay_min != null) p.set('pay_min', String(q.pay_min));
  q.metro?.forEach((m) => p.append('metro', m));
  if (q.today) p.set('today', 'true');
  if (q.lat != null && q.lng != null) {
    p.set('lat', q.lat.toFixed(5));
    p.set('lng', q.lng.toFixed(5));
    if (q.radius_km != null) p.set('radius_km', String(q.radius_km));
  }
  if (q.sort && q.sort !== 'fresh') p.set('sort', q.sort);
  if (q.with_location) p.set('with_location', 'true');
  if (q.q?.trim()) p.set('q', q.q.trim());
  if (q.limit != null) p.set('limit', String(q.limit));
  if (q.offset) p.set('offset', String(q.offset));
  return p;
}

const mock = async () => (await import('./mock/mockApi')).mockApi;

export const api = {
  async meta(): Promise<Meta> {
    if (MOCK) return (await mock()).meta();
    return request<Meta>('/meta');
  },

  async me(): Promise<Me> {
    if (MOCK) return (await mock()).me();
    return request<Me>('/me');
  },

  async updateMe(body: MePatch): Promise<Me> {
    if (MOCK) return (await mock()).updateMe(body);
    return request<Me>('/me', json('PATCH', body));
  },

  async jobs(q: JobsQuery, signal?: AbortSignal): Promise<JobsPage> {
    if (MOCK) return (await mock()).jobs(q);
    const qs = jobsSearchParams(q).toString();
    return request<JobsPage>(`/jobs${qs ? `?${qs}` : ''}`, { signal });
  },

  async job(id: number): Promise<Job> {
    if (MOCK) return (await mock()).job(id);
    return request<Job>(`/jobs/${id}`);
  },

  async createJob(body: JobIn): Promise<Job> {
    if (MOCK) return (await mock()).createJob(body);
    return request<Job>('/jobs', json('POST', body));
  },

  async updateJob(id: number, body: JobIn): Promise<Job> {
    if (MOCK) return (await mock()).updateJob(id, body);
    return request<Job>(`/jobs/${id}`, json('PUT', body));
  },

  async setSaved(id: number, saved: boolean): Promise<void> {
    if (MOCK) return (await mock()).setSaved(id, saved);
    await request<void>(`/jobs/${id}/save`, { method: saved ? 'PUT' : 'DELETE' });
  },

  async savedJobs(): Promise<Job[]> {
    if (MOCK) return (await mock()).savedJobs();
    return (await request<{ items: Job[] }>('/my/saved')).items;
  },

  async setJobStatus(id: number, status: JobStatus): Promise<Job> {
    if (MOCK) return (await mock()).setJobStatus(id, status);
    return request<Job>(`/jobs/${id}`, json('PATCH', { status }));
  },

  async myJobs(): Promise<Job[]> {
    if (MOCK) return (await mock()).myJobs();
    return (await request<{ items: Job[] }>('/my/jobs')).items;
  },

  async respond(jobId: number, message: string | null): Promise<JobResponse> {
    if (MOCK) return (await mock()).respond(jobId, message);
    return request<JobResponse>(`/jobs/${jobId}/responses`, json('POST', message ? { message } : {}));
  },

  async setResponseStatus(id: number, status: Exclude<ResponseStatus, 'pending'>): Promise<JobResponse> {
    if (MOCK) return (await mock()).setResponseStatus(id, status);
    return request<JobResponse>(`/responses/${id}`, json('PATCH', { status }));
  },

  async myResponses(): Promise<MyResponse[]> {
    if (MOCK) return (await mock()).myResponses();
    return (await request<{ items: MyResponse[] }>('/my/responses')).items;
  },

  async review(body: ReviewIn): Promise<ReviewMine> {
    if (MOCK) return (await mock()).review(body);
    return request<ReviewMine>('/reviews', json('POST', body));
  },

  async reportJob(id: number, reason: ReportReason, text: string | null): Promise<void> {
    if (MOCK) return (await mock()).reportJob(id, reason, text);
    await request<void>(`/jobs/${id}/report`, json('POST', text ? { reason, text } : { reason }));
  },

  async user(id: number): Promise<UserProfile> {
    if (MOCK) return (await mock()).user(id);
    return request<UserProfile>(`/users/${id}`);
  },

  async workers(q: WorkersQuery, signal?: AbortSignal): Promise<{ total: number; items: WorkerCard[] }> {
    if (MOCK) return (await mock()).workers(q);
    const p = new URLSearchParams();
    if (q.category) p.set('category', q.category);
    if (q.q?.trim()) p.set('q', q.q.trim());
    if (q.limit != null) p.set('limit', String(q.limit));
    if (q.offset) p.set('offset', String(q.offset));
    const qs = p.toString();
    return request(`/workers${qs ? `?${qs}` : ''}`, { signal });
  },

  async invite(jobId: number, workerId: number): Promise<void> {
    if (MOCK) return (await mock()).invite(jobId, workerId);
    await request<void>(`/jobs/${jobId}/invites`, json('POST', { worker_id: workerId }));
  },

  async subscriptions(): Promise<Subscription[]> {
    if (MOCK) return (await mock()).subscriptions();
    return request<Subscription[]>('/subscriptions');
  },

  async createSubscription(body: SubscriptionInput): Promise<Subscription> {
    if (MOCK) return (await mock()).createSubscription(body);
    return request<Subscription>('/subscriptions', json('POST', body));
  },

  async deleteSubscription(id: number): Promise<void> {
    if (MOCK) return (await mock()).deleteSubscription(id);
    await request<void>(`/subscriptions/${id}`, { method: 'DELETE' });
  },
};

const CYRILLIC = /[а-яё]/i;

/** Сообщение сервера можно показать человеку: русский текст, а не «Not Found» или «Ошибка 418». */
function humanDetail(msg: string): string {
  return msg && CYRILLIC.test(msg) && !/^Ошибка \d+$/.test(msg) ? msg : '';
}

/** Понятный человеку текст для любой ошибки: показываем его в тостах и на экранах ошибок. */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const human = humanDetail(e.message);
    if (e.kind === 'network' || e.kind === 'timeout') {
      const offline = typeof navigator !== 'undefined' && navigator.onLine === false;
      const base = offline
        ? 'Нет интернета. Проверьте подключение.'
        : e.kind === 'timeout'
          ? 'Сервер долго не отвечает. Проверьте интернет и попробуйте ещё раз.'
          : 'Нет связи с сервером. Проверьте интернет.';
      return e.unsafe ? `${base} Если действие не применилось, повторите его.` : base;
    }
    if (e.kind === 'parse') return 'Сервер ответил с ошибкой. Попробуйте ещё раз чуть позже.';
    if (e.status === 401) return 'Не удалось войти. Закройте приложение и откройте его снова из бота в Telegram.';
    if (e.status === 429) return human || 'Слишком много действий подряд. Попробуйте чуть позже.';
    if (e.status >= 500) return 'Сервер временно недоступен. Попробуйте ещё раз через минуту.';
    if (human) return human;
    if (e.status === 403) return 'Это действие вам недоступно.';
    if (e.status === 404) return 'Не нашли: возможно, это уже удалили.';
    if (e.status === 409) return 'Не получилось: данные уже изменились. Обновите экран.';
    if (e.status === 413) return 'Слишком большой запрос. Сократите текст.';
    if (e.status === 400 || e.status === 422) return 'Проверьте введённые данные.';
    return 'Что-то пошло не так. Попробуйте ещё раз.';
  }
  if (typeof navigator !== 'undefined' && navigator.onLine === false) return 'Нет интернета. Проверьте подключение.';
  return 'Что-то пошло не так. Попробуйте ещё раз.';
}

export function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === 'AbortError';
}
