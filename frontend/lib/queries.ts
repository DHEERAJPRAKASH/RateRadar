// TanStack Query hooks wrapping the API client.

import { useQuery } from "@tanstack/react-query";

import {
  RateFilters,
  fetchBrowse,
  fetchHistory,
  fetchIngestionStatus,
  fetchLatest,
  fetchMeta,
  fetchQuarantined,
} from "./api";

const REFRESH_MS = 60_000; // 60s auto-refresh per the brief.

export function useIngestionStatus() {
  return useQuery({
    queryKey: ["ingestion-status"],
    queryFn: fetchIngestionStatus,
    // Poll quickly while a seed is running, back off once it settles.
    refetchInterval: (query) =>
      query.state.data?.state === "running" ? 2_000 : 15_000,
  });
}

export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: fetchMeta });
}

export function useLatest(rateType?: string) {
  return useQuery({
    queryKey: ["latest", rateType ?? "all"],
    queryFn: () => fetchLatest(rateType),
    refetchInterval: REFRESH_MS,
  });
}

export function useHistory(provider?: string, rateType?: string, from?: string, to?: string) {
  return useQuery({
    queryKey: ["history", provider, rateType, from, to],
    queryFn: () => fetchHistory(provider!, rateType!, from, to),
    enabled: Boolean(provider && rateType),
    refetchInterval: REFRESH_MS,
  });
}

export function useBrowse(filters: RateFilters, page: number) {
  return useQuery({
    queryKey: ["browse", filters, page],
    queryFn: () => fetchBrowse(filters, page),
    refetchInterval: REFRESH_MS,
  });
}

export function useQuarantined(page: number) {
  return useQuery({
    queryKey: ["quarantined", page],
    queryFn: () => fetchQuarantined(page),
    refetchInterval: REFRESH_MS,
  });
}
