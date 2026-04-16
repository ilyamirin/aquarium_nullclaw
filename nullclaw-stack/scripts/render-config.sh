#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/../.."
  pwd
)

NULLCLAW_ENV_FILE=${NULLCLAW_ENV_FILE:-"$ROOT_DIR/nullclaw-stack/.env"}
NULLCLAW_HOME=${NULLCLAW_HOME:-"$ROOT_DIR/nullclaw-stack/data"}

export NULLCLAW_ENV_FILE
export NULLCLAW_HOME

exec "$ROOT_DIR/scripts/render-nullclaw-config.sh"
