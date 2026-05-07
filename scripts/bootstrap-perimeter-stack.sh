#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)
PERIMETER_DIR="$ROOT_DIR/perimeter-stack"
ENV_FILE="$PERIMETER_DIR/.env"
USERS_EXAMPLE="$PERIMETER_DIR/authelia/users_database.yml.example"
USERS_FILE="$PERIMETER_DIR/authelia/users_database.yml"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

random_secret() {
  openssl rand -hex 24
}

ensure_env_file() {
  tmp_file="${ENV_FILE}.tmp"
  touch "$ENV_FILE"
  grep -Ev '^(PERIMETER_HTTP_PORT|AUTHELIA_SESSION_SECRET|AUTHELIA_STORAGE_ENCRYPTION_KEY|AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET|CONTROLPLANE_PUBLIC_URL|GRAFANA_PUBLIC_URL|SECRETS_PUBLIC_URL)=' "$ENV_FILE" >"$tmp_file" || true
  {
    cat "$tmp_file"
    printf 'PERIMETER_HTTP_PORT=%s\n' "${PERIMETER_HTTP_PORT:-8080}"
    printf 'AUTHELIA_SESSION_SECRET=%s\n' "${AUTHELIA_SESSION_SECRET:-$(random_secret)}"
    printf 'AUTHELIA_STORAGE_ENCRYPTION_KEY=%s\n' "${AUTHELIA_STORAGE_ENCRYPTION_KEY:-$(random_secret)}"
    printf 'AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET=%s\n' "${AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET:-$(random_secret)}"
    printf 'CONTROLPLANE_PUBLIC_URL=%s\n' "${CONTROLPLANE_PUBLIC_URL:-http://app.aquarium.local}"
    printf 'GRAFANA_PUBLIC_URL=%s\n' "${GRAFANA_PUBLIC_URL:-http://grafana.aquarium.local}"
    printf 'SECRETS_PUBLIC_URL=%s\n' "${SECRETS_PUBLIC_URL:-http://secrets.aquarium.local}"
  } >"$ENV_FILE"
  rm -f "$tmp_file"
}

ensure_users_file() {
  if [ -f "$USERS_FILE" ]; then
    return
  fi

  cp "$USERS_EXAMPLE" "$USERS_FILE"
}

require_command openssl
ensure_env_file
ensure_users_file

echo "Bootstrapped perimeter stack defaults in $ENV_FILE"
echo "Copied Authelia users file to $USERS_FILE if it was missing"
