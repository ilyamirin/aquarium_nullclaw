# LiteLLM Gateway

This project now uses LiteLLM as the mandatory LLM gateway between hosted NullClaw runtimes and external model providers.

## Purpose

LiteLLM exists here to solve platform problems that upstream NullClaw does not solve well enough on its own:

- per-runtime LLM keys
- spend and rate-limit policy
- provider routing boundary
- centralized LLM usage and pricing visibility
- internal operator API and UI for LLM access control

The operational rule is simple:

- NullClaw never receives provider master keys
- LiteLLM is the only component allowed to hold provider master credentials
- each runtime gets its own LiteLLM key

## Stack Shape

Tracked files:

- compose stack: [litellm-stack/docker-compose.yml](/Users/ilyagmirin/PycharmProjects/aquarium/litellm-stack/docker-compose.yml)
- LiteLLM config template output: [litellm-stack/config.yaml](/Users/ilyagmirin/PycharmProjects/aquarium/litellm-stack/config.yaml)
- custom image: [docker/litellm-infisical.Dockerfile](/Users/ilyagmirin/PycharmProjects/aquarium/docker/litellm-infisical.Dockerfile)
- entrypoint: [scripts/litellm-infisical-entrypoint.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/litellm-infisical-entrypoint.sh)
- bootstrap exec wrapper: [scripts/bootstrap-litellm-and-exec.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/bootstrap-litellm-and-exec.sh)
- orchestration helpers: [orchestrator/litellm.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/litellm.py)

Compose project name:

- `aquarium-litellm`

Services:

- `litellm`
- `litellm-db`

## Setup Path

Minimal operator sequence:

```bash
.venv/bin/orchestrator init
OPENROUTER_API_KEY=... .venv/bin/orchestrator litellm bootstrap
cd /Users/ilyagmirin/PycharmProjects/aquarium/litellm-stack
docker compose up -d
cd /Users/ilyagmirin/PycharmProjects/aquarium
.venv/bin/orchestrator litellm status
```

What this produces:

- `litellm-core` project in Infisical
- `LITELLM_MASTER_KEY`
- `OPENROUTER_API_KEY`
- `litellm-stack/.env`
- `litellm-stack/config.yaml`
- `aquarium-litellm` running on loopback

## URLs

Host-loopback endpoints:

- root: `http://127.0.0.1:14000/`
- admin UI: `http://127.0.0.1:14000/ui/`
- fallback login: `http://127.0.0.1:14000/fallback/login`
- OpenAPI JSON: `http://127.0.0.1:14000/openapi.json`
- health: `http://127.0.0.1:14000/health/liveliness`

Container-facing endpoint used by NullClaw runtimes:

- `http://host.docker.internal:14000/v1`

Important note:

- the current image answers on `/` and `/ui/`
- `/docs` is not the stable operator path in this setup and should not be treated as the primary UI

## UI Login

Current observed fallback UI login behavior in this local stack:

- username: `admin`
- password: the current `LITELLM_MASTER_KEY` value from the `litellm-core` Infisical project

Meaning:

- this is not a separately provisioned local user account
- the fallback login uses the LiteLLM master key as the effective admin credential
- the real secret still lives in Infisical as `LITELLM_MASTER_KEY`

Operator implication:

- do not treat `admin + LITELLM_MASTER_KEY` as an independently managed identity pair
- treat it as a UI wrapper around the same master secret

## Secret Boundary

Infisical project layout now has a dedicated LiteLLM core project:

- `litellm-core`

Secrets stored there:

- `LITELLM_MASTER_KEY`
- `OPENROUTER_API_KEY`

Runtime projects no longer store provider master keys.

Runtime projects store:

- `LITELLM_API_KEY`
- `TELEGRAM_BOT_TOKEN` when Telegram is enabled
- `TELEGRAM_ALLOW_FROM` when Telegram is enabled

## How NullClaw Talks To LiteLLM

NullClaw runtime config is rendered by [scripts/render-nullclaw-config.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/render-nullclaw-config.sh).

Important implementation detail:

- the upstream `openai` provider path in NullClaw does not honor a custom `base_url` in the way we need
- the wrapper therefore uses a `custom:<base-url>` provider with `api_mode = "chat_completions"`

Current generated provider shape:

- provider key in config: `custom:http://host.docker.internal:14000/v1`
- `api_key` value: runtime-specific `LITELLM_API_KEY`
- `primary` model alias: `openai/qwen/qwen3.6-plus`

This lets NullClaw hit LiteLLM's OpenAI-compatible endpoint without modifying upstream `nullclaw/`.

## Orchestrator Responsibilities

