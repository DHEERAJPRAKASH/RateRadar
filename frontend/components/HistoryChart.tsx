"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useHistory } from "@/lib/queries";
import { QueryState } from "./QueryState";

interface Props {
  provider: string;
  rateType: string;
  from: string;
  to: string;
}

export function HistoryChart({ provider, rateType, from, to }: Props) {
  const query = useHistory(
    provider || undefined,
    rateType || undefined,
    from || undefined,
    to || undefined,
  );

  const chartData = (query.data ?? [])
    .map((r) => ({
      date: r.effective_date,
      rate: parseFloat(r.rate_value),
    }))
    .reverse();

  const ready = Boolean(provider && rateType);

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-semibold mb-4">Rate History</h2>
      {!ready ? (
        <div className="py-12 text-center text-gray-400 text-sm">
          Select a provider and rate type to view history.
        </div>
      ) : (
        <QueryState
          isLoading={query.isLoading}
          isError={query.isError}
          error={query.error}
          onRetry={() => query.refetch()}
          loadingLabel="Loading history…"
        >
          {chartData.length === 0 ? (
            <div className="py-12 text-center text-gray-400 text-sm">
              No history in the selected window.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="rate"
                  stroke="#2563eb"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </QueryState>
      )}
    </div>
  );
}
