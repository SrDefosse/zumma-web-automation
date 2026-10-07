#!/usr/bin/env bash
# Smoke test de punta a punta sin dependencias externas: crea un job real,
# espera a que termine y valida la forma de la respuesta.
#
#   ./scripts/smoke_test.sh [task_id] [lookup_key]
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TASK_ID="${1:-saucedemo}"
LOOKUP_KEY="${2:-}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"
SLEEP_SECONDS="${SLEEP_SECONDS:-3}"

if [[ -n "$LOOKUP_KEY" ]]; then
  payload=$(printf '{"task_id":"%s","lookup_key":"%s"}' "$TASK_ID" "$LOOKUP_KEY")
else
  payload=$(printf '{"task_id":"%s"}' "$TASK_ID")
fi

echo "==> POST $BASE_URL/tasks  $payload"
job_id=$(curl -fsS -X POST "$BASE_URL/tasks" \
  -H 'Content-Type: application/json' \
  -d "$payload" | python -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
echo "    job_id=$job_id"

for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
  response=$(curl -fsS "$BASE_URL/tasks/$job_id")
  status=$(printf '%s' "$response" | python -c 'import json,sys; print(json.load(sys.stdin)["status"])')

  case "$status" in
    completed)
      printf '%s' "$response" | python - <<'PY'
import json
import sys

body = json.load(sys.stdin)
products = body["data"]
assert products, "el job termino sin productos"
for product in products:
    assert set(product) == {"name", "price", "description", "image_url"}, product
    assert product["name"], product
    assert product["price"], product

con_imagen = sum(1 for p in products if p["image_url"])
print(f"==> OK: {len(products)} productos, {con_imagen} con imagen servida por el backend")
print(json.dumps(products[0], indent=2, ensure_ascii=False))
PY
      exit 0
      ;;
    failed)
      echo "==> El job fallo:"
      printf '%s\n' "$response"
      exit 1
      ;;
    *)
      echo "    [$attempt/$MAX_ATTEMPTS] status=$status"
      sleep "$SLEEP_SECONDS"
      ;;
  esac
done

echo "==> Timeout: el job no termino tras $((MAX_ATTEMPTS * SLEEP_SECONDS))s"
exit 1
