# Administration

This document is the operator-facing runbook for the current Aquarium stack.

Use it for routine administration after the initial install is complete.

## Main Services

Primary services:

- runtime plane: `aquarium-nullclaw-runtimes`
- secrets backend: `aquarium-infisical`

Primary runtime ids:

- `test-nullclaw`
- `probe`

## Core Admin Commands

List runtimes:

```bash
.venv/bin/orchestrator runtime list
```

Inspect one runtime:

```bash
.venv/bin/orchestrator runtime status --id test-nullclaw
.venv/bin/orchestrator runtime status --id probe
```

Start or recreate one runtime:

```bash
.venv/bin/orchestrator runtime up --id test-nullclaw
```

Stop one runtime:

```bash
.venv/bin/orchestrator runtime stop --id test-nullclaw
```

Delete one runtime from the local control plane without deleting its Infisical project:

```bash
.venv/bin/orchestrator runtime delete --id probe
```

## Logs

Runtime gateway logs:

```bash
docker logs aquarium-nullclaw-runtimes-gateway-test-nullclaw-1
docker logs aquarium-nullclaw-runtimes-gateway-probe-1
```

Follow logs:

```bash
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml logs -f gateway-test-nullclaw
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml logs -f gateway-probe
```

Infisical logs:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/infisical-stack
docker compose logs -f backend
```

## Secret Rotation

Current practical rule:

- Infisical is the source of truth for application secrets
- `.aquarium/runtimes/<id>/runtime.env` stores only the runtime service token and non-secret runtime settings

If you rotate an app secret:

1. update the secret in Infisical for the target project and `prod:/runtime`
2. rerun `runtime create` for that runtime with the new value
3. confirm health and model behavior

Example for the live runtime:

```bash
OPENROUTER_API_KEY=... \
TELEGRAM_BOT_TOKEN=... \
TELEGRAM_ALLOW_FROM=373793732 \
.venv/bin/orchestrator runtime create --id test-nullclaw --telegram --gateway-port 3000
```

Why rerun `runtime create`:

- it refreshes the runtime-local service token and env file if needed
- it rewrites the shared compose file
- it force-recreates the gateway with fresh runtime config

## Isolation Management

Run the cross-runtime isolation proof:

```bash
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
```

Expected result:

- each runtime can read only its own OpenRouter secret
- cross-project reads do not expose the other runtime's secret value

## Telegram Administration

Only `test-nullclaw` currently has Telegram enabled.

Current live behavior:

- allowlisted user id: `373793732`
- private bot flow works
- the live runtime already answered successfully after the orchestrator migration

If Telegram stops responding:

1. check runtime health
2. inspect gateway logs
3. verify the live runtime still has the correct bot token in Infisical
4. rerun `runtime create` for `test-nullclaw`

## Recovery Notes

If the runtime plane is lost but Infisical still exists:

1. recreate `.venv`
2. run `.venv/bin/orchestrator init`
3. recreate runtimes with `runtime create`
4. verify health and isolation

If Infisical is lost:

- recover `infisical-stack/data/` from backup if possible
- otherwise bootstrap Infisical again and recreate runtime projects and secrets before starting runtimes

## Current Known Admin Constraints

- the runtime plane is CLI-driven only; there is no HTTP control-plane API yet
- service tokens are long-lived and stored in ignored local runtime env files
- older manual stacks still exist in the repo, but operators should treat them as legacy references, not as the primary path
