#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)

for stack_dir in \
  "$ROOT_DIR/nullclaw-stack" \
  "$ROOT_DIR/nullclaw-probe-stack" \
  "$ROOT_DIR/infisical-stack" \
  "$ROOT_DIR/litellm-stack" \
  "$ROOT_DIR/monitoring-stack" \
  "$ROOT_DIR/perimeter-stack"; do
  docker compose -f "$stack_dir/docker-compose.yml" config >/dev/null
  echo "docker compose config is valid: $stack_dir/docker-compose.yml"
done

GENERATED_COMPOSE="$ROOT_DIR/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml"
if [ -f "$GENERATED_COMPOSE" ]; then
  docker compose -f "$GENERATED_COMPOSE" config >/dev/null
  echo "docker compose config is valid: $GENERATED_COMPOSE"
fi
