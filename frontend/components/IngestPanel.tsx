"use client";

import { useEffect, useState } from "react";
import { LogIn, LogOut, Plus, Loader2, ShieldCheck } from "lucide-react";

import {
  IngestRecord,
  clearStoredAuth,
  loadStoredAuth,
  saveStoredAuth,
} from "@/lib/api";
import { useIngest, useLogin } from "@/lib/queries";
import { IngestModal } from "./IngestModal";

// Demo convenience: the dashboard auto-logs in with the default user the backend
// provisions on boot, then exchanges it for a bearer token at runtime (the token
// itself is never shipped in the bundle).
const DEFAULT_USERNAME =
  process.env.NEXT_PUBLIC_DEFAULT_USERNAME || "ingestor";
const DEFAULT_PASSWORD =
  process.env.NEXT_PUBLIC_DEFAULT_PASSWORD || "ingest-dev-password";

export function IngestPanel() {
  const [token, setToken] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  const loginMutation = useLogin();
  const ingestMutation = useIngest(token);

  // Restore bearer token from localStorage after client hydration.
  useEffect(() => {
    const stored = loadStoredAuth();
    if (stored) {
      setToken(stored.token);
      setUsername(stored.username);
    }
    setAuthReady(true);
  }, []);

  const handleLogin = () => {
    loginMutation.mutate(
      { username: DEFAULT_USERNAME, password: DEFAULT_PASSWORD },
      {
        onSuccess: (data) => {
          setToken(data.token);
          setUsername(data.username);
          saveStoredAuth({ token: data.token, username: data.username });
        },
      },
    );
  };

  const handleLogout = () => {
    clearStoredAuth();
    setToken(null);
    setUsername(null);
    setModalOpen(false);
  };

  const openModal = () => {
    ingestMutation.reset();
    setModalOpen(true);
  };

  const handleSubmit = (record: IngestRecord) => {
    ingestMutation.mutate(record);
  };

  return (
    <div className="mb-6 bg-white rounded-lg shadow p-4 flex items-center justify-between">
      <div className="text-sm">
        <p className="font-medium text-gray-800">Add rate data</p>
        <p className="text-gray-500">
          {token
            ? `Authenticated as ${username} — create new records via the secured ingest endpoint.`
            : "Authenticate to create new records via the secured ingest endpoint."}
        </p>
      </div>

      {token ? (
        <div className="flex items-center gap-2">
          <button
            onClick={openModal}
            className="flex items-center gap-2 bg-blue-600 text-white rounded-md px-4 py-2 text-sm hover:bg-blue-700"
          >
            <Plus className="w-4 h-4" /> Create record
          </button>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 border border-gray-300 text-gray-700 rounded-md px-4 py-2 text-sm hover:bg-gray-50"
          >
            <LogOut className="w-4 h-4" /> Logout
          </button>
        </div>
      ) : authReady ? (
        <div className="flex flex-col items-end">
          <button
            onClick={handleLogin}
            disabled={loginMutation.isPending}
            className="flex items-center gap-2 bg-gray-900 text-white rounded-md px-4 py-2 text-sm hover:bg-gray-800 disabled:opacity-50"
          >
            {loginMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <LogIn className="w-4 h-4" />
            )}
            Login
          </button>
          {loginMutation.isError && (
            <span className="text-red-600 text-xs mt-1">
              {(loginMutation.error as Error).message}
            </span>
          )}
        </div>
      ) : (
        <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
      )}

      {token && (
        <span className="hidden sm:flex items-center gap-1 text-xs text-green-700 ml-3">
          <ShieldCheck className="w-4 h-4" /> Bearer token active
        </span>
      )}

      {modalOpen && (
        <IngestModal
          onClose={() => setModalOpen(false)}
          onSubmit={handleSubmit}
          isSubmitting={ingestMutation.isPending}
          submitError={
            ingestMutation.isError
              ? (ingestMutation.error as Error).message
              : null
          }
          result={ingestMutation.data ?? null}
        />
      )}
    </div>
  );
}
