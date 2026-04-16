#!/bin/sh
set -eu

MODE="${1:-all}"
ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)
SKIP_DIRS="
$ROOT_DIR/.cache
$ROOT_DIR/.git
$ROOT_DIR/nullclaw
$ROOT_DIR/nullclaw-stack/data
"

build_skip_args() {
  for dir in $SKIP_DIRS; do
    printf '%s\n' "--skip-dirs" "$dir"
  done
}

if ! command -v trivy >/dev/null 2>&1; then
  echo "trivy is not installed. Install it to run filesystem/config security scans." >&2
  echo "Recommended commands once installed:" >&2
  echo "  trivy config $ROOT_DIR" >&2
  echo "  trivy fs $ROOT_DIR" >&2
  exit 1
fi

case "$MODE" in
  config)
    # Limit scanning to the wrapper repo, not generated caches or the upstream checkout.
    # shellcheck disable=SC2046
    trivy config $(build_skip_args) "$ROOT_DIR/nullclaw-stack"
    ;;
  fs)
    # shellcheck disable=SC2046
    trivy fs $(build_skip_args) "$ROOT_DIR"
    ;;
  all)
    # shellcheck disable=SC2046
    trivy config $(build_skip_args) "$ROOT_DIR/nullclaw-stack"
    # shellcheck disable=SC2046
    trivy fs $(build_skip_args) "$ROOT_DIR"
    ;;
  *)
    echo "usage: $0 [config|fs|all]" >&2
    exit 2
    ;;
esac
