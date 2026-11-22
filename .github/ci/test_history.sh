#!/usr/bin/env bash
set -euo pipefail
: "${PG_CONTAINER:?Provide the disposable PostgreSQL container ID}"
for file in \
  .github/ci/bootstrap_postgres.sql \
  supabase/migrations/001_initial.sql \
  supabase/seed.sql \
  supabase/migrations/002_customer_routing.sql \
  supabase/routing_seed.sql \
  supabase/migrations/003_history_retrieval.sql \
  supabase/tests/history_acceptance.sql
do
  docker exec -i "$PG_CONTAINER" psql -U postgres -d sentra_test -v ON_ERROR_STOP=1 < "$file"
done
