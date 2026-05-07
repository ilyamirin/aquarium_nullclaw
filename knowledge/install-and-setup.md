# Installation And Initial Setup

This is the primary bootstrap document for bringing the Aquarium wrapper up from scratch.

For the public GitHub-friendly story, see:

- [`../README.md`](../README.md)
- [`../docs/demo-walkthrough.md`](../docs/demo-walkthrough.md)

It assumes the current architecture:

- Infisical for secrets
- LiteLLM for provider access, budgets, and limits
- NullClaw for agent runtime behavior
- the Python 3.12 orchestrator plus Django control plane for lifecycle management

## Project Contents

Project root: [aquarium](/Users/ilyagmirin/PycharmProjects/aquarium)

Important parts:

- upstream runtime reference: [nullclaw](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw)
- Python control plane: [orchestrator](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator)
- web control plane: [controlplane](/Users/ilyagmirin/PycharmProjects/aquarium/controlplane)
- secrets backend: [infisical-stack](/Users/ilyagmirin/PycharmProjects/aquarium/infisical-stack)
- LLM gateway: [litellm-stack](/Users/ilyagmirin/PycharmProjects/aquarium/litellm-stack)
- monitoring stack: [monitoring-stack](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack)
- project memory: [knowledge](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge)
- local commands: [Makefile](/Users/ilyagmirin/PycharmProjects/aquarium/Makefile)

Primary compose project names:

- `aquarium-infisical`
- `aquarium-litellm`
- `aquarium-monitoring`
- `aquarium-nullclaw-runtimes`

## Prerequisites

Expected local tools:

- `git`
- `docker`
- `docker compose`
- `pre-commit`
- Homebrew Python 3.12 at `/opt/homebrew/bin/python3.12`
- `infisical` CLI

Recommended install set:

```bash
brew install trivy shellcheck shfmt semgrep infisical/get-cli/infisical
```

## Step 1: Open The Project

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium
```

## Step 2: Create The Repo-Local Python 3.12 Environment

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install -e .[dev]
```

The orchestrator must be run from this `.venv`.

## Fast Demo Path

For the smallest visible recruiter/demo setup, the public happy path is:

```bash
make demo-up
make demo-check
```

That path intentionally starts only:

- `aquarium-infisical`
- `aquarium-litellm`
- the Django control plane
- `test-nullclaw`

It does not start monitoring or the legacy/manual wrapper stacks.

## Step 3: Install Git Hooks

```bash
make hooks-install
```

This enables:

- `gitleaks`
- shell formatting and linting
- YAML and JSON checks
- compose validation
- generated config validation

## Step 4: Prepare Infisical

Create the real env file:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/infisical-stack
cp .env.example .env
```

Fill in at least:

- `ENCRYPTION_KEY`
- `AUTH_SECRET`
- `POSTGRES_PASSWORD`
- `INFISICAL_ADMIN_PASSWORD`

Do not commit this file.

## Step 5: Start Infisical

From the project root:

```bash
make infisical-up
make infisical-health
```

Expected:

- `http://127.0.0.1:18080/api/status` responds
- the supported UI entry is `http://secrets.aquarium.local`

## Step 6: Create The First Infisical Admin

