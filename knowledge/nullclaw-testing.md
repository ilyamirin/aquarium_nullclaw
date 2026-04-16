# NullClaw Testing

## Current Acceptance Targets

Primary runtimes:

- `test-nullclaw`
- `probe`

Primary compose project:

- `aquarium-nullclaw-runtimes`

Secrets backend:

- `aquarium-infisical`

## Smoke Tests

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

### Runtime Creation

Create the live runtime:

```bash
OPENROUTER_API_KEY=... \
TELEGRAM_BOT_TOKEN=... \
TELEGRAM_ALLOW_FROM=373793732 \
.venv/bin/orchestrator runtime create --id test-nullclaw --telegram --gateway-port 3000
```

Create the probe runtime:

```bash
OPENROUTER_API_KEY=probe-distinct-key \
.venv/bin/orchestrator runtime create --id probe --no-telegram --gateway-port 3002
```

Expected:

- both runtimes appear in `.aquarium/state/runtimes.json`
- shared compose file is regenerated
- `gateway-test-nullclaw` and `gateway-probe` start in one Compose project

### Status Checks

Run:

```bash
.venv/bin/orchestrator runtime status --id test-nullclaw
.venv/bin/orchestrator runtime status --id probe
```

Expected:

- `test-nullclaw` health uses `127.0.0.1:3000/health`
- `probe` health uses `127.0.0.1:3002/health`

## Telegram Test

Only `test-nullclaw` should have Telegram enabled.

Manual flow:

1. send a message to the configured bot from account `373793732`
2. confirm a reply arrives
3. confirm `probe` has no Telegram bot attached and required no bot token for startup

Current verified status:

- this flow succeeded after the orchestrator migration
- the live bot answered correctly with secrets loaded from Infisical through runtime env injection

## Isolation Proof

Run:

```bash
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
```

Expected:

- probe can read its own OpenRouter secret
- target can read its own OpenRouter secret
- probe cannot read target OpenRouter secret

The proof is strongest when `probe` intentionally uses a distinct OpenRouter key value.

## Observability Checks

Expected runtime signals:

- service starts cleanly
- generated `config.json` exists only in ignored runtime state
- LLM request/response preview logs are enabled
- token usage ledger is enabled

Current verified status:

- both `test-nullclaw` and `probe` reached healthy state
- one-shot agent execution on `test-nullclaw` returned `LIVE-OK`
- generated `config.json` exists under `.aquarium/runtimes/<id>/home/config.json`

## Known Gaps

- service tokens are currently long-lived and stored in ignored runtime env files; secret-zero is improved but not eliminated
- the older manual stack artifacts still exist and can confuse operators if they are treated as primary paths
- the runtime plane does not yet expose an HTTP control-plane API; the Python CLI is the sole orchestrator interface for now
