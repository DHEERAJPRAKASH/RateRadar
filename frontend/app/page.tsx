"use client";

import { useEffect, useState } from "react";
import { RefreshCw, AlertCircle } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface Rate {
  id: number;
  provider_slug: string;
  provider_name: string;
  rate_type: string;
  rate_value: string;
  currency: string;
  effective_date: string;
  ingestion_ts: string;
}

export default function Dashboard() {
  const [rates, setRates] = useState<Rate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const fetchRates = async () => {
    try {
      setError(null);
      const response = await fetch(`${API_BASE_URL}/rates/latest/`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setRates(data);
      setLastRefresh(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch rates");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRates();
    const interval = setInterval(fetchRates, 60000); // 60s refresh
    return () => clearInterval(interval);
  }, []);

  // Prepare chart data (group by provider, latest rate)
  const chartData = rates.map((r) => ({
    provider: r.provider_name,
    rate: parseFloat(r.rate_value),
  }));

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-8">
      <div className="max-w-7xl mx-auto">
        <header className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">RateRadar</h1>
            <p className="text-gray-600 mt-1">Interest rate comparison dashboard</p>
          </div>
          <button
            onClick={fetchRates}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </header>

        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-600" />
            <p className="text-red-800">{error}</p>
          </div>
        )}

        {loading && !rates.length && (
          <div className="text-center py-12">
            <RefreshCw className="w-8 h-8 animate-spin mx-auto text-blue-600" />
            <p className="mt-4 text-gray-600">Loading rates...</p>
          </div>
        )}

        {rates.length > 0 && (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-xl font-semibold mb-4">Latest Rates</h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-2 px-3 font-medium text-gray-700">Provider</th>
                        <th className="text-left py-2 px-3 font-medium text-gray-700">Type</th>
                        <th className="text-right py-2 px-3 font-medium text-gray-700">Rate</th>
                        <th className="text-left py-2 px-3 font-medium text-gray-700">Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rates.map((rate) => (
                        <tr key={rate.id} className="border-b hover:bg-gray-50">
                          <td className="py-2 px-3">{rate.provider_name}</td>
                          <td className="py-2 px-3 text-gray-600">{rate.rate_type}</td>
                          <td className="py-2 px-3 text-right font-medium">{rate.rate_value}%</td>
                          <td className="py-2 px-3 text-gray-600">{rate.effective_date}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="bg-white rounded-lg shadow p-6">
                <h2 className="text-xl font-semibold mb-4">Rate Comparison</h2>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="provider" />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="rate" stroke="#2563eb" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {lastRefresh && (
              <p className="text-sm text-gray-500 text-center">
                Last updated: {lastRefresh.toLocaleTimeString()}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
