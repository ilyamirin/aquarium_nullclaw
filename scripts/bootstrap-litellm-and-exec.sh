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

require_var LITELLM_MASTER_KEY
require_var OPENROUTER_API_KEY
require_var DATABASE_URL

LITELLM_CONFIG_PATH=${LITELLM_CONFIG_PATH:-/app/config.yaml}
LITELLM_PORT=${LITELLM_PORT:-4000}

exec litellm --config "$LITELLM_CONFIG_PATH" --port "$LITELLM_PORT" "$@"
