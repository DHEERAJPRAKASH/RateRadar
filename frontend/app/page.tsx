"use client";

import { useState } from "react";

import { RateFilters } from "@/lib/api";
import { AllRatesTable } from "@/components/AllRatesTable";
import { FilterBar, Filters } from "@/components/FilterBar";
import { HistoryChart } from "@/components/HistoryChart";
import { IngestionProgress } from "@/components/IngestionProgress";
import { LatestRatesTable } from "@/components/LatestRatesTable";
import { QuarantineTable } from "@/components/QuarantineTable";

const EMPTY_FILTERS: Filters = {
  rateType: "",
  provider: "",
  from: "",
  to: "",
};

export default function Dashboard() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);

  const apiFilters: RateFilters = {
    rate_type: filters.rateType || undefined,
    provider: filters.provider || undefined,
    from: filters.from || undefined,
    to: filters.to || undefined,
  };

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-8">
      <div className="max-w-7xl mx-auto">
        <header className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">RateRadar</h1>
          <p className="text-gray-600 mt-1">
            Interest rate comparison dashboard
          </p>
        </header>

        <IngestionProgress />

        <FilterBar filters={filters} onChange={setFilters} />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <LatestRatesTable rateType={filters.rateType} />
          <HistoryChart
            provider={filters.provider}
            rateType={filters.rateType}
            from={filters.from}
            to={filters.to}
          />
        </div>

        <AllRatesTable filters={apiFilters} />

        <QuarantineTable />
      </div>
    </div>
  );
}
