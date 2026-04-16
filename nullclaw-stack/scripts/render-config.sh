#!/bin/sh
set -eu

SCRIPT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")"
  pwd
)
STACK_DIR=$(
  CDPATH='' cd -- "$SCRIPT_DIR/.."
  pwd
)
ENV_FILE="$STACK_DIR/.env"
DATA_DIR="$STACK_DIR/data"
CONFIG_PATH="$DATA_DIR/config.json"
WORKSPACE_DIR="$DATA_DIR/workspace"

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  . "$ENV_FILE"
fi

require_var() {
  var_name="$1"
  eval "var_value=\${$var_name-}"
  if [ -z "${var_value}" ]; then
    echo "Missing required environment variable: $var_name" >&2
    exit 1
  fi
}

json_escape() {
  printf '%s' "$1" | sed \
    -e 's/\\/\\\\/g' \
    -e 's/"/\\"/g' \
    -e 's/\r/\\r/g' \
    -e 's/\t/\\t/g'
}

bool_or_default() {
  value="$1"
  default="$2"
  if [ -z "$value" ]; then
    printf '%s' "$default"
    return
  fi

  case "$value" in
    true | false) printf '%s' "$value" ;;
    *) printf '%s' "$default" ;;
  esac
}

mkdir -p "$DATA_DIR" "$WORKSPACE_DIR"

require_var OPENROUTER_API_KEY
require_var TELEGRAM_BOT_TOKEN
require_var TELEGRAM_ALLOW_FROM

NULLCLAW_MODEL=${NULLCLAW_MODEL:-openrouter/qwen/qwen3.6-plus}
NULLCLAW_GATEWAY_PORT=${NULLCLAW_GATEWAY_PORT:-3000}
NULLCLAW_GATEWAY_HOST=${NULLCLAW_GATEWAY_HOST:-127.0.0.1}
NULLCLAW_REQUIRE_PAIRING=$(bool_or_default "${NULLCLAW_REQUIRE_PAIRING-}" true)
NULLCLAW_AUTONOMY_LEVEL=${NULLCLAW_AUTONOMY_LEVEL:-supervised}
NULLCLAW_WORKSPACE_ONLY=$(bool_or_default "${NULLCLAW_WORKSPACE_ONLY-}" true)
NULLCLAW_MAX_ACTIONS_PER_HOUR=${NULLCLAW_MAX_ACTIONS_PER_HOUR:-20}

NULLCLAW_LOG_TOOL_CALLS=$(bool_or_default "${NULLCLAW_LOG_TOOL_CALLS-}" true)
NULLCLAW_LOG_MESSAGE_RECEIPTS=$(bool_or_default "${NULLCLAW_LOG_MESSAGE_RECEIPTS-}" true)
NULLCLAW_LOG_MESSAGE_PAYLOADS=$(bool_or_default "${NULLCLAW_LOG_MESSAGE_PAYLOADS-}" true)
NULLCLAW_LOG_LLM_IO=$(bool_or_default "${NULLCLAW_LOG_LLM_IO-}" true)
NULLCLAW_TOKEN_USAGE_LEDGER_ENABLED=$(bool_or_default "${NULLCLAW_TOKEN_USAGE_LEDGER_ENABLED-}" true)

NULLCLAW_OTEL_ENABLED=$(bool_or_default "${NULLCLAW_OTEL_ENABLED-}" false)
NULLCLAW_OTEL_ENDPOINT=${NULLCLAW_OTEL_ENDPOINT-}
NULLCLAW_OTEL_SERVICE_NAME=${NULLCLAW_OTEL_SERVICE_NAME:-nullclaw-local}

DIAGNOSTICS_BLOCK=$(
  cat <<EOF
    "diagnostics": {
      "backend": "log",
      "log_tool_calls": $NULLCLAW_LOG_TOOL_CALLS,
      "log_message_receipts": $NULLCLAW_LOG_MESSAGE_RECEIPTS,
      "log_message_payloads": $NULLCLAW_LOG_MESSAGE_PAYLOADS,
      "log_llm_io": $NULLCLAW_LOG_LLM_IO,
      "token_usage_ledger_enabled": $NULLCLAW_TOKEN_USAGE_LEDGER_ENABLED
    },
EOF
)

if [ "$NULLCLAW_OTEL_ENABLED" = "true" ] && [ -n "$NULLCLAW_OTEL_ENDPOINT" ]; then
  DIAGNOSTICS_BLOCK=$(
    cat <<EOF
    "diagnostics": {
      "backend": "otel",
      "log_tool_calls": $NULLCLAW_LOG_TOOL_CALLS,
      "log_message_receipts": $NULLCLAW_LOG_MESSAGE_RECEIPTS,
      "log_message_payloads": $NULLCLAW_LOG_MESSAGE_PAYLOADS,
      "log_llm_io": $NULLCLAW_LOG_LLM_IO,
      "token_usage_ledger_enabled": $NULLCLAW_TOKEN_USAGE_LEDGER_ENABLED,
      "otel": {
        "endpoint": "$(json_escape "$NULLCLAW_OTEL_ENDPOINT")",
        "service_name": "$(json_escape "$NULLCLAW_OTEL_SERVICE_NAME")"
      }
    },
EOF
  )
fi

cat >"$CONFIG_PATH" <<EOF
{
  "models": {
    "providers": {
      "openrouter": {
        "api_key": "$(json_escape "$OPENROUTER_API_KEY")"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "$(json_escape "$NULLCLAW_MODEL")"
      }
    }
  },
  "channels": {
    "cli": true,
    "telegram": {
      "accounts": {
        "main": {
          "bot_token": "$(json_escape "$TELEGRAM_BOT_TOKEN")",
          "allow_from": ["$(json_escape "$TELEGRAM_ALLOW_FROM")"],
          "reply_in_private": true,
          "streaming": true,
          "draft_previews": false,
          "binding_commands_enabled": true
        }
      }
    }
  },
  "memory": {
    "backend": "sqlite",
    "auto_save": true
  },
$DIAGNOSTICS_BLOCK
  "gateway": {
    "host": "$(json_escape "$NULLCLAW_GATEWAY_HOST")",
    "port": $NULLCLAW_GATEWAY_PORT,
    "require_pairing": $NULLCLAW_REQUIRE_PAIRING
  },
  "autonomy": {
    "level": "$(json_escape "$NULLCLAW_AUTONOMY_LEVEL")",
    "workspace_only": $NULLCLAW_WORKSPACE_ONLY,
    "max_actions_per_hour": $NULLCLAW_MAX_ACTIONS_PER_HOUR
  },
  "security": {
    "sandbox": {
      "backend": "auto"
    },
    "audit": {
      "enabled": true
    }
  },
  "http_request": {
    "enabled": false
  }
}
EOF

echo "Rendered $CONFIG_PATH"
