#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)
LIVE_ENV_FILE="$ROOT_DIR/nullclaw-stack/.env"
PROBE_ENV_FILE="$ROOT_DIR/nullclaw-probe-stack/.env"

require_var() {
  var_name="$1"
  eval "var_value=\${$var_name-}"
  if [ -z "$var_value" ]; then
    echo "Missing required environment variable: $var_name" >&2
    exit 1
  fi
}

load_env_file() {
  env_file="$1"
  if [ ! -f "$env_file" ]; then
    echo "Missing env file: $env_file" >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  . "$env_file"
}

login_identity() {
  api_url="$1"
  client_id="$2"
  client_secret="$3"

  curl --fail --silent --show-error \
    --request POST \
    --url "${api_url}/api/v1/auth/universal-auth/login" \
    --header 'Content-Type: application/json' \
    --data "$(jq -n --arg clientId "$client_id" --arg clientSecret "$client_secret" '{clientId: $clientId, clientSecret: $clientSecret}')" |
    jq -r '.accessToken'
}

can_read_own_runtime() {
  api_url="$1"
  token="$2"
  project_id="$3"

  INFISICAL_API_URL="$api_url" infisical secrets \
    --token="$token" \
    --projectId="$project_id" \
    --env=prod \
    --path=/runtime \
    --silent >/dev/null
}

cannot_read_other_runtime() {
  api_url="$1"
  token="$2"
  project_id="$3"

  if INFISICAL_API_URL="$api_url" infisical secrets \
    --token="$token" \
    --projectId="$project_id" \
    --env=prod \
    --path=/runtime \
    --silent >/dev/null 2>&1; then
    echo "Unexpectedly read forbidden project secrets: $project_id" >&2
    exit 1
  fi
}

command -v infisical >/dev/null 2>&1 || {
  echo "The infisical CLI is required for this check." >&2
  exit 1
}

load_env_file "$LIVE_ENV_FILE"
require_var INFISICAL_API_URL
require_var INFISICAL_PROJECT_ID
require_var INFISICAL_CLIENT_ID
require_var INFISICAL_CLIENT_SECRET
LIVE_API_URL="$INFISICAL_API_URL"
LIVE_PROJECT_ID="$INFISICAL_PROJECT_ID"
LIVE_CLIENT_ID="$INFISICAL_CLIENT_ID"
LIVE_CLIENT_SECRET="$INFISICAL_CLIENT_SECRET"

load_env_file "$PROBE_ENV_FILE"
require_var INFISICAL_API_URL
require_var INFISICAL_PROJECT_ID
require_var INFISICAL_CLIENT_ID
require_var INFISICAL_CLIENT_SECRET
PROBE_API_URL="$INFISICAL_API_URL"
PROBE_PROJECT_ID="$INFISICAL_PROJECT_ID"
PROBE_CLIENT_ID="$INFISICAL_CLIENT_ID"
PROBE_CLIENT_SECRET="$INFISICAL_CLIENT_SECRET"

LIVE_TOKEN=$(login_identity "$LIVE_API_URL" "$LIVE_CLIENT_ID" "$LIVE_CLIENT_SECRET")
PROBE_TOKEN=$(login_identity "$PROBE_API_URL" "$PROBE_CLIENT_ID" "$PROBE_CLIENT_SECRET")

can_read_own_runtime "$LIVE_API_URL" "$LIVE_TOKEN" "$LIVE_PROJECT_ID"
can_read_own_runtime "$PROBE_API_URL" "$PROBE_TOKEN" "$PROBE_PROJECT_ID"
cannot_read_other_runtime "$LIVE_API_URL" "$LIVE_TOKEN" "$PROBE_PROJECT_ID"
cannot_read_other_runtime "$PROBE_API_URL" "$PROBE_TOKEN" "$LIVE_PROJECT_ID"

echo "Infisical project isolation checks passed."
