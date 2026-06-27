"use client";

import { useState } from "react";
import { X, Loader2, CheckCircle2 } from "lucide-react";
import { z } from "zod";

import { IngestRecord, IngestResult } from "@/lib/api";
import { useMeta } from "@/lib/queries";

const schema = z.object({
  provider: z.string().trim().min(1, "Provider is required"),
  rate_type: z.string().trim().min(1, "Rate type is required"),
  rate_value: z.coerce
    .number({ invalid_type_error: "Rate must be a number" })
    .min(0, "Rate must be ≥ 0")
    .max(100, "Rate must be ≤ 100"),
  currency: z.enum(["USD", "EUR", "GBP"]),
  effective_date: z.string().min(1, "Effective date is required"),
  source_url: z
    .string()
    .trim()
    .url("Must be a valid URL")
    .or(z.literal(""))
    .optional(),
});

type FieldErrors = Partial<Record<keyof IngestRecord, string>>;

interface Props {
  onClose: () => void;
  onSubmit: (record: IngestRecord) => void;
  isSubmitting: boolean;
  submitError: string | null;
  result: IngestResult | null;
}

const EMPTY_FORM = {
  provider: "",
  rate_type: "",
  rate_value: "",
  currency: "USD",
  effective_date: new Date().toISOString().slice(0, 10),
  source_url: "",
};

export function IngestModal({
  onClose,
  onSubmit,
  isSubmitting,
  submitError,
  result,
}: Props) {
  const { data: meta } = useMeta();
  const [form, setForm] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState<FieldErrors>({});

  const update = (patch: Partial<typeof form>) =>
    setForm((prev) => ({ ...prev, ...patch }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const parsed = schema.safeParse(form);
    if (!parsed.success) {
      const next: FieldErrors = {};
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] as keyof IngestRecord;
        if (!next[key]) next[key] = issue.message;
      }
      setErrors(next);
      return;
    }
    setErrors({});
    onSubmit({
      ...parsed.data,
      source_url: parsed.data.source_url || undefined,
      ingestion_ts: new Date().toISOString(),
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 sm:items-center">
      <div className="my-auto w-full max-w-md max-h-[90vh] overflow-y-auto bg-white rounded-lg shadow-xl">
        <div className="flex items-center justify-between border-b px-5 py-3">
          <h2 className="text-lg font-semibold">Create rate record</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {result ? (
          <div className="px-5 py-6 text-sm">
            <div className="flex items-center gap-2 text-green-700 font-medium mb-3">
              <CheckCircle2 className="w-5 h-5" /> Record ingested
            </div>
            <ul className="text-gray-600 space-y-1">
              <li>Inserted: {result.inserted}</li>
              <li>Updated: {result.updated}</li>
              <li>Providers created: {result.providers_created}</li>
              <li>
                Quarantined:{" "}
                {Object.keys(result.quarantined).length
                  ? JSON.stringify(result.quarantined)
                  : 0}
              </li>
            </ul>
            <button
              onClick={onClose}
              className="mt-5 w-full bg-gray-900 text-white rounded-md py-2 hover:bg-gray-800"
            >
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="px-5 py-4 space-y-3 text-sm">
            <Field label="Provider" error={errors.provider}>
              <input
                className="input"
                placeholder="e.g. HSBC"
                value={form.provider}
                onChange={(e) => update({ provider: e.target.value })}
              />
            </Field>

            <Field label="Rate type" error={errors.rate_type}>
              <select
                className="input"
                value={form.rate_type}
                onChange={(e) => update({ rate_type: e.target.value })}
              >
                <option value="">Select rate type</option>
                {meta?.rate_types.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Rate value (%)" error={errors.rate_value}>
                <input
                  className="input"
                  type="number"
                  step="0.0001"
                  placeholder="4.5"
                  value={form.rate_value}
                  onChange={(e) => update({ rate_value: e.target.value })}
                />
              </Field>
              <Field label="Currency" error={errors.currency}>
                <select
                  className="input"
                  value={form.currency}
                  onChange={(e) => update({ currency: e.target.value })}
                >
                  <option value="USD">USD</option>
                  <option value="EUR">EUR</option>
                  <option value="GBP">GBP</option>
                </select>
              </Field>
            </div>

            <Field label="Effective date" error={errors.effective_date}>
              <input
                className="input"
                type="date"
                value={form.effective_date}
                onChange={(e) => update({ effective_date: e.target.value })}
              />
            </Field>

            <Field label="Source URL (optional)" error={errors.source_url}>
              <input
                className="input"
                placeholder="https://example.com/rates"
                value={form.source_url}
                onChange={(e) => update({ source_url: e.target.value })}
              />
            </Field>

            {submitError && (
              <p className="text-red-600 text-xs">{submitError}</p>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white rounded-md py-2 hover:bg-blue-700 disabled:opacity-50"
            >
              {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
              {isSubmitting ? "Submitting…" : "Submit"}
            </button>
          </form>
        )}
      </div>

      <style jsx>{`
        :global(.input) {
          width: 100%;
          border: 1px solid #d1d5db;
          border-radius: 0.375rem;
          padding: 0.375rem 0.5rem;
          background: white;
        }
      `}</style>
    </div>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col">
      <span className="text-gray-600 mb-1">{label}</span>
      {children}
      {error && <span className="text-red-600 text-xs mt-1">{error}</span>}
    </label>
  );
}