The orchestrator now owns LiteLLM lifecycle below the operator level.

Relevant commands:

```bash
.venv/bin/orchestrator litellm bootstrap
.venv/bin/orchestrator litellm status
.venv/bin/orchestrator runtime create --id test-nullclaw --telegram --gateway-port 3000
.venv/bin/orchestrator runtime rotate-key --id test-nullclaw
.venv/bin/orchestrator runtime revoke-key --id probe
.venv/bin/orchestrator runtime inspect-key --id test-nullclaw
.venv/bin/orchestrator runtime limits --id test-nullclaw
.venv/bin/orchestrator runtime sync-limits --id test-nullclaw
```

What `litellm bootstrap` does:

- ensures the `litellm-core` Infisical project exists
- stores or refreshes `LITELLM_MASTER_KEY`
- stores or refreshes `OPENROUTER_API_KEY`
- creates a read-only service token for the LiteLLM stack
- writes `litellm-stack/.env`
- writes `litellm-stack/config.yaml`

What `runtime create` now does in addition to the older flow:

- verifies LiteLLM reachability
- creates or rotates a per-runtime LiteLLM key
- attaches runtime metadata to the LiteLLM key
- stores the runtime key in the runtime's Infisical project as `LITELLM_API_KEY`
- removes legacy `OPENROUTER_API_KEY` from that runtime project

Example live provisioning:

```bash
TELEGRAM_BOT_TOKEN=... \
TELEGRAM_ALLOW_FROM=373793732 \
.venv/bin/orchestrator runtime create --id test-nullclaw --telegram --gateway-port 3000
```

## Runtime Roles

The current runtime roles are:

- `live`
  used by `test-nullclaw`
- `probe`
  used by `probe`
- `limit-probe`
  used by `limit-probe`

Current runtime intent:

- `test-nullclaw`
  normal Telegram-connected runtime
- `probe`
  secret-isolation runtime without Telegram
- `limit-probe`
  dedicated runtime for spend and RPM testing

## Pricing Source

The current price source for `qwen/qwen3.6-plus` is [OpenRouter pricing](https://openrouter.ai/qwen/qwen3.6-plus/pricing).

Observed values from April 17, 2026:

- input: `$0.325 / 1M tokens`
- output: `$1.95 / 1M tokens`

The helper in [orchestrator/litellm.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/litellm.py) parses this page and caches the result in `.aquarium/state/litellm-pricing.json`.

The current generated LiteLLM config also writes explicit cost-per-token metadata into `litellm-stack/config.yaml` so spend accounting is not left implicit.

## Limit Policy

Current default policies:

- `test-nullclaw`
  budget `10.0`, RPM `180`, TPM `400000`
- `probe`
  budget `0.05`, RPM `10`, TPM `20000`
- `limit-probe`
  budget computed from parsed price and intentionally tiny, RPM `1`, TPM `20000`

The current `limit-probe` budget is computed from a very small token allowance derived from the parsed model price. The point is not production realism. The point is deterministic failure testing.

## Operator Troubleshooting

Status:

```bash
.venv/bin/orchestrator litellm status
```

Logs:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/litellm-stack
docker compose logs -f litellm
```

Common checks:

- confirm `http://127.0.0.1:14000/health/liveliness`
- confirm `http://127.0.0.1:14000/ui/`
- confirm `http://127.0.0.1:14000/openapi.json`
- confirm `litellm-stack/config.yaml` still contains the expected model mapping and cost metadata
- confirm `litellm-core` still holds `LITELLM_MASTER_KEY` and `OPENROUTER_API_KEY`

## Verified Behavior

Verified working:

- LiteLLM health responds on loopback
- LiteLLM root UI is reachable on loopback
- LiteLLM admin UI is reachable on `/ui/`
- live one-shot NullClaw call succeeds through LiteLLM
- each runtime has a distinct LiteLLM key
- runtime projects no longer need `OPENROUTER_API_KEY`
- `probe` cannot read `test-nullclaw` LiteLLM secrets

Verified limit behavior:

- RPM limiting is compatible with NullClaw
- LiteLLM returns `429` for RPM exhaustion
- NullClaw surfaces this as a recognizable rate-limit failure

Current compatibility gap:

- spend-budget exhaustion is enforced by LiteLLM
- LiteLLM returns a budget failure as a non-`429` provider error
- NullClaw currently surfaces that path only as a generic `ApiError`

This means:

- the platform can enforce budgets in LiteLLM
- but the end-user error wording from NullClaw is not yet good enough on the budget-exceeded path

Because upstream `nullclaw/` must not be patched here, this gap is currently documented rather than hidden.
