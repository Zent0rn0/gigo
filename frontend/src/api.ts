// Типизированный клиент API (docs/api.md). При VITE_MOCK=1 запросы обслуживает src/mock.
import { initData } from './telegram';
import type { Job, JobsPage, JobsQuery, Meta, Subscription, SubscriptionInput } from './types';

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

function headers(json: boolean): HeadersInit {
  const h: Record<string, string> = { Accept: 'application/json' };
  if (json) h['Content-Type'] = 'application/json';
  if (initData) h.Authorization = `tma ${initData}`;
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
    } catch {
      /* тело не JSON */
    }
    throw new ApiError(res.status, detail || `Ошибка ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

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

const mock = () => import('./mock/mockApi');

export const api = {
  async meta(): Promise<Meta> {
    if (MOCK) return (await mock()).mockApi.meta();
    return request<Meta>('/meta');
  },

  async jobs(q: JobsQuery, signal?: AbortSignal): Promise<JobsPage> {
    if (MOCK) return (await mock()).mockApi.jobs(q);
    const qs = jobsSearchParams(q).toString();
    return request<JobsPage>(`/jobs${qs ? `?${qs}` : ''}`, { signal });
  },

  async job(id: number): Promise<Job> {
    if (MOCK) return (await mock()).mockApi.job(id);
    return request<Job>(`/jobs/${id}`);
  },

  async subscriptions(): Promise<Subscription[]> {
    if (MOCK) return (await mock()).mockApi.subscriptions();
    return request<Subscription[]>('/subscriptions');
  },

  async createSubscription(body: SubscriptionInput): Promise<Subscription> {
    if (MOCK) return (await mock()).mockApi.createSubscription(body);
    return request<Subscription>('/subscriptions', { method: 'POST', body: JSON.stringify(body) });
  },

  async deleteSubscription(id: number): Promise<void> {
    if (MOCK) return (await mock()).mockApi.deleteSubscription(id);
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
