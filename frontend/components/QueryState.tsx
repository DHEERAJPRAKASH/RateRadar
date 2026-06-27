"use client";

import { AlertCircle, Loader2 } from "lucide-react";

interface QueryStateProps {
  isLoading: boolean;
  isError: boolean;
  error?: unknown;
  onRetry?: () => void;
  loadingLabel?: string;
  children: React.ReactNode;
}

// Renders explicit loading and error states for a query, falling back to the
// children once data is available. Used by every data panel so each fetch has
// a visible loading + error state (not just a spinner).
export function QueryState({
  isLoading,
  isError,
  error,
  onRetry,
  loadingLabel = "Loading…",
  children,
}: QueryStateProps) {
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 justify-center text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span>{loadingLabel}</span>
      </div>
    );
  }

  if (isError) {
    const message =
      error instanceof Error ? error.message : "Something went wrong.";
    return (
      <div className="py-6 px-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-red-800">
          <AlertCircle className="w-5 h-5" />
          <span className="text-sm">{message}</span>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="text-sm px-3 py-1.5 bg-red-600 text-white rounded-md hover:bg-red-700"
          >
            Retry
          </button>
        )}
      </div>
    );
  }

  return <>{children}</>;
}
