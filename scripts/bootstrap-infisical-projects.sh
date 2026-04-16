#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)
INFISICAL_ENV_FILE="$ROOT_DIR/infisical-stack/.env"
LIVE_ENV_FILE="$ROOT_DIR/nullclaw-stack/.env"
PROBE_ENV_FILE="$ROOT_DIR/nullclaw-probe-stack/.env"

if [ -f "$INFISICAL_ENV_FILE" ]; then
  # shellcheck disable=SC1090
  . "$INFISICAL_ENV_FILE"
fi

require_var() {
  var_name="$1"
  eval "var_value=\${$var_name-}"
  if [ -z "$var_value" ]; then
    echo "Missing required environment variable: $var_name" >&2
    exit 1
  fi
}

api_request() {
  method="$1"
  path="$2"
  data="${3-}"

  if [ -n "$data" ]; then
    curl --fail --silent --show-error \
      --request "$method" \
      --url "${INFISICAL_API_URL}${path}" \
      --header "Authorization: Bearer $INFISICAL_ADMIN_TOKEN" \
      --header 'Content-Type: application/json' \
      --data "$data"
    return
  fi

  curl --fail --silent --show-error \
    --request "$method" \
    --url "${INFISICAL_API_URL}${path}" \
    --header "Authorization: Bearer $INFISICAL_ADMIN_TOKEN"
}

ensure_admin_token() {
  if [ -n "${INFISICAL_ADMIN_TOKEN-}" ]; then
    return
  fi

  if command -v infisical >/dev/null 2>&1; then
    token=$(INFISICAL_API_URL="$INFISICAL_API_URL" infisical user get token --plain 2>/dev/null || true)
    if [ -n "$token" ]; then
      INFISICAL_ADMIN_TOKEN="$token"
      export INFISICAL_ADMIN_TOKEN
      return
    fi
  fi

  echo "Missing INFISICAL_ADMIN_TOKEN and no active infisical CLI session found." >&2
  exit 1
}

project_id_by_slug() {
  slug="$1"
  api_request GET "/api/v1/projects" | jq -r --arg slug "$slug" '.projects[] | select(.slug == $slug) | .id' | head -n1
}

ensure_project() {
  name="$1"
  slug="$2"

  project_id=$(project_id_by_slug "$slug" || true)
  if [ -n "$project_id" ]; then
    printf '%s' "$project_id"
    return
  fi

  payload=$(jq -n \
    --arg projectName "$name" \
    --arg slug "$slug" \
    '{
      projectName: $projectName,
      slug: $slug,
      type: "secret-manager",
      shouldCreateDefaultEnvs: true,
      hasDeleteProtection: false
    }')

  api_request POST "/api/v1/projects" "$payload" | jq -r '.project.id'
}

identity_id_by_name() {
  project_id="$1"
  name="$2"

  api_request GET "/api/v1/projects/${project_id}/identities" |
    jq -r --arg name "$name" '.identities[] | select(.name == $name) | .id' |
    head -n1
}

ensure_identity() {
  project_id="$1"
  identity_name="$2"

  identity_id=$(identity_id_by_name "$project_id" "$identity_name" || true)
  if [ -z "$identity_id" ]; then
    payload=$(jq -n --arg name "$identity_name" '{name: $name, hasDeleteProtection: false}')
    identity_id=$(
      api_request POST "/api/v1/projects/${project_id}/identities" "$payload" | jq -r '.identity.id'
    )
  fi

  membership_payload='{"role":"admin"}'
  api_request POST "/api/v1/projects/${project_id}/memberships/identities/${identity_id}" "$membership_payload" >/dev/null 2>&1 ||
    api_request PATCH "/api/v1/projects/${project_id}/memberships/identities/${identity_id}" '{"roles":[{"role":"admin","isTemporary":false}]}' >/dev/null

  printf '%s' "$identity_id"
}

ensure_universal_auth() {
  identity_id="$1"

  response=$(api_request GET "/api/v1/auth/universal-auth/identities/${identity_id}" 2>/dev/null || true)
  if [ -n "$response" ]; then
    printf '%s' "$response" | jq -r '.identityUniversalAuth.clientId'
    return
  fi

  payload='{"accessTokenTTL":7200,"accessTokenMaxTTL":7200,"accessTokenNumUsesLimit":0,"accessTokenPeriod":0}'
  api_request POST "/api/v1/auth/universal-auth/identities/${identity_id}" "$payload" | jq -r '.identityUniversalAuth.clientId'
}

