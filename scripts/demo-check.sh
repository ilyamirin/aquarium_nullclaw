#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)

cd "$ROOT_DIR"

retry() {
  ATTEMPTS=$1
  shift
  COUNT=1
  while [ "$COUNT" -le "$ATTEMPTS" ]; do
    if "$@" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    COUNT=$((COUNT + 1))
  done
  "$@"
}

./scripts/controlplane-dev-server.sh status >/dev/null
retry 10 curl -fsS http://127.0.0.1:18080/api/status
retry 10 curl -fsS http://127.0.0.1:14000/health/liveliness
retry 10 curl -fsS http://127.0.0.1:15000/admin/login/
retry 30 curl -fsS http://127.0.0.1:3000/health
.venv/bin/orchestrator runtime status --id test-nullclaw >/dev/null

echo "Aquarium demo path is healthy."
