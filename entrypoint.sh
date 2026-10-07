#!/usr/bin/env bash
# Entrypoint comun a la API y al worker.
#
# RUN_MIGRATIONS=1 (solo el servicio api) aplica las migraciones antes de arrancar.
# Asi el esquema lo crea Alembic y no la aplicacion: `create_all` en el startup no
# sobrevive a ningun cambio de modelo posterior.
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-0}" == "1" ]]; then
  echo "[entrypoint] aplicando migraciones..."
  alembic upgrade head
  echo "[entrypoint] migraciones al dia"
fi

exec "$@"
