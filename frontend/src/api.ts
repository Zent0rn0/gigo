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
  ReviewIn,
  ReviewMine,
  Subscription,
  SubscriptionInput,
  UserProfile,
} from './types';

export const MOCK = import.meta.env.VITE_MOCK === '1';
const BASE = '/api';

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, { ...init, headers: headers(init.body != null) });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new ApiError(0, 'Нет связи с сервером');
  }
  if (!res.ok) {
    let detail = '';
    try {
      const body = await res.json();
      if (body && typeof body.detail === 'string') detail = body.detail;
      // FastAPI-валидация: detail — массив {msg, loc}
      else if (body && Array.isArray(body.detail) && body.detail[0]?.msg) detail = String(body.detail[0].msg);
    } catch {
      /* тело не JSON */
    }
    throw new ApiError(res.status, detail || `Ошибка ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
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

  async user(id: number): Promise<UserProfile> {
    if (MOCK) return (await mock()).user(id);
    return request<UserProfile>(`/users/${id}`);
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

export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return 'Не удалось войти. Откройте приложение из бота в Telegram.';
    if (e.status === 0) return 'Нет связи с сервером. Проверьте интернет.';
    if (e.status >= 500) return 'Сервер временно недоступен. Попробуйте ещё раз.';
    return e.message;
  }
  return 'Что-то пошло не так. Попробуйте ещё раз.';
}

export function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === 'AbortError';
}
