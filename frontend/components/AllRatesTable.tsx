"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { RateFilters } from "@/lib/api";
import { useBrowse } from "@/lib/queries";
import { QueryState } from "./QueryState";

interface Props {
  filters: RateFilters;
}

const PAGE_SIZE = 50;

export function AllRatesTable({ filters }: Props) {
  const [page, setPage] = useState(1);
  const [pageInput, setPageInput] = useState("");
  const query = useBrowse(filters, page);

  const rows = query.data?.results ?? [];
  const count = query.data?.count ?? 0;
  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-8">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold">All Rates</h2>
        <span className="text-sm text-gray-500">
          {count.toLocaleString()} rows
        </span>
      </div>

      <QueryState
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        onRetry={() => query.refetch()}
        loadingLabel="Loading rates…"
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2 px-3 font-medium text-gray-700">
                  Provider
                </th>
                <th className="text-left py-2 px-3 font-medium text-gray-700">
                  Type
                </th>
                <th className="text-right py-2 px-3 font-medium text-gray-700">
                  Rate
                </th>
                <th className="text-left py-2 px-3 font-medium text-gray-700">
                  Currency
                </th>
                <th className="text-left py-2 px-3 font-medium text-gray-700">
                  Effective date
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((rate) => (
                <tr key={rate.id} className="border-b hover:bg-gray-50">
                  <td className="py-2 px-3">{rate.provider_name}</td>
                  <td className="py-2 px-3 text-gray-600">{rate.rate_type}</td>
                  <td className="py-2 px-3 text-right font-medium">
                    {rate.rate_value}%
                  </td>
                  <td className="py-2 px-3 text-gray-600">{rate.currency}</td>
                  <td className="py-2 px-3 text-gray-600">
                    {rate.effective_date}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-gray-400">
                    No rates match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-end gap-3 mt-4 text-sm">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="flex items-center gap-1 px-3 py-1.5 border border-gray-300 rounded-md disabled:opacity-40 hover:bg-gray-50"
          >
            <ChevronLeft className="w-4 h-4" /> Prev
          </button>
          <span className="text-gray-600">
            Page {page} of {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={1}
              max={totalPages}
              value={pageInput}
              onChange={(e) => setPageInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const pageNum = parseInt(pageInput, 10);
                  if (pageNum >= 1 && pageNum <= totalPages) {
                    setPage(pageNum);
                    setPageInput("");
                  }
                }
              }}
              placeholder="Go to"
              className="w-20 px-2 py-1.5 border border-gray-300 rounded-md text-center"
            />
            <button
              onClick={() => {
                const pageNum = parseInt(pageInput, 10);
                if (pageNum >= 1 && pageNum <= totalPages) {
                  setPage(pageNum);
                  setPageInput("");
                }
              }}
              disabled={
                !pageInput ||
                parseInt(pageInput, 10) < 1 ||
                parseInt(pageInput, 10) > totalPages
              }
              className="px-3 py-1.5 border border-gray-300 rounded-md disabled:opacity-40 hover:bg-gray-50"
            >
              Go
            </button>
          </div>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            className="flex items-center gap-1 px-3 py-1.5 border border-gray-300 rounded-md disabled:opacity-40 hover:bg-gray-50"
          >
            Next <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </QueryState>
    </div>
  );
}
