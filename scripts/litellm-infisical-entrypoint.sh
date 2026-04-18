#!/bin/sh
set -eu

require_var() {
  var_name="$1"
  eval "var_value=\${$var_name-}"
  if [ -z "$var_value" ]; then
    echo "Missing required environment variable: $var_name" >&2
    exit 1
  fi
}

require_var INFISICAL_API_URL

export INFISICAL_DISABLE_UPDATE_CHECK="${INFISICAL_DISABLE_UPDATE_CHECK:-true}"
export INFISICAL_ENV="${INFISICAL_ENV:-prod}"
export INFISICAL_PATH="${INFISICAL_PATH:-/runtime}"

if [ -n "${INFISICAL_TOKEN-}" ]; then
  export INFISICAL_TOKEN
  exec infisical run \
    --token="$INFISICAL_TOKEN" \
    --env="$INFISICAL_ENV" \
    --path="$INFISICAL_PATH" \
    -- /opt/aquarium-scripts/bootstrap-litellm-and-exec.sh "$@"
fi

require_var INFISICAL_CLIENT_ID
require_var INFISICAL_CLIENT_SECRET
require_var INFISICAL_PROJECT_ID

INFISICAL_TOKEN=$(
  infisical login \
    --method=universal-auth \
    --client-id="$INFISICAL_CLIENT_ID" \
    --client-secret="$INFISICAL_CLIENT_SECRET" \
    --silent \
    --plain
)
export INFISICAL_TOKEN

exec infisical run \
  --projectId="$INFISICAL_PROJECT_ID" \
  --env="$INFISICAL_ENV" \
  --path="$INFISICAL_PATH" \
  -- /opt/aquarium-scripts/bootstrap-litellm-and-exec.sh "$@"
