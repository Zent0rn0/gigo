// Типы по контракту docs/api.md

export type CategoryId =
  | 'loader'
  | 'courier'
  | 'warehouse'
  | 'cleaning'
  | 'construction'
  | 'promo'
  | 'kitchen'
  | 'driver'
  | 'event'
  | 'other';

export type PayUnit = 'hour' | 'shift' | 'day' | 'task' | 'month';

export type JobSort = 'fresh' | 'distance' | 'pay';

export interface Category {
  id: string;
  label: string;
  emoji: string;
}

export interface MetroStation {
  id: string;
  name: string;
  line: string;
  color: string | null;
  lat: number;
  lng: number;
}

export interface City {
  id: string;
  name: string;
  lat: number;
  lng: number;
}

export interface Meta {
  categories: Category[];
  metro: MetroStation[];
  city: City;
}

export interface JobMetro {
  id: string;
  name: string;
  line: string | null;
  color: string | null;
}

export interface JobPost {
  link: string;
  chat: string | null;
  sent_at: string | null;
}

export interface Job {
  id: number;
  category: string;
  title: string;
  workers_needed: number | null;
  pay_amount: number | null;
  pay_unit: PayUnit | null;
  pay_per_hour: number | null;
  pay_estimated: boolean | null;
  pay_total: number | null;
  pay_timing: string | null;
  starts_on: string | null; // YYYY-MM-DD
  starts_at: string | null; // ISO 8601
  duration_hours: number | null;
  metro: JobMetro | null;
  address: string | null;
  lat: number | null;
  lng: number | null;
  distance_km: number | null;
  description: string | null;
  phone: string | null; // цифры без «+», например 79001234567
  posts: JobPost[];
  first_seen_at: string;
  expires_at: string;
}

export interface JobsPage {
  total: number;
  items: Job[];
}

export interface JobsQuery {
  category?: string[];
  pay_min?: number | null;
  metro?: string[];
  today?: boolean;
  lat?: number | null;
  lng?: number | null;
  radius_km?: number | null;
  sort?: JobSort;
  with_location?: boolean;
  limit?: number;
  offset?: number;
}

export interface Subscription {
  id: number;
  name: string;
  categories: string[];
  pay_min: number | null;
  metro_ids: string[];
  lat: number | null;
  lng: number | null;
  radius_km: number | null;
  today_only: boolean;
  enabled: boolean;
}

/** Тело POST /api/subscriptions: обязательно только name. */
export type SubscriptionInput = { name: string } & Partial<Omit<Subscription, 'id' | 'enabled' | 'name'>>;

export interface GeoPoint {
  lat: number;
  lng: number;
}
