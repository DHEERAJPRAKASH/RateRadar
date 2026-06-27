"use client";

import { useMeta } from "@/lib/queries";

export interface Filters {
  rateType: string;
  provider: string;
  from: string;
  to: string;
}

interface FilterBarProps {
  filters: Filters;
  onChange: (next: Filters) => void;
}

export function FilterBar({ filters, onChange }: FilterBarProps) {
  const { data: meta } = useMeta();

  const update = (patch: Partial<Filters>) =>
    onChange({ ...filters, ...patch });

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
        <label className="flex flex-col text-sm">
          <span className="text-gray-600 mb-1">Rate type</span>
          <select
            value={filters.rateType}
            onChange={(e) => update({ rateType: e.target.value })}
            className="border border-gray-300 rounded-md px-2 py-1.5 bg-white"
          >
            <option value="">All types</option>
            {meta?.rate_types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-gray-600 mb-1">Provider</span>
          <select
            value={filters.provider}
            onChange={(e) => update({ provider: e.target.value })}
            className="border border-gray-300 rounded-md px-2 py-1.5 bg-white"
          >
            <option value="">All providers</option>
            {meta?.providers.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-gray-600 mb-1">From</span>
          <input
            type="date"
            value={filters.from}
            onChange={(e) => update({ from: e.target.value })}
            className="border border-gray-300 rounded-md px-2 py-1.5"
          />
        </label>

        <label className="flex flex-col text-sm">
          <span className="text-gray-600 mb-1">To</span>
          <input
            type="date"
            value={filters.to}
            onChange={(e) => update({ to: e.target.value })}
            className="border border-gray-300 rounded-md px-2 py-1.5"
          />
        </label>

        <button
          onClick={() =>
            onChange({ rateType: "", provider: "", from: "", to: "" })
          }
          className="px-3 py-2 text-sm border border-gray-300 rounded-md hover:bg-gray-50"
        >
          Clear filters
        </button>
      </div>
    </div>
  );
}
