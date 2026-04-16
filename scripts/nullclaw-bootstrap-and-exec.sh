#!/bin/sh
set -eu

RENDER_SCRIPT=${NULLCLAW_RENDER_CONFIG_SCRIPT:-/opt/aquarium-scripts/render-nullclaw-config.sh}

if [ ! -x "$RENDER_SCRIPT" ]; then
  echo "NullClaw render script is not executable: $RENDER_SCRIPT" >&2
  exit 1
fi

"$RENDER_SCRIPT"

exec nullclaw "$@"