create_client_secret() {
  identity_id="$1"
  description="$2"

  payload=$(jq -n --arg description "$description" '{description: $description, numUsesLimit: 0, ttl: 0}')
  api_request POST "/api/v1/auth/universal-auth/identities/${identity_id}/client-secrets" "$payload" | jq -r '.clientSecret'
}

upsert_secret() {
  project_id="$1"
  secret_name="$2"
  secret_value="$3"

  payload=$(jq -n \
    --arg projectId "$project_id" \
    --arg environment "prod" \
    --arg secretValue "$secret_value" \
    --arg secretPath "/runtime" \
    '{
      projectId: $projectId,
      environment: $environment,
      secretValue: $secretValue,
      secretPath: $secretPath,
      type: "shared",
      skipMultilineEncoding: true
    }')

  api_request POST "/api/v4/secrets/${secret_name}" "$payload" >/dev/null 2>&1 ||
    api_request PATCH "/api/v4/secrets/${secret_name}" "$payload" >/dev/null
}

write_stack_env() {
  env_file="$1"
  project_id="$2"
  client_id="$3"
  client_secret="$4"

  tmp_file="${env_file}.tmp"
  touch "$env_file"
  grep -Ev '^(INFISICAL_PROJECT_ID|INFISICAL_CLIENT_ID|INFISICAL_CLIENT_SECRET)=' "$env_file" >"$tmp_file" || true
  {
    cat "$tmp_file"
    printf 'INFISICAL_PROJECT_ID=%s\n' "$project_id"
    printf 'INFISICAL_CLIENT_ID=%s\n' "$client_id"
    printf 'INFISICAL_CLIENT_SECRET=%s\n' "$client_secret"
  } >"$env_file"
  rm -f "$tmp_file"
}

require_var INFISICAL_API_URL
require_var TEST_NULLCLAW_OPENROUTER_API_KEY
require_var TEST_NULLCLAW_TELEGRAM_BOT_TOKEN
require_var TEST_NULLCLAW_TELEGRAM_ALLOW_FROM
require_var TEST_NULLCLAW_PROBE_OPENROUTER_API_KEY

ensure_admin_token

LIVE_PROJECT_ID=$(ensure_project "test-nullclaw" "test-nullclaw")
PROBE_PROJECT_ID=$(ensure_project "test-nullclaw-probe" "test-nullclaw-probe")

LIVE_IDENTITY_ID=$(ensure_identity "$LIVE_PROJECT_ID" "mi-test-nullclaw-runtime")
PROBE_IDENTITY_ID=$(ensure_identity "$PROBE_PROJECT_ID" "mi-test-nullclaw-probe-runtime")

LIVE_CLIENT_ID=$(ensure_universal_auth "$LIVE_IDENTITY_ID")
PROBE_CLIENT_ID=$(ensure_universal_auth "$PROBE_IDENTITY_ID")

LIVE_CLIENT_SECRET=$(create_client_secret "$LIVE_IDENTITY_ID" "test-nullclaw runtime")
PROBE_CLIENT_SECRET=$(create_client_secret "$PROBE_IDENTITY_ID" "test-nullclaw-probe runtime")

upsert_secret "$LIVE_PROJECT_ID" "OPENROUTER_API_KEY" "$TEST_NULLCLAW_OPENROUTER_API_KEY"
upsert_secret "$LIVE_PROJECT_ID" "TELEGRAM_BOT_TOKEN" "$TEST_NULLCLAW_TELEGRAM_BOT_TOKEN"
upsert_secret "$LIVE_PROJECT_ID" "TELEGRAM_ALLOW_FROM" "$TEST_NULLCLAW_TELEGRAM_ALLOW_FROM"
upsert_secret "$PROBE_PROJECT_ID" "OPENROUTER_API_KEY" "$TEST_NULLCLAW_PROBE_OPENROUTER_API_KEY"

write_stack_env "$LIVE_ENV_FILE" "$LIVE_PROJECT_ID" "$LIVE_CLIENT_ID" "$LIVE_CLIENT_SECRET"
write_stack_env "$PROBE_ENV_FILE" "$PROBE_PROJECT_ID" "$PROBE_CLIENT_ID" "$PROBE_CLIENT_SECRET"

echo "Bootstrapped Infisical projects and wrote machine-identity bootstrap values into:"
echo "  $LIVE_ENV_FILE"
echo "  $PROBE_ENV_FILE"
