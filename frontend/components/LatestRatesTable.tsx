"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";

import { Rate } from "@/lib/api";
import { useLatest } from "@/lib/queries";
import { QueryState } from "./QueryState";

type SortKey = "rate_value" | "effective_date";

interface Props {
  rateType: string;
}

export function LatestRatesTable({ rateType }: Props) {
  const query = useLatest(rateType || undefined);
  const [sortKey, setSortKey] = useState<SortKey>("rate_value");
  const [asc, setAsc] = useState(false);

  const rows = useMemo(() => {
    const data: Rate[] = query.data ?? [];
    const sorted = [...data].sort((a, b) => {
      if (sortKey === "rate_value") {
        return parseFloat(a.rate_value) - parseFloat(b.rate_value);
      }
      return a.effective_date.localeCompare(b.effective_date);
    });
    return asc ? sorted : sorted.reverse();
  }, [query.data, sortKey, asc]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setAsc((v) => !v);
    } else {
      setSortKey(key);
      setAsc(false);
    }
  };

  const SortIcon = ({ active }: { active: boolean }) =>
    !active ? null : asc ? (
      <ArrowUp className="w-3 h-3 inline" />
    ) : (
      <ArrowDown className="w-3 h-3 inline" />
    );

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-xl font-semibold mb-4">Latest Rates</h2>
      <QueryState
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        onRetry={() => query.refetch()}
        loadingLabel="Loading latest rates…"
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
                <th
                  className="text-right py-2 px-3 font-medium text-gray-700 cursor-pointer select-none"
                  onClick={() => toggleSort("rate_value")}
                >
                  Rate <SortIcon active={sortKey === "rate_value"} />
                </th>
                <th
                  className="text-left py-2 px-3 font-medium text-gray-700 cursor-pointer select-none"
                  onClick={() => toggleSort("effective_date")}
                >
                  Date <SortIcon active={sortKey === "effective_date"} />
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
                  <td className="py-2 px-3 text-gray-600">
                    {rate.effective_date}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-6 text-center text-gray-400">
                    No rates yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </QueryState>
    </div>
  );
}
