// Имитация бэкенда для VITE_MOCK=1: фильтры, сортировка и пагинация как в docs/api.md.
import { ApiError } from '../api';
import { haversineKm } from '../geo';
import { mskDay } from '../format';
import type { Job, JobsPage, JobsQuery, Meta, Subscription, SubscriptionInput } from '../types';
import { buildJobs, initialSubscriptions, meta } from './fixture';

const delay = <T>(v: T, ms = 250) => new Promise<T>((r) => setTimeout(() => r(v), ms));

const jobs = buildJobs();
let subs: Subscription[] = initialSubscriptions.map((s) => ({ ...s }));
let nextSubId = 100;

export const mockApi = {
  meta(): Promise<Meta> {
    return delay(meta, 150);
  },

  jobs(q: JobsQuery): Promise<JobsPage> {
    const today = mskDay(new Date());
    const here = q.lat != null && q.lng != null ? { lat: q.lat, lng: q.lng } : null;
    let list: Job[] = jobs
      .filter((j) => !q.category?.length || q.category.includes(j.category))
      .filter((j) => q.pay_min == null || (j.pay_per_hour != null && j.pay_per_hour >= q.pay_min))
      .filter((j) => !q.metro?.length || (j.metro != null && q.metro.includes(j.metro.id)))
      .filter((j) => !q.today || j.starts_on === today)
      .filter((j) => !q.with_location || (j.lat != null && j.lng != null))
      .map((j) => ({
        ...j,
        distance_km: here && j.lat != null && j.lng != null ? Math.round(haversineKm(here, { lat: j.lat, lng: j.lng }) * 10) / 10 : null,
      }))
      .filter((j) => q.radius_km == null || (j.distance_km != null && j.distance_km <= q.radius_km));

    if (q.sort === 'distance') list.sort((a, b) => (a.distance_km ?? 1e9) - (b.distance_km ?? 1e9));
    else if (q.sort === 'pay') list.sort((a, b) => (b.pay_per_hour ?? -1) - (a.pay_per_hour ?? -1));
    else list.sort((a, b) => b.first_seen_at.localeCompare(a.first_seen_at));

    const offset = q.offset ?? 0;
    const limit = Math.min(q.limit ?? 30, 500);
    const total = list.length;
    list = list.slice(offset, offset + limit);
    return delay({ total, items: list });
  },

  job(id: number): Promise<Job> {
    const j = jobs.find((x) => x.id === id);
    if (!j) return Promise.reject(new ApiError(404, 'Заказ не найден'));
    return delay(j, 150);
  },

  subscriptions(): Promise<Subscription[]> {
    return delay(subs.map((s) => ({ ...s })));
  },

  createSubscription(body: SubscriptionInput): Promise<Subscription> {
    if (subs.length >= 10) return Promise.reject(new ApiError(409, 'Не больше 10 подписок'));
    const s: Subscription = {
      id: nextSubId++,
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
    return delay({ ...s });
  },

  deleteSubscription(id: number): Promise<void> {
    subs = subs.filter((s) => s.id !== id);
    return delay(undefined);
  },
};
