// TanStack Query hooks wrapping the API client.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  IngestRecord,
  RateFilters,
  fetchBrowse,
  fetchHistory,
  fetchIngestionStatus,
  fetchLatest,
  fetchMeta,
  fetchQuarantined,
  ingestRate,
  login,
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

export function useLogin() {
  return useMutation({
    mutationFn: (creds: { username: string; password: string }) =>
      login(creds.username, creds.password),
  });
}

export function useIngest(token: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (record: IngestRecord) => {
      if (!token) {
        throw new Error("Not authenticated — log in first.");
      }
      return ingestRate(token, record);
    },
    onSuccess: () => {
      // New record is now in the DB — refresh the data-driven views.
      queryClient.invalidateQueries({ queryKey: ["browse"] });
      queryClient.invalidateQueries({ queryKey: ["latest"] });
      queryClient.invalidateQueries({ queryKey: ["meta"] });
      queryClient.invalidateQueries({ queryKey: ["quarantined"] });
    },
  });
}
