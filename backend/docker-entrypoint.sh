#!/bin/sh
# Apply migrations before serving (ARCHITECTURE §19). Workers skip this: only the API container migrates.
set -e
if [ "${PERSISTENCE_BACKEND:-postgres}" = "postgres" ] && [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  alembic upgrade head
fi
exec "$@"
