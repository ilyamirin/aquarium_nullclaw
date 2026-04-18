# NullClaw Operations

## Primary Stack Layout

This project now operates four active layers:

- runtime plane: `aquarium-nullclaw-runtimes`
- secrets backend: `aquarium-infisical`
- LLM gateway: `aquarium-litellm`
- monitoring plane: `aquarium-monitoring`

Tracked control-plane code:

- CLI: [orchestrator/cli.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/cli.py)
- compose generator: [orchestrator/compose.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/compose.py)
- Infisical integration: [orchestrator/infisical.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/infisical.py)
- LiteLLM helpers: [orchestrator/litellm.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/litellm.py)

Legacy/manual stack files still exist, but they are not the primary operational path.

## First-Time Setup Order

High-level order:

1. prepare `infisical-stack/.env`
2. start `aquarium-infisical`
3. create the first Infisical admin and log in locally
4. initialize the orchestrator
5. bootstrap LiteLLM core secrets
6. start `aquarium-litellm`
7. bootstrap `aquarium-monitoring`
8. create `test-nullclaw`
9. create `probe`
10. create `limit-probe`

## Start Infisical

From the project root:

```bash
make infisical-up
make infisical-health
```

Expected:

```bash
curl http://127.0.0.1:18080/api/status
```

## Bootstrap And Start LiteLLM

Bootstrap the core project:

```bash
OPENROUTER_API_KEY=... \
.venv/bin/orchestrator litellm bootstrap
```

Start the stack:

```bash
make litellm-up
make litellm-status
```

Expected URLs:

- `http://127.0.0.1:14000/`
- `http://127.0.0.1:14000/ui/`
- `http://127.0.0.1:14000/openapi.json`

## Initialize The Orchestrator

From the project root:

```bash
.venv/bin/orchestrator init
```

Or via helper:

```bash
make orchestrator-init
```

## Bootstrap Monitoring

From the project root:

```bash
make monitoring-bootstrap
make monitoring-up
make monitoring-health
```

Expected URLs:

- `http://127.0.0.1:13000`
- `http://127.0.0.1:13100/ready`
- `http://127.0.0.1:13200/ready`
- `http://127.0.0.1:13300/ready`

## Create Or Update Runtimes

Live runtime:

```bash
TELEGRAM_BOT_TOKEN=... \
TELEGRAM_ALLOW_FROM=373793732 \
.venv/bin/orchestrator runtime create --id test-nullclaw --telegram --gateway-port 3000
```

Probe runtime:

```bash
.venv/bin/orchestrator runtime create --id probe --no-telegram --gateway-port 3002
```

Limit runtime:

```bash
.venv/bin/orchestrator runtime create --id limit-probe --no-telegram --gateway-port 3003 --runtime-role limit-probe
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
.venv/bin/orchestrator runtime status --id limit-probe
```

Delete one runtime without deleting its Infisical project:

```bash
.venv/bin/orchestrator runtime delete --id probe
```

## Logs

Infisical logs:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/infisical-stack
docker compose logs -f backend
```

LiteLLM logs:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/litellm-stack
docker compose logs -f litellm
```

Runtime logs:

```bash
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml logs -f gateway-test-nullclaw
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml logs -f gateway-probe
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml logs -f gateway-limit-probe
```

Monitoring logs:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack
docker compose logs -f
```

## CLI Entry

Live one-shot through LiteLLM:

```bash
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml run --rm agent-test-nullclaw agent -m "Reply with LIVE-LITELLM-OK only"
```

Probe one-shot:

```bash
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml run --rm agent-probe agent -m "hello"
```

Limit runtime one-shot:

```bash
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml run --rm agent-limit-probe agent -m "hello"
```

## Safe Restart Procedure

If you rotate:

- Telegram credentials
- a runtime LiteLLM key
- LiteLLM core provider credentials

restart only the affected layer.

Typical runtime refresh:

```bash
.venv/bin/orchestrator runtime create --id test-nullclaw --telegram --gateway-port 3000
```

Typical LiteLLM core refresh:

```bash
OPENROUTER_API_KEY=... \
.venv/bin/orchestrator litellm bootstrap
cd /Users/ilyagmirin/PycharmProjects/aquarium/litellm-stack
docker compose up -d
```

## Isolation Check

Run:

```bash
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
```

Expected:

- `probe` can read only its own LiteLLM key
- `test-nullclaw` can read only its own LiteLLM key
- cross-project read is rejected

## Operational Notes

- `test-nullclaw` is the production-like local runtime
- `probe` exists to verify secret isolation
- `limit-probe` exists to verify budget and RPM enforcement behavior
- when monitoring bootstrap exists, NullClaw diagnostics move onto OTEL and traces go to Tempo
- service lifecycle is now owned by the Python orchestrator
