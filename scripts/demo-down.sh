#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)

cd "$ROOT_DIR"

if [ -x ".venv/bin/orchestrator" ] && .venv/bin/orchestrator runtime status --id test-nullclaw >/dev/null 2>&1; then
  .venv/bin/orchestrator runtime stop --id test-nullclaw >/dev/null || true
fi

./scripts/controlplane-dev-server.sh stop >/dev/null || true
(cd litellm-stack && docker compose down) >/dev/null
(cd infisical-stack && docker compose down) >/dev/null

echo "Aquarium demo path stopped."
