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

resolve_operator_token() {
  if [ -n "${INFISICAL_OPERATOR_TOKEN-}" ]; then
    printf '%s' "$INFISICAL_OPERATOR_TOKEN"
    return
  fi

  if command -v infisical >/dev/null 2>&1; then
    token="$(INFISICAL_API_URL="${INFISICAL_API_URL:-http://127.0.0.1:18080}" infisical user get token --plain 2>/dev/null || true)"
    if [ -n "$token" ]; then
      printf '%s' "$token"
    fi
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

  if command -v htpasswd >/dev/null 2>&1; then
    htpasswd -bnBC 12 "" "$password" | sed 's/^://'
    return
  fi

  if printf '%s' "$password" | openssl passwd -6 -stdin >/dev/null 2>&1; then
    printf '%s' "$password" | openssl passwd -6 -stdin
    return
  fi

  echo "Missing password hash support: install htpasswd or an openssl build with passwd -6." >&2
  exit 1
}

append_env_if_missing() {
  key="$1"
  value="$2"

  if grep -Eq "^${key}=" "$ENV_FILE"; then
    return
  fi

  printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
}

replace_legacy_env_value() {
  key="$1"
  legacy_value="$2"
  replacement_value="$3"

  if [ ! -f "$ENV_FILE" ]; then
    return
  fi

  if grep -Eq "^${key}=${legacy_value}\$" "$ENV_FILE"; then
    python3 - "$ENV_FILE" "$key" "$replacement_value" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
key = sys.argv[2]
replacement = sys.argv[3]
lines = env_path.read_text().splitlines()
updated = [f"{key}={replacement}" if line.startswith(f"{key}=") else line for line in lines]
env_path.write_text("\n".join(updated) + "\n")
PY
    echo "Updated legacy ${key}=${legacy_value} to ${replacement_value} in $ENV_FILE"
  fi
}

ensure_env_file() {
  token="$(resolve_operator_token)"
  touch "$ENV_FILE"
  replace_legacy_env_value "PERIMETER_HTTP_PORT" "8080" "${PERIMETER_HTTP_PORT:-80}"
  replace_legacy_env_value "CONTROLPLANE_PUBLIC_URL" "http://app.aquarium.local" "${CONTROLPLANE_PUBLIC_URL:-https://app.aquarium.local}"
  replace_legacy_env_value "GRAFANA_PUBLIC_URL" "http://grafana.aquarium.local" "${GRAFANA_PUBLIC_URL:-https://grafana.aquarium.local}"
  replace_legacy_env_value "SECRETS_PUBLIC_URL" "http://secrets.aquarium.local" "${SECRETS_PUBLIC_URL:-https://secrets.aquarium.local}"
  replace_legacy_env_value "AUTHELIA_PUBLIC_URL" "http://auth.aquarium.local" "${AUTHELIA_PUBLIC_URL:-https://auth.aquarium.local}"
  append_env_if_missing "PERIMETER_HTTP_PORT" "${PERIMETER_HTTP_PORT:-80}"
  append_env_if_missing "PERIMETER_HTTPS_PORT" "${PERIMETER_HTTPS_PORT:-443}"
  append_env_if_missing "AUTHELIA_SESSION_SECRET" "${AUTHELIA_SESSION_SECRET:-$(random_secret)}"
  append_env_if_missing "AUTHELIA_STORAGE_ENCRYPTION_KEY" "${AUTHELIA_STORAGE_ENCRYPTION_KEY:-$(random_secret)}"
  append_env_if_missing "AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET" "${AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET:-$(random_secret)}"
  append_env_if_missing "CONTROLPLANE_PUBLIC_URL" "${CONTROLPLANE_PUBLIC_URL:-https://app.aquarium.local}"
  append_env_if_missing "GRAFANA_PUBLIC_URL" "${GRAFANA_PUBLIC_URL:-https://grafana.aquarium.local}"
  append_env_if_missing "SECRETS_PUBLIC_URL" "${SECRETS_PUBLIC_URL:-https://secrets.aquarium.local}"
  append_env_if_missing "AUTHELIA_PUBLIC_URL" "${AUTHELIA_PUBLIC_URL:-https://auth.aquarium.local}"
  if [ -n "$token" ]; then
    append_env_if_missing "INFISICAL_OPERATOR_TOKEN" "$token"
  fi
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

  if [ -d "$USERS_FILE" ]; then
    if rmdir "$USERS_FILE" 2>/dev/null; then
      echo "Removed empty directory at $USERS_FILE so Authelia users file can be written."
    else
      echo "$USERS_FILE is a directory. Remove it before bootstrapping the perimeter stack." >&2
      exit 1
    fi
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
echo "Trusted local TLS certs are expected under $PERIMETER_DIR/certs. Run make perimeter-tls if they are missing."
if grep -Eq '^INFISICAL_OPERATOR_TOKEN=' "$ENV_FILE"; then
  echo "Stored INFISICAL_OPERATOR_TOKEN for the containerized control plane."
else
  echo "Warning: INFISICAL_OPERATOR_TOKEN was not written. Control-plane pages that resolve workspace secrets will need a host CLI login or explicit token export." >&2
fi
