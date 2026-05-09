#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)
CERT_DIR="$ROOT_DIR/perimeter-stack/certs"
CERT_FILE="$CERT_DIR/aquarium-local.pem"
KEY_FILE="$CERT_DIR/aquarium-local-key.pem"

: "${AQUARIUM_TLS_HOSTS:=app.aquarium.local auth.aquarium.local grafana.aquarium.local secrets.aquarium.local app.lvh.me auth.lvh.me grafana.lvh.me secrets.lvh.me localhost 127.0.0.1 ::1}"

if ! command -v mkcert >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Missing required command: mkcert

Install it on macOS with:
  brew install mkcert nss

Then rerun:
  make perimeter-tls
EOF
  exit 1
fi

mkdir -p "$CERT_DIR"

if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ] && [ "${AQUARIUM_TLS_FORCE:-0}" != "1" ]; then
  echo "Trusted local TLS certificate already exists:"
  echo "  $CERT_FILE"
  echo "  $KEY_FILE"
  echo "Set AQUARIUM_TLS_FORCE=1 to regenerate it."
  exit 0
fi

mkcert -install

# AQUARIUM_TLS_HOSTS is intentionally shell-split so operators can override
# the exact SAN list without editing this script.
# shellcheck disable=SC2086
set -- $AQUARIUM_TLS_HOSTS

mkcert -cert-file "$CERT_FILE" -key-file "$KEY_FILE" "$@"

echo "Wrote trusted local TLS certificate:"
echo "  $CERT_FILE"
echo "  $KEY_FILE"
echo "mkcert CA root:"
mkcert -CAROOT
