# NullClaw Operations

## Primary Stack Layout

This project now operates two primary layers:

- runtime plane: `aquarium-nullclaw-runtimes`
- secrets backend: `aquarium-infisical`

Tracked control-plane code:

- orchestrator CLI: [orchestrator/cli.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/cli.py)
- compose generator: [orchestrator/compose.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/compose.py)
- Infisical integration: [orchestrator/infisical.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/infisical.py)

Legacy/manual stack files still exist, but they are no longer the primary operational path.

## First-Time Setup

High-level order:

1. prepare `infisical-stack/.env`
2. start `aquarium-infisical`
3. create the first Infisical admin and log in locally
4. initialize the orchestrator
5. create `test-nullclaw`
6. create `probe`

Project root helpers live in [Makefile](/Users/ilyagmirin/PycharmProjects/aquarium/Makefile).

## Start Infisical

From the project root:

```bash
make infisical-up
make infisical-health
```

Expected health endpoint:

```bash
curl http://127.0.0.1:18080/api/status
```

The UI/API is intentionally loopback-only.

## Initialize The Orchestrator

From the project root:

```bash
.venv/bin/orchestrator init
```

Or through the helper:

```bash
make orchestrator-init
```

## Create Or Update A Runtime

Live runtime:

```bash
OPENROUTER_API_KEY=... \
TELEGRAM_BOT_TOKEN=... \
TELEGRAM_ALLOW_FROM=373793732 \
.venv/bin/orchestrator runtime create --id test-nullclaw --telegram --gateway-port 3000
```

Probe runtime:

```bash
OPENROUTER_API_KEY=probe-distinct-key \
.venv/bin/orchestrator runtime create --id probe --no-telegram --gateway-port 3002
```

## Day-To-Day Commands

List runtimes:

```bash
.venv/bin/orchestrator runtime list
```

Start one runtime:

```bash
.venv/bin/orchestrator runtime up --id test-nullclaw
```

Stop one runtime:

```bash
.venv/bin/orchestrator runtime stop --id test-nullclaw
```

Status:

```bash
.venv/bin/orchestrator runtime status --id test-nullclaw
.venv/bin/orchestrator runtime status --id probe
```

Delete one runtime without deleting the Infisical project:

```bash
.venv/bin/orchestrator runtime delete --id probe
```

## Logs

Infisical logs:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/infisical-stack
docker compose logs -f backend
```

Runtime-plane logs:

```bash
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml logs -f gateway-test-nullclaw
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml logs -f gateway-probe
```

## CLI Entry

One-shot agent execution through the shared compose file:

```bash
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml run --rm agent-test-nullclaw agent -m "hello"
```

Probe CLI:

```bash
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml run --rm agent-probe agent -m "hello"
```

## Safe Restart Procedure

When a runtime secret changes in Infisical:

1. update the secret in Infisical
2. rerun `runtime create` with the new secret value or create a fresh service token
3. restart only the affected runtime

Example:

```bash
.venv/bin/orchestrator runtime up --id test-nullclaw
```

The runtime `config.json` is regenerated on every container start through the entrypoint flow, so manual regeneration is not the normal container path.

## Isolation Check

Run:

```bash
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
```

Expected result:

- probe runtime can access only its own project secret
- cross-project read is rejected

## Operational Notes

- `test-nullclaw` is the production-like local runtime
- `probe` exists to verify isolation and to keep a second instance in the same shared compose plane
- service lifecycle is now owned by the Python orchestrator
- any future control-plane/UI change that affects lifecycle, status, restart, or rotation must update this document
