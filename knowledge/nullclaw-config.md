# NullClaw Config And Environment

## Config Strategy

Current runtime config strategy is LiteLLM-first.

That means:

- Infisical stores secrets
- the orchestrator writes ignored runtime env files under `.aquarium/runtimes/<id>/runtime.env`
- [scripts/render-nullclaw-config.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/render-nullclaw-config.sh) renders `config.json` inside each ignored runtime home
- generated config is disposable runtime state, not a tracked source file

This matters because upstream NullClaw does not expand `${VAR}` placeholders inside `config.json`, and because provider master keys must not be written into runtime config.

## Primary Files

Tracked sources:

- state schema: [orchestrator/models.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/models.py)
- CLI: [orchestrator/cli.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/cli.py)
- shared compose generator: [orchestrator/compose.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/compose.py)
- render script: [scripts/render-nullclaw-config.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/render-nullclaw-config.sh)
- runtime entrypoint: [scripts/nullclaw-infisical-entrypoint.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/nullclaw-infisical-entrypoint.sh)

Ignored runtime artifacts:

- `.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml`
- `.aquarium/runtimes/<id>/runtime.env`
- `.aquarium/runtimes/<id>/home/config.json`

## Runtime Env Contract

Each generated runtime env file contains:

- `INFISICAL_API_URL`
- `INFISICAL_ENV`
- `INFISICAL_PATH`
- `INFISICAL_PROJECT_ID`
- `INFISICAL_TOKEN`
- `NULLCLAW_ENABLE_TELEGRAM`
- `NULLCLAW_ENABLE_SLACK`
- `NULLCLAW_ENABLE_MATTERMOST`
- `NULLCLAW_MODEL`
- `NULLCLAW_GATEWAY_HOST`
- `NULLCLAW_GATEWAY_PORT`
- `NULLCLAW_REQUIRE_PAIRING`
- `NULLCLAW_AUTONOMY_LEVEL`
- `NULLCLAW_WORKSPACE_ONLY`
- `NULLCLAW_MAX_ACTIONS_PER_HOUR`
- `NULLCLAW_LOG_TOOL_CALLS`
- `NULLCLAW_LOG_MESSAGE_RECEIPTS`
- `NULLCLAW_LOG_MESSAGE_PAYLOADS`
- `NULLCLAW_LOG_LLM_IO`
- `NULLCLAW_TOKEN_USAGE_LEDGER_ENABLED`
- `NULLCLAW_HTTP_ENABLED`
- `NULLCLAW_SEARCH_PROVIDER`
- `NULLCLAW_SEARCH_BASE_URL`
- `NULLCLAW_OTEL_ENABLED`
- `NULLCLAW_OTEL_ENDPOINT`
- `NULLCLAW_OTEL_SERVICE_NAME`
- `LITELLM_BASE_URL`

Important distinction:

- runtime env files contain bootstrap material and non-secret settings
- application secrets are injected at process start from Infisical
- provider master credentials do not belong in these runtime env files
- OTEL runtime bootstrap is injected only when `monitoring-stack/.env` exists
- `NULLCLAW_MAX_ACTIONS_PER_HOUR` is intentionally pinned to `1000000` so LiteLLM remains the real enforcement layer for budget/RPM/TPM limits

## What Gets Injected From Infisical

### `test-nullclaw`

- `LITELLM_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOW_FROM`

### `probe`

- `LITELLM_API_KEY`

### `limit-probe`

- `LITELLM_API_KEY`

Current provider master-key rule:

- `OPENROUTER_API_KEY` belongs only to `litellm-core`
- runtime projects must not retain `OPENROUTER_API_KEY`

## Generated Provider Config

The rendered runtime config uses:

- `NULLCLAW_MODEL = openai/qwen/qwen3.6-plus`
- provider key in config: `custom:http://host.docker.internal:14000/v1`
- `api_key = LITELLM_API_KEY`
- `api_mode = "chat_completions"`

This is deliberate.

The wrapper does not use a direct `openrouter` provider anymore, and it also does not rely on the upstream `openai` provider for custom base URL routing.

## Generated Config Blocks

Every generated runtime config includes:

- LiteLLM-backed `models.providers`
- `agents.defaults.model.provider`
- `agents.defaults.model.primary`
- `channels.cli = true`
- `memory.backend = "sqlite"`
- `memory.auto_save = true`
- `gateway.host`
- `gateway.port`
- `gateway.require_pairing`
- `autonomy.level`
- `autonomy.workspace_only`
- `autonomy.max_actions_per_hour`
- `diagnostics.*`
- `security.sandbox.backend = "auto"`
- `security.audit.enabled = true`

Telegram is conditional:

- `test-nullclaw` renders `channels.telegram.accounts.main`
- `probe` and `limit-probe` render no Telegram block

Additional wrapper support now exists for future control-plane driven playground profiles:

- Slack channel rendering when `NULLCLAW_ENABLE_SLACK=true`
- Mattermost channel rendering when `NULLCLAW_ENABLE_MATTERMOST=true`
- `http_request.enabled` when `NULLCLAW_HTTP_ENABLED=true`
- search provider/base URL wiring from `NULLCLAW_SEARCH_PROVIDER` and `NULLCLAW_SEARCH_BASE_URL`

Current note:

- the control plane data model already supports `playground` runtimes and richer integration settings
- the local wrapper config path is prepared for those values even though the full playground surface is still a later phase

Current action-rate policy:

- the rendered config keeps `autonomy.max_actions_per_hour` for compatibility with upstream config expectations
- the value is intentionally rendered as `1000000`, not `20`
- budget, RPM, and TPM enforcement belongs to LiteLLM virtual keys, not to a restrictive NullClaw-side action cap

## Telegram Decisions

Current `test-nullclaw` Telegram policy:

- explicit allowlist
- private replies enabled
- streaming enabled
- draft previews disabled
- binding commands enabled

Reason:

- safest path for a local hosted-bot test
- closest shape to a future private hosted assistant

## Security Defaults

The current runtime posture remains conservative:

- host-loopback-only publishing on the Docker host
- pairing enabled
- supervised autonomy
- workspace-only scope
- no unrestricted command or path allowlists
- `http_request.enabled = false`
- no public tunnel

## Diagnostics Defaults

Enabled by default:

- tool-call logs
- message receipt logs
- message payload logs
- LLM request and response preview logs
- token usage ledger

OTel remains optional and is enabled automatically only when monitoring bootstrap exists.

## Container Bind Behavior

The container command still starts NullClaw with `gateway --host ::`, while the host port is published only on `127.0.0.1`.

Why:

- this keeps host exposure loopback-only
- while avoiding container-local bind issues that broke host-side health checks in earlier iterations

## Monitoring Interaction

Current rule:

- without monitoring bootstrap, generated config keeps `diagnostics.backend = "log"`
- with monitoring bootstrap, generated config switches to `diagnostics.backend = "otel"`

That switch happens because:

1. the orchestrator writes `NULLCLAW_OTEL_*` env when [monitoring-stack/.env](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack/.env) exists
2. [scripts/render-nullclaw-config.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/render-nullclaw-config.sh) detects those env vars
3. the rendered `config.json` uses OTEL diagnostics and points to Alloy on `http://alloy.local:4318`

The runtime reaches `alloy.local` over the shared external Docker network `aquarium-monitoring`.

Important consequence:

- deep NullClaw observability events move from container logs into `Tempo`
- stdout/stderr still remains in Docker logs and therefore still reaches `Loki`
