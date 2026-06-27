"use client";

import { CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";

import { useIngestionStatus } from "@/lib/queries";

export function IngestionProgress() {
  const { data, isLoading } = useIngestionStatus();

  if (isLoading || !data) {
    return null;
  }

  const { state, total, processed, quarantined, error } = data;
  // Older cached status payloads may predate these fields; default to 0.
  const inserted = data.inserted ?? 0;
  const updated = data.updated ?? 0;
  const output = data.output ?? inserted;

  // Nothing meaningful to show once the dataset is loaded and not re-running.
  if (state === "idle") {
    return null;
  }

  const pct =
    total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;

  const barColor =
    state === "error"
      ? "bg-red-500"
      : state === "complete"
        ? "bg-green-500"
        : "bg-blue-600";

  return (
    <div className="mb-6 bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-sm font-medium text-gray-800">
          {state === "running" && (
            <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
          )}
          {state === "complete" && (
            <CheckCircle2 className="w-4 h-4 text-green-600" />
          )}
          {state === "error" && (
            <AlertTriangle className="w-4 h-4 text-red-600" />
          )}
          <span>
            {state === "running" && "Seeding data…"}
            {state === "complete" && "Data loaded"}
            {state === "error" && "Seeding failed"}
          </span>
        </div>
        <span className="text-sm text-gray-500 tabular-nums">
          {processed.toLocaleString()} / {total.toLocaleString()} ({pct}%)
        </span>
      </div>

      <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className={`h-2 ${barColor} transition-all duration-500`}
          style={{ width: `${state === "complete" ? 100 : pct}%` }}
        />
      </div>

      <div className="flex flex-wrap gap-4 mt-2 text-xs text-gray-500">
        <span>Inserted: {inserted.toLocaleString()}</span>
        <span>Updated: {updated.toLocaleString()}</span>
        <span className="font-medium text-gray-700">
          Rows in table: {output.toLocaleString()}
        </span>
        <span>Quarantined: {quarantined.toLocaleString()}</span>
        {error && <span className="text-red-600">Error: {error}</span>}
      </div>
    </div>
  );
}
