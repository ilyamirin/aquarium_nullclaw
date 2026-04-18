#!/bin/sh
set -eu

NULLCLAW_HOME=${NULLCLAW_HOME:-}

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

if [ -n "${NULLCLAW_ENV_FILE-}" ] && [ -f "$NULLCLAW_ENV_FILE" ]; then
  # shellcheck disable=SC1090
  . "$NULLCLAW_ENV_FILE"
fi

if [ -z "$NULLCLAW_HOME" ]; then
  NULLCLAW_HOME="/nullclaw-data"
fi

DATA_DIR="$NULLCLAW_HOME"
CONFIG_PATH="$DATA_DIR/config.json"
WORKSPACE_DIR="$DATA_DIR/workspace"

mkdir -p "$DATA_DIR" "$WORKSPACE_DIR"

require_var LITELLM_API_KEY
require_var LITELLM_BASE_URL

NULLCLAW_MODEL=${NULLCLAW_MODEL:-openai/qwen/qwen3.6-plus}
NULLCLAW_PROVIDER="custom:${LITELLM_BASE_URL}"
NULLCLAW_GATEWAY_PORT=${NULLCLAW_GATEWAY_PORT:-3000}
NULLCLAW_GATEWAY_HOST=${NULLCLAW_GATEWAY_HOST:-127.0.0.1}
NULLCLAW_REQUIRE_PAIRING=$(bool_or_default "${NULLCLAW_REQUIRE_PAIRING-}" true)
NULLCLAW_ENABLE_TELEGRAM=$(bool_or_default "${NULLCLAW_ENABLE_TELEGRAM-}" true)
NULLCLAW_ENABLE_SLACK=$(bool_or_default "${NULLCLAW_ENABLE_SLACK-}" false)
NULLCLAW_ENABLE_MATTERMOST=$(bool_or_default "${NULLCLAW_ENABLE_MATTERMOST-}" false)
NULLCLAW_AUTONOMY_LEVEL=${NULLCLAW_AUTONOMY_LEVEL:-supervised}
NULLCLAW_WORKSPACE_ONLY=$(bool_or_default "${NULLCLAW_WORKSPACE_ONLY-}" true)
NULLCLAW_MAX_ACTIONS_PER_HOUR=${NULLCLAW_MAX_ACTIONS_PER_HOUR:-1000000}

NULLCLAW_LOG_TOOL_CALLS=$(bool_or_default "${NULLCLAW_LOG_TOOL_CALLS-}" true)
NULLCLAW_LOG_MESSAGE_RECEIPTS=$(bool_or_default "${NULLCLAW_LOG_MESSAGE_RECEIPTS-}" true)
NULLCLAW_LOG_MESSAGE_PAYLOADS=$(bool_or_default "${NULLCLAW_LOG_MESSAGE_PAYLOADS-}" true)
NULLCLAW_LOG_LLM_IO=$(bool_or_default "${NULLCLAW_LOG_LLM_IO-}" true)
NULLCLAW_TOKEN_USAGE_LEDGER_ENABLED=$(bool_or_default "${NULLCLAW_TOKEN_USAGE_LEDGER_ENABLED-}" true)

NULLCLAW_OTEL_ENABLED=$(bool_or_default "${NULLCLAW_OTEL_ENABLED-}" false)
NULLCLAW_OTEL_ENDPOINT=${NULLCLAW_OTEL_ENDPOINT-}
NULLCLAW_OTEL_SERVICE_NAME=${NULLCLAW_OTEL_SERVICE_NAME:-nullclaw-local}
NULLCLAW_HTTP_ENABLED=$(bool_or_default "${NULLCLAW_HTTP_ENABLED-}" false)
NULLCLAW_SEARCH_PROVIDER=${NULLCLAW_SEARCH_PROVIDER-auto}
NULLCLAW_SEARCH_BASE_URL=${NULLCLAW_SEARCH_BASE_URL-}

CHANNEL_ITEMS='
    "cli": true'

if [ "$NULLCLAW_ENABLE_TELEGRAM" = "true" ]; then
  require_var TELEGRAM_BOT_TOKEN
  require_var TELEGRAM_ALLOW_FROM
  CHANNEL_ITEMS=$CHANNEL_ITEMS$(
    cat <<EOF
,
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
EOF
  )
fi

if [ "$NULLCLAW_ENABLE_SLACK" = "true" ]; then
  require_var SLACK_BOT_TOKEN
  require_var SLACK_APP_TOKEN
  require_var SLACK_SIGNING_SECRET
  SLACK_WEBHOOK_PATH=${SLACK_WEBHOOK_PATH:-/slack/events}
  CHANNEL_ITEMS=$CHANNEL_ITEMS$(
    cat <<EOF
,
    "slack": {
      "accounts": {
        "main": {
          "bot_token": "$(json_escape "$SLACK_BOT_TOKEN")",
          "app_token": "$(json_escape "$SLACK_APP_TOKEN")",
          "signing_secret": "$(json_escape "$SLACK_SIGNING_SECRET")",
          "webhook_path": "$(json_escape "$SLACK_WEBHOOK_PATH")"
        }
      }
    }
EOF
  )
fi

if [ "$NULLCLAW_ENABLE_MATTERMOST" = "true" ]; then
  require_var MATTERMOST_BOT_TOKEN
  require_var MATTERMOST_BASE_URL
  CHANNEL_ITEMS=$CHANNEL_ITEMS$(
    cat <<EOF
,
    "mattermost": {
      "accounts": {
        "main": {
          "bot_token": "$(json_escape "$MATTERMOST_BOT_TOKEN")",
          "base_url": "$(json_escape "$MATTERMOST_BASE_URL")"
        }
      }
    }
EOF
  )
fi

CHANNELS_BLOCK=$(
  cat <<EOF
  "channels": {
$CHANNEL_ITEMS
  },
EOF
)

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

HTTP_REQUEST_BLOCK=$(
  cat <<EOF
  "http_request": {
    "enabled": $NULLCLAW_HTTP_ENABLED,
    "search_provider": "$(json_escape "$NULLCLAW_SEARCH_PROVIDER")"
  }
EOF
)

if [ -n "$NULLCLAW_SEARCH_BASE_URL" ]; then
  HTTP_REQUEST_BLOCK=$(
    cat <<EOF
  "http_request": {
    "enabled": $NULLCLAW_HTTP_ENABLED,
    "search_provider": "$(json_escape "$NULLCLAW_SEARCH_PROVIDER")",
    "search_base_url": "$(json_escape "$NULLCLAW_SEARCH_BASE_URL")"
  }
EOF
  )
fi

cat >"$CONFIG_PATH" <<EOF
{
  "models": {
    "providers": {
      "$(json_escape "$NULLCLAW_PROVIDER")": {
        "api_key": "$(json_escape "$LITELLM_API_KEY")",
        "api_mode": "chat_completions"
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "provider": "$(json_escape "$NULLCLAW_PROVIDER")",
        "primary": "$(json_escape "$NULLCLAW_MODEL")"
      }
    }
  },
$CHANNELS_BLOCK
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
$HTTP_REQUEST_BLOCK
}
EOF

echo "Rendered $CONFIG_PATH"
