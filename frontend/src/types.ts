// Типы по контракту docs/api.md

export type Role = 'worker' | 'employer';

export type PayUnit = 'hour' | 'shift' | 'day' | 'task';

export type JobSort = 'fresh' | 'distance' | 'pay';

/** Сервер присылает open | closed | cancelled; на всякий случай терпим и другое значение. */
export type JobStatus = 'open' | 'closed' | 'cancelled';

export type ResponseStatus = 'pending' | 'accepted' | 'rejected' | 'withdrawn';

export interface Category {
  id: string;
  label: string;
  emoji: string;
}

export interface PayUnitOption {
  id: PayUnit;
  label: string;
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
  pay_units: PayUnitOption[];
  metro: MetroStation[];
  city: City;
}

export interface Me {
  id: number;
  username: string | null;
  first_name: string;
  role: Role | null;
  about: string | null;
  rating: number | null;
  reviews_count: number;
}

export interface MePatch {
  role?: Role;
  about?: string;
}

/** Короткая карточка второй стороны (заказчик в Job, исполнитель в Response). */
export interface UserStub {
  id: number;
  first_name: string;
  about?: string | null;
  rating: number | null;
  reviews_count: number;
}

export interface Contact {
  first_name: string;
  username: string | null;
  url: string;
}

export interface ReviewMine {
  rating: number;
  text: string | null;
}

export interface JobResponse {
  id: number;
  job_id: number;
  status: ResponseStatus;
  message: string | null;
  created_at: string;
  worker: UserStub;
  contact: Contact | null;
  my_review: ReviewMine | null;
}

/** Элемент GET /api/my/responses. */
export interface MyResponse extends JobResponse {
  job: Job;
}

export interface JobMetro {
  id: string;
  name: string;
  line: string | null;
  color: string | null;
}

export interface Job {
  id: number;
  status: JobStatus;
  category: string;
  title: string;
  description: string | null;
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
  employer: UserStub;
  responses_count: number;
  accepted_count: number;
  is_mine: boolean;
  my_response: JobResponse | null;
  created_at: string;
  expires_at: string;
  /** Только автору в GET /api/jobs/{id}. */
  responses?: JobResponse[];
  /** Только в GET /api/my/jobs. */
  pending_count?: number;
}

/** Тело POST /api/jobs. */
export interface JobIn {
  category: string;
  title: string;
  description?: string | null;
  workers_needed?: number | null;
  pay_amount: number;
  pay_unit: PayUnit;
  pay_timing?: string | null;
  starts_on?: string | null;
  start_time?: string | null; // HH:MM
  duration_hours?: number | null;
  metro_id?: string | null;
  address?: string | null;
  lat?: number | null;
  lng?: number | null;
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

export interface PublicReview {
  rating: number;
  text: string | null;
  author: { id: number; first_name: string };
  job_title: string | null;
  created_at: string;
}

export interface UserProfile {
  id: number;
  first_name: string;
  role: Role | null;
  about: string | null;
  rating: number | null;
  reviews_count: number;
  jobs_count: number;
  reviews: PublicReview[];
}

export interface ReviewIn {
  response_id: number;
  rating: number;
  text?: string | null;
}

/** Причина жалобы на заявку: POST /api/jobs/{id}/report. */
export type ReportReason = 'scam' | 'spam' | 'rude' | 'other';

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
