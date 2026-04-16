#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)
CONFIG_PATH="$ROOT_DIR/nullclaw-stack/data/config.json"

if [ ! -f "$CONFIG_PATH" ]; then
  echo "generated config not present, skipping: $CONFIG_PATH"
  exit 0
fi

python3 -m json.tool "$CONFIG_PATH" >/dev/null
echo "generated config is valid JSON: $CONFIG_PATH"
