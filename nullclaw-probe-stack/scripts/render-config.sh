#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/../.."
  pwd
)

NULLCLAW_ENV_FILE=${NULLCLAW_ENV_FILE:-"$ROOT_DIR/nullclaw-probe-stack/.env"}
NULLCLAW_HOME=${NULLCLAW_HOME:-"$ROOT_DIR/nullclaw-probe-stack/data"}

export NULLCLAW_ENV_FILE
export NULLCLAW_HOME
export NULLCLAW_ENABLE_TELEGRAM="${NULLCLAW_ENABLE_TELEGRAM:-false}"

exec "$ROOT_DIR/scripts/render-nullclaw-config.sh"