Open [http://secrets.aquarium.local](http://secrets.aquarium.local) and create the first user.

Then authenticate the local CLI:

```bash
INFISICAL_API_URL=http://127.0.0.1:18080 infisical login
```

The orchestrator relies on the local operator login unless `INFISICAL_OPERATOR_TOKEN` is exported manually.

## Step 7: Initialize The Orchestrator

From the project root:

```bash
.venv/bin/orchestrator init
```

This verifies:

- Python 3.12 inside `.venv`
- `docker` and `infisical`
- Infisical reachability
- local `.aquarium/` directories

## Step 8: Bootstrap LiteLLM Core Secrets

LiteLLM is the only component that should hold provider master credentials.

Bootstrap it with the real provider key:

```bash
OPENROUTER_API_KEY=... \
.venv/bin/orchestrator litellm bootstrap
```

This creates or refreshes:

- Infisical project `litellm-core`
- `LITELLM_MASTER_KEY`
- `OPENROUTER_API_KEY`
- `litellm-stack/.env`
- `litellm-stack/config.yaml`

## Step 9: Start LiteLLM

From the project root:

```bash
make litellm-up
make litellm-status
```

Expected:

- health on `http://127.0.0.1:14000/health/liveliness`
- UI on `http://127.0.0.1:14000/ui/`
- fallback login on `http://127.0.0.1:14000/fallback/login`
- OpenAPI JSON on `http://127.0.0.1:14000/openapi.json`

Current observed local UI login:

- username: `admin`
- password: the current `LITELLM_MASTER_KEY` value from the `litellm-core` Infisical project

## Step 10: Bootstrap Monitoring

From the project root:

```bash
make monitoring-bootstrap
make monitoring-up
make monitoring-health
```

Expected:

- `monitoring-core` exists in Infisical
- `monitoring-stack/.env` exists and is ignored
- Grafana responds through `http://grafana.aquarium.local`
- Loki responds on `http://127.0.0.1:13100/ready`
- Tempo responds on `http://127.0.0.1:13200/ready`
- Mimir responds on `http://127.0.0.1:13300/ready`

Operational note:

- if monitoring is bootstrapped before runtime creation, generated runtime env files automatically include OTEL settings for NullClaw

## Step 11: Create The Hosted Runtimes

Live runtime:

```bash
TELEGRAM_BOT_TOKEN=... \
TELEGRAM_ALLOW_FROM=373793732 \
.venv/bin/orchestrator runtime create \
  --id test-nullclaw \
  --telegram \
  --gateway-port 3000
```

Probe runtime:

```bash
.venv/bin/orchestrator runtime create \
  --id probe \
  --no-telegram \
  --gateway-port 3002
```

Limit test runtime:

```bash
.venv/bin/orchestrator runtime create \
  --id limit-probe \
  --no-telegram \
  --gateway-port 3003 \
  --runtime-role limit-probe
```

Important runtime contract:

- you do not pass `OPENROUTER_API_KEY` to hosted runtimes anymore
- provider master secrets live only in `litellm-core`
- runtime projects receive `LITELLM_API_KEY` instead

## Step 12: Bootstrap The Django Control Plane

Run migrations:

```bash
make controlplane-migrate
```

Import the current runtime inventory into the DB:

```bash
make controlplane-import-state
```

This import now also backfills operator-side related records so the admin console is usable immediately after migration:

- integration connections
- runtime secret refs
- runtime diagnostic snapshots
- baseline action logs

Create the first local operator:

```bash
make controlplane-bootstrap-operator
```

This creates:

- username: `admin`
- password: `admin`

Run the local UI:

```bash
make controlplane-run
```

Expected:

- [http://127.0.0.1:15000/admin/](http://127.0.0.1:15000/admin/) responds
- [http://app.aquarium.local](http://app.aquarium.local) is the supported browser entry when the perimeter stack is running
- login works with the bootstrap operator
- runtime list shows the imported runtimes
- runtime detail pages are populated instead of empty raw tables

Important state rule:

- `.aquarium/state/controlplane.sqlite3` is now the main control-plane state
- `.aquarium/state/runtimes.json` is still mirrored for compatibility

Important operator-console rule:

- the runtime detail page is the main surface for one runtime
- use it for lifecycle, limits, keys, integrations, secrets, diagnostics, and chat
- the main admin page `/admin/` is the single operator home and links directly to the working sections and runtimes
- raw `/admin/domain/...` URLs are compatibility redirects only, not supported operator entrypoints

## Step 13: Primary Checks

List runtimes:

```bash
.venv/bin/orchestrator runtime list
```

Check live status:

```bash
.venv/bin/orchestrator runtime status --id test-nullclaw
```

Check probe status:

```bash
.venv/bin/orchestrator runtime status --id probe
```

Check limit runtime status:

```bash
.venv/bin/orchestrator runtime status --id limit-probe
```

Check isolation:

```bash
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
```

## Step 13: Telegram Check

Send a message to the live bot from account `373793732`.

Expected:

- `test-nullclaw` replies
- `probe` has no Telegram integration at all
- `limit-probe` has no Telegram integration at all

## Step 14: One-Shot Runtime Check

Run one-shot through the live runtime:

```bash
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml run --rm agent-test-nullclaw agent -m "Reply with LIVE-LITELLM-OK only"
```

Expected:

- NullClaw answers through LiteLLM
- provider access works
- provider master key is still absent from the runtime project and runtime config
