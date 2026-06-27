#!/usr/bin/env bash
# Web entrypoint: apply migrations, then exec the given command (gunicorn).
# The worker/beat services override this with their own commands and skip migrate.
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
  echo '{"level":"INFO","logger":"entrypoint","message":"applying migrations"}'
  python manage.py migrate --noinput
fi

# Seed the full dataset asynchronously on boot. The page loads immediately and
# a progress bar polls /ingestion/status while the worker streams the ~1M rows.
# Idempotent: the task skips if rates already exist, so re-`up` is fast.
#
# (Previous behaviour: a synchronous 5000-row sample for the 2-minute rule —
#  replaced by the async full seed so the dashboard shows the real dataset.)
if [[ "${RUN_AUTO_SEED:-1}" == "1" ]]; then
  echo '{"level":"INFO","logger":"entrypoint","message":"enqueuing full seed task"}'
  python manage.py seed_data --async --path /app/rates_seed.parquet
fi

exec "$@"
