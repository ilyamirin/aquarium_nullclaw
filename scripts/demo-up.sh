#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)

cd "$ROOT_DIR"

if [ ! -x ".venv/bin/orchestrator" ]; then
  echo "Create the repo-local .venv first and install the project into it." >&2
  exit 1
fi

echo "Starting Infisical..."
(cd infisical-stack && docker compose up -d)

if ! INFISICAL_API_URL=http://127.0.0.1:18080 infisical user get token --plain >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Infisical CLI is not logged in yet.

Run:
  INFISICAL_API_URL=http://127.0.0.1:18080 infisical login

Then re-run:
  make demo-up
EOF
  exit 1
fi

echo "Initializing local control-plane layout..."
.venv/bin/orchestrator init >/dev/null

if [ ! -f "litellm-stack/.env" ] || [ ! -f "litellm-stack/config.yaml" ]; then
  if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    echo "OPENROUTER_API_KEY is required to bootstrap LiteLLM from scratch." >&2
    exit 1
  fi
  echo "Bootstrapping LiteLLM core secrets..."
  OPENROUTER_API_KEY="$OPENROUTER_API_KEY" .venv/bin/orchestrator litellm bootstrap >/dev/null
fi

echo "Starting LiteLLM..."
(cd litellm-stack && docker compose up -d)

echo "Preparing the Django control plane..."
.venv/bin/python manage.py migrate >/dev/null
.venv/bin/python manage.py import_runtime_state >/dev/null
.venv/bin/python manage.py bootstrap_operator --username admin --password admin --email admin@aquarium.local >/dev/null
./scripts/controlplane-dev-server.sh start >/dev/null

if .venv/bin/orchestrator runtime status --id test-nullclaw >/dev/null 2>&1; then
  echo "Starting existing test-nullclaw runtime..."
  .venv/bin/orchestrator runtime up --id test-nullclaw >/dev/null
else
  echo "Creating test-nullclaw runtime..."
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
      TELEGRAM_ALLOW_FROM="${TELEGRAM_ALLOW_FROM:-373793732}" \
      .venv/bin/orchestrator runtime create --id test-nullclaw --telegram --gateway-port 3000 >/dev/null
  else
    .venv/bin/orchestrator runtime create --id test-nullclaw --no-telegram --gateway-port 3000 >/dev/null
  fi
fi

./scripts/demo-check.sh

cat <<'EOF'

Demo surfaces:
  Infisical:    http://127.0.0.1:18080
  LiteLLM UI:   http://127.0.0.1:14000/ui/
  Control plane http://127.0.0.1:15000/admin/
  Runtime:      http://127.0.0.1:3000/health
EOF
