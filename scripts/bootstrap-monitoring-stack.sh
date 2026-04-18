#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)
INFISICAL_ENV_FILE="$ROOT_DIR/infisical-stack/.env"
MONITORING_ENV_FILE="$ROOT_DIR/monitoring-stack/.env"

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

random_secret() {
  openssl rand -hex 24
}

containerized_api_url() {
  api_url="$1"

  case "$api_url" in
    http://127.0.0.1:* | http://localhost:*) printf '%s\n' "$api_url" | sed 's#://127\.0\.0\.1#://host.docker.internal#; s#://localhost#://host.docker.internal#' ;;
    https://127.0.0.1:* | https://localhost:*) printf '%s\n' "$api_url" | sed 's#://127\.0\.0\.1#://host.docker.internal#; s#://localhost#://host.docker.internal#' ;;
    *) printf '%s\n' "$api_url" ;;
  esac
}

api_request() {
  method="$1"
  path="$2"
  data="${3-}"
  query="${4-}"

  url="${INFISICAL_API_URL}${path}"
  if [ -n "$query" ]; then
    url="${url}?${query}"
  fi

  if [ -n "$data" ]; then
    curl --fail --silent --show-error \
      --request "$method" \
      --url "$url" \
      --header "Authorization: Bearer $INFISICAL_ADMIN_TOKEN" \
      --header 'Content-Type: application/json' \
      --data "$data"
    return
  fi

  curl --fail --silent --show-error \
    --request "$method" \
    --url "$url" \
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
  slug="$1"

  project_id=$(project_id_by_slug "$slug" || true)
  if [ -n "$project_id" ]; then
    printf '%s' "$project_id"
    return
  fi

  payload=$(jq -n \
    --arg projectName "$slug" \
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

ensure_secret_path() {
  project_id="$1"
  secret_path="$2"

  normalized=$(printf '%s' "$secret_path" | sed 's#^/*#/#')
  if [ "$normalized" = "/" ] || [ -z "$normalized" ]; then
    return
  fi

  current_path="/"
  printf '%s\n' "$normalized" | tr '/' '\n' | while IFS= read -r part; do
    if [ -z "$part" ]; then
      continue
    fi
    payload=$(jq -n \
      --arg projectId "$project_id" \
      --arg environment "prod" \
      --arg name "$part" \
      --arg path "$current_path" \
      '{projectId: $projectId, environment: $environment, name: $name, path: $path}')

    curl --silent --show-error \
      --request POST \
      --url "${INFISICAL_API_URL}/api/v2/folders" \
      --header "Authorization: Bearer $INFISICAL_ADMIN_TOKEN" \
      --header 'Content-Type: application/json' \
      --data "$payload" >/dev/null 2>&1 || true

    if [ "$current_path" = "/" ]; then
      current_path="/$part"
    else
      current_path="${current_path}/$part"
    fi
  done
}

read_secret() {
  project_id="$1"
  secret_name="$2"

  query=$(printf 'projectId=%s&environment=prod&secretPath=/runtime&type=shared' "$project_id")
  api_request GET "/api/v4/secrets/${secret_name}" "" "$query" 2>/dev/null | jq -r '.secret.secretValue // .secretValue // empty' || true
}

upsert_secret() {
  project_id="$1"
  secret_name="$2"
  secret_value="$3"

  ensure_secret_path "$project_id" "/runtime"

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

write_monitoring_env() {
  env_file="$1"
  project_id="$2"
  service_token="$3"

  tmp_file="${env_file}.tmp"
  touch "$env_file"
  grep -Ev '^(INFISICAL_API_URL|INFISICAL_PROJECT_ID|INFISICAL_TOKEN|INFISICAL_ENV|INFISICAL_PATH|GRAFANA_PORT|ALLOY_PORT|LOKI_PORT|TEMPO_PORT|MIMIR_PORT|OTLP_HTTP_PORT)=' "$env_file" >"$tmp_file" || true
  {
    cat "$tmp_file"
    printf 'GRAFANA_PORT=%s\n' "${GRAFANA_PORT:-13000}"
    printf 'ALLOY_PORT=%s\n' "${ALLOY_PORT:-12345}"
    printf 'LOKI_PORT=%s\n' "${LOKI_PORT:-13100}"
    printf 'TEMPO_PORT=%s\n' "${TEMPO_PORT:-13200}"
    printf 'MIMIR_PORT=%s\n' "${MIMIR_PORT:-13300}"
    printf 'OTLP_HTTP_PORT=%s\n' "${OTLP_HTTP_PORT:-4318}"
    printf 'INFISICAL_API_URL=%s\n' "$(containerized_api_url "$INFISICAL_API_URL")"
    printf 'INFISICAL_PROJECT_ID=%s\n' "$project_id"
    printf 'INFISICAL_ENV=prod\n'
    printf 'INFISICAL_PATH=/runtime\n'
    printf 'INFISICAL_TOKEN=%s\n' "$service_token"
  } >"$env_file"
  rm -f "$tmp_file"
}

require_var INFISICAL_API_URL
ensure_admin_token

PROJECT_ID=$(ensure_project "monitoring-core")

ADMIN_PASSWORD=$(read_secret "$PROJECT_ID" "GF_SECURITY_ADMIN_PASSWORD")
if [ -z "$ADMIN_PASSWORD" ]; then
  ADMIN_PASSWORD=$(random_secret)
fi

SECRET_KEY=$(read_secret "$PROJECT_ID" "GF_SECURITY_SECRET_KEY")
if [ -z "$SECRET_KEY" ]; then
  SECRET_KEY=$(random_secret)
fi

upsert_secret "$PROJECT_ID" "GF_SECURITY_ADMIN_PASSWORD" "$ADMIN_PASSWORD"
upsert_secret "$PROJECT_ID" "GF_SECURITY_SECRET_KEY" "$SECRET_KEY"

SERVICE_TOKEN=$(
  INFISICAL_API_URL="$INFISICAL_API_URL" infisical service-token create \
    --projectId "$PROJECT_ID" \
    --name monitoring-core-runtime-token \
    --access-level read \
    --scope prod:/runtime \
    --expiry-seconds 0 \
    --token-only
)

write_monitoring_env "$MONITORING_ENV_FILE" "$PROJECT_ID" "$SERVICE_TOKEN"

echo "Bootstrapped monitoring-core secrets and wrote $MONITORING_ENV_FILE"
