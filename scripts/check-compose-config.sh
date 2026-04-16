#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)
STACK_DIR="$ROOT_DIR/nullclaw-stack"

docker compose -f "$STACK_DIR/docker-compose.yml" config >/dev/null
echo "docker compose config is valid: $STACK_DIR/docker-compose.yml"
