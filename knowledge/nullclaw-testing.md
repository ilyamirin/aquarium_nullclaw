# NullClaw Testing

## Current Acceptance Targets

Primary runtimes:

- `test-nullclaw`
- `probe`
- `limit-probe`

Primary compose projects:

- `aquarium-infisical`
- `aquarium-litellm`
- `aquarium-monitoring`
- `aquarium-nullclaw-runtimes`

Primary local operator surface:

- Django control plane at `http://127.0.0.1:15000/admin/`

## Smoke Tests

### Django Control Plane

Run:

```bash
make controlplane-migrate
make controlplane-import-state
make controlplane-bootstrap-operator
make controlplane-check
```

Expected:

- `.aquarium/state/controlplane.sqlite3` exists
- imported runtimes appear in Django DB
- operator login works in the admin UI
- operator-only API and pages are available after login

### Environment And Orchestrator

Run:

```bash
.venv/bin/orchestrator init
```

Expected:

- Python 3.12 `.venv` is accepted
- Docker is available
- Infisical CLI is available
- `http://127.0.0.1:18080/api/status` is reachable
- `.aquarium/` state layout exists

### LiteLLM Bootstrap

Run:

```bash
OPENROUTER_API_KEY=... \
.venv/bin/orchestrator litellm bootstrap
cd /Users/ilyagmirin/PycharmProjects/aquarium/litellm-stack
docker compose up -d
```

Expected:

- `litellm-core` exists in Infisical
- `litellm-stack/.env` exists and is ignored
- `litellm-stack/config.yaml` exists and contains the model mapping plus cost metadata
- LiteLLM responds on `127.0.0.1:14000`

### Runtime Creation

Create the live runtime:

```bash
TELEGRAM_BOT_TOKEN=... \
TELEGRAM_ALLOW_FROM=373793732 \
.venv/bin/orchestrator runtime create --id test-nullclaw --telegram --gateway-port 3000
```

Create the probe runtime:

```bash
.venv/bin/orchestrator runtime create --id probe --no-telegram --gateway-port 3002
```

Create the limit runtime:

```bash
.venv/bin/orchestrator runtime create --id limit-probe --no-telegram --gateway-port 3003 --runtime-role limit-probe
```

Expected:

- all runtimes appear in `.aquarium/state/runtimes.json`
- the shared compose file is regenerated
- `gateway-test-nullclaw`, `gateway-probe`, and `gateway-limit-probe` run in one compose project

If monitoring bootstrap exists:

- generated runtime env files include `NULLCLAW_OTEL_ENABLED=true`
- generated runtime env files include `NULLCLAW_OTEL_ENDPOINT=http://alloy.local:4318`
- generated runtime env files include runtime-specific `NULLCLAW_OTEL_SERVICE_NAME`

### Status Checks

Run:

```bash
.venv/bin/orchestrator runtime status --id test-nullclaw
.venv/bin/orchestrator runtime status --id probe
.venv/bin/orchestrator runtime status --id limit-probe
```

Expected:

- `test-nullclaw` health uses `127.0.0.1:3000/health`
- `probe` health uses `127.0.0.1:3002/health`
- `limit-probe` health uses `127.0.0.1:3003/health`

## Secrets And Isolation

Expected current state:

- runtime Infisical projects contain `LITELLM_API_KEY`, not `OPENROUTER_API_KEY`
- `litellm-core` contains provider master credentials
- generated runtime `config.json` contains no provider master key

Run:

```bash
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
```

Expected:

- `probe` can read its own LiteLLM key
- `test-nullclaw` can read its own LiteLLM key
- `probe` cannot read `test-nullclaw` secrets

Current verified status:

- this check passes

## Functional Runtime Behavior

Live one-shot:

```bash
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml run --rm agent-test-nullclaw agent -m "Reply with LIVE-LITELLM-OK only"
```

Expected:

- the response is returned through LiteLLM
- the runtime remains healthy

Current verified status:

- one-shot through `test-nullclaw` succeeded through LiteLLM

## Monitoring Stack

Run:

```bash
make monitoring-bootstrap
make monitoring-up
make monitoring-health
```

Expected:

- Grafana responds on `127.0.0.1:13000/api/health`
- Loki responds on `127.0.0.1:13100/ready`
- Tempo responds on `127.0.0.1:13200/ready`
- Mimir responds on `127.0.0.1:13300/ready`
- Alloy responds on `127.0.0.1:12345`

Additional signal checks:

- Loki exposes log streams for `aquarium-nullclaw-runtimes`, `aquarium-litellm`, and `aquarium-infisical`
- Mimir returns `probe_success == 1` for healthy Aquarium services
- Tempo receives traces after a live one-shot run from `agent-test-nullclaw`

## Telegram Test

Only `test-nullclaw` should have Telegram enabled.

Manual flow:

1. send a message to the configured bot from account `373793732`
2. confirm a reply arrives
3. confirm `probe` and `limit-probe` have no Telegram bot attached

Current verified status:

- this flow succeeded after the LiteLLM migration

## Limit Enforcement

### RPM Limit

The runtime role `limit-probe` is configured with RPM `1`.

Expected result on back-to-back requests:

- LiteLLM returns a `429`
- NullClaw surfaces a recognizable rate-limit failure

Current verified status:

- this path is compatible
- NullClaw surfaces `Error: error.RateLimited` and includes rate-limit style guidance
- for a clean RPM-only check, the runtime was temporarily recreated with `--budget-usd 1 --rpm-limit 1` so budget exhaustion would not mask the `429` path

### Budget Limit

The runtime role `limit-probe` is configured with a tiny spend budget derived from the parsed OpenRouter price.

Expected target:

- a deliberately verbose request exceeds the budget
- LiteLLM rejects the request

Current verified status:

- LiteLLM spend accounting works once `litellm-stack/config.yaml` contains explicit token pricing
- LiteLLM enforces the budget
- the budget-exceeded path is not cleanly translated by NullClaw

Observed behavior:

- LiteLLM logs a budget-exceeded rejection
- NullClaw surfaces the result only as `error: ApiError`

This is the main current compatibility gap.

## Price Parsing

The helper parses [OpenRouter pricing](https://openrouter.ai/qwen/qwen3.6-plus/pricing) for `qwen/qwen3.6-plus`.

Observed values on April 17, 2026:

- `$0.325 / 1M input tokens`
- `$1.95 / 1M output tokens`

Those values are cached locally and written into the LiteLLM config generation path.

## Known Gaps

- service tokens are still long-lived bootstrap material in ignored runtime env files
- budget-exceeded provider failures are not surfaced by NullClaw as clearly as RPM `429` failures
- the old manual stack artifacts still exist and can confuse operators if treated as primary
- NullClaw deep diagnostics are currently either log-backend events or OTEL traces, not both simultaneously
- the built-in control-plane chat is buffered `docker compose run` execution, not a streaming rich playground
