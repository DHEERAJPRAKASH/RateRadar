#!/usr/bin/env bash
# Web entrypoint: apply migrations, then exec the given command (gunicorn).
# The worker/beat services override this with their own commands and skip migrate.
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-1}" == "1" ]]; then
  echo '{"level":"INFO","logger":"entrypoint","message":"applying migrations"}'
  python manage.py migrate --noinput
fi

# Auto-sample seed for fast dashboard availability (2-minute rule).
# Sample 5000 rows (~1M total) to have data immediately available.
if [[ "${RUN_AUTO_SEED:-1}" == "1" ]]; then
  echo '{"level":"INFO","logger":"entrypoint","message":"auto-sampling seed data"}'
  python manage.py seed_data --sample 5000 --path /app/rates_seed.parquet
fi

exec "$@"
