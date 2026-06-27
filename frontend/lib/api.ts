// Typed API client for the RateRadar backend.

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface Rate {
  id: number;
  provider_slug: string;
  provider_name: string;
  rate_type: string;
  rate_value: string;
  currency: string;
  effective_date: string;
  ingestion_ts: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface QuarantineRow {
  id: number;
  reason: string;
  payload: Record<string, unknown>;
  source_url: string;
  created_at: string;
}

export interface RateMeta {
  rate_types: string[];
  providers: { slug: string; name: string }[];
}

export type IngestionState = "idle" | "running" | "complete" | "error";

export interface IngestionStatus {
  state: IngestionState;
  total: number;
  processed: number;
  inserted: number;
  updated: number;
  output: number;
  quarantined: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export interface RateFilters {
  rate_type?: string;
  provider?: string;
  from?: string;
  to?: string;
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`Request to ${path} failed: HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      qs.set(key, String(value));
    }
  }
  const str = qs.toString();
  return str ? `?${str}` : "";
}

export function fetchLatest(rateType?: string): Promise<Rate[]> {
  return getJSON<Rate[]>(`/rates/latest/${buildQuery({ rate_type: rateType })}`);
}

export function fetchHistory(
  provider: string,
  rateType: string,
  from?: string,
  to?: string,
): Promise<Rate[]> {
  return getJSON<Rate[]>(
    `/rates/history/${buildQuery({ provider, rate_type: rateType, from, to })}`,
  );
}

export function fetchBrowse(
  filters: RateFilters,
  page: number,
): Promise<Paginated<Rate>> {
  return getJSON<Paginated<Rate>>(
    `/rates/browse/${buildQuery({
      rate_type: filters.rate_type,
      provider: filters.provider,
      from: filters.from,
      to: filters.to,
      page,
    })}`,
  );
}

export function fetchQuarantined(page: number): Promise<Paginated<QuarantineRow>> {
  return getJSON<Paginated<QuarantineRow>>(
    `/rates/quarantined/${buildQuery({ page })}`,
  );
}

export function fetchMeta(): Promise<RateMeta> {
  return getJSON<RateMeta>("/rates/meta/");
}

export function fetchIngestionStatus(): Promise<IngestionStatus> {
  return getJSON<IngestionStatus>("/ingestion/status/");
}
