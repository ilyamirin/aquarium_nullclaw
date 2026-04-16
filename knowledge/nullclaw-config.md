# NullClaw Config And Environment

## Config Strategy

We no longer treat per-stack `.env` files as the main operational contract.

Current model:

- Infisical stores application secrets
- the orchestrator writes ignored runtime env files under `.aquarium/runtimes/<id>/runtime.env`
- [scripts/render-nullclaw-config.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/render-nullclaw-config.sh) renders `config.json` inside each ignored runtime home
- generated config is disposable runtime state, not a tracked source file

This matters because upstream NullClaw does not expand `${VAR}` placeholders inside `config.json`.

## Primary Files

Tracked sources:

- orchestrator state schema: [orchestrator/models.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/models.py)
- orchestrator CLI: [orchestrator/cli.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/cli.py)
- shared compose generator: [orchestrator/compose.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/compose.py)
- shared render script: [scripts/render-nullclaw-config.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/render-nullclaw-config.sh)
- runtime entrypoint: [scripts/nullclaw-infisical-entrypoint.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/nullclaw-infisical-entrypoint.sh)
- bootstrap exec wrapper: [scripts/nullclaw-bootstrap-and-exec.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/nullclaw-bootstrap-and-exec.sh)

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

Important distinction:

- application secrets come from Infisical
- runtime env files contain the runtime service token and non-secret settings
- if the control plane uses `127.0.0.1` or `localhost`, the orchestrator rewrites `INFISICAL_API_URL` to `host.docker.internal` for container use

## What Gets Injected From Infisical

### `test-nullclaw`

- `OPENROUTER_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOW_FROM`

### `probe`

- `OPENROUTER_API_KEY`

Telegram is intentionally absent from `probe`.

## Generated Config Blocks

Every generated runtime config includes:

- `models.providers.openrouter.api_key`
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
- `probe` renders no Telegram channel block

## Telegram Decisions

Current `test-nullclaw` Telegram decisions:

- explicit allowlist
- private replies enabled
- streaming enabled
- draft previews disabled
- binding commands enabled

Reason:

- safest way to validate a real bot
- closest shape to a future private hosted assistant

## OpenRouter Decisions

Current provider decisions:

- provider: `openrouter`
- primary model: `openrouter/qwen/qwen3.6-plus`

## Security Defaults

The current config keeps a conservative runtime posture:

- host-loopback-only publishing on the Docker host
- pairing enabled
- supervised autonomy
- workspace-only scope
- no unrestricted command/path allowlists
- `http_request.enabled = false`
- no public tunnel
- no webhook-first deployment

## Container Bind Behavior

The container command starts NullClaw with `gateway --host ::`, while the host port is still published only on `127.0.0.1`.

Why:

- container-local loopback-only bind caused unreliable host-side checks
- host exposure still remains loopback-only

## Diagnostics Defaults

Enabled by default:

- tool-call logs
- message receipt logs
- message payload logs
- LLM request/response preview logs
- token usage ledger

OTel remains optional and is not wired into the runtime env by default.
