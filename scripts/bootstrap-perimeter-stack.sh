#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)
PERIMETER_DIR="$ROOT_DIR/perimeter-stack"
ENV_FILE="$PERIMETER_DIR/.env"
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

random_password() {
  openssl rand -base64 18 | tr -d '\n'
}

hash_password() {
  password="$1"
  printf '%s' "$password" | openssl passwd -6 -stdin
}

append_env_if_missing() {
  key="$1"
  value="$2"

  if grep -Eq "^${key}=" "$ENV_FILE"; then
    return
  fi

  printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
}

ensure_env_file() {
  touch "$ENV_FILE"
  append_env_if_missing "PERIMETER_HTTP_PORT" "${PERIMETER_HTTP_PORT:-8080}"
  append_env_if_missing "AUTHELIA_SESSION_SECRET" "${AUTHELIA_SESSION_SECRET:-$(random_secret)}"
  append_env_if_missing "AUTHELIA_STORAGE_ENCRYPTION_KEY" "${AUTHELIA_STORAGE_ENCRYPTION_KEY:-$(random_secret)}"
  append_env_if_missing "AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET" "${AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET:-$(random_secret)}"
  append_env_if_missing "CONTROLPLANE_PUBLIC_URL" "${CONTROLPLANE_PUBLIC_URL:-http://app.aquarium.local}"
  append_env_if_missing "GRAFANA_PUBLIC_URL" "${GRAFANA_PUBLIC_URL:-http://grafana.aquarium.local}"
  append_env_if_missing "SECRETS_PUBLIC_URL" "${SECRETS_PUBLIC_URL:-http://secrets.aquarium.local}"
}

write_users_file() {
  password_hash="$1"

  cat >"$USERS_FILE" <<EOF
users:
  admin:
    displayname: Aquarium Admin
    email: admin@aquarium.local
    password: "$password_hash"
    groups:
      - admins
EOF
}

ensure_users_file() {
  if [ -f "$USERS_FILE" ]; then
    return
  fi

  if [ -n "${AUTHELIA_ADMIN_PASSWORD_HASH-}" ]; then
    write_users_file "$AUTHELIA_ADMIN_PASSWORD_HASH"
    echo "Wrote $USERS_FILE from AUTHELIA_ADMIN_PASSWORD_HASH"
    return
  fi

  admin_password="${AUTHELIA_ADMIN_PASSWORD-}"
  generated_password=""
  if [ -z "$admin_password" ]; then
    generated_password="$(random_password)"
    admin_password="$generated_password"
  fi

  write_users_file "$(hash_password "$admin_password")"
  if [ -n "$generated_password" ]; then
    echo "Generated one-time Authelia admin password: $generated_password"
  else
    echo "Wrote $USERS_FILE from AUTHELIA_ADMIN_PASSWORD"
  fi
}

require_command openssl
ensure_env_file
ensure_users_file

echo "Bootstrapped perimeter stack defaults in $ENV_FILE"
