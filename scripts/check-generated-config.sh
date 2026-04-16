#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)
found_any=0

for config_path in \
  "$ROOT_DIR/nullclaw-stack/data/config.json" \
  "$ROOT_DIR/nullclaw-probe-stack/data/config.json"; do
  if [ ! -f "$config_path" ]; then
    echo "generated config not present, skipping: $config_path"
    continue
  fi

  python3 -m json.tool "$config_path" >/dev/null
  echo "generated config is valid JSON: $config_path"
  found_any=1
done

if [ -d "$ROOT_DIR/.aquarium/runtimes" ]; then
  while IFS= read -r config_path; do
    [ -n "$config_path" ] || continue
    python3 -m json.tool "$config_path" >/dev/null
    echo "generated config is valid JSON: $config_path"
    found_any=1
  done <<EOF
$(find "$ROOT_DIR/.aquarium/runtimes" -type f -name config.json)
EOF
fi

if [ "$found_any" -eq 0 ]; then
  exit 0
fi
