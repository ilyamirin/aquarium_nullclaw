# Installation And Initial Setup

This is the single entry document for bringing the project up from scratch.

It now assumes the Python 3.12 orchestrator is the primary runtime-management layer.

## What This Project Contains

Project root: [aquarium](/Users/ilyagmirin/PycharmProjects/aquarium)

Important parts:

- upstream reference checkout: [nullclaw](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw)
- Python control plane: [orchestrator](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator)
- secrets backend: [infisical-stack](/Users/ilyagmirin/PycharmProjects/aquarium/infisical-stack)
- project memory: [knowledge](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge)
- local developer workflow: [Makefile](/Users/ilyagmirin/PycharmProjects/aquarium/Makefile)

Primary compose project names:

- `aquarium-nullclaw-runtimes`
- `aquarium-infisical`

Legacy/manual compose names kept only for reference:

- `aquarium-nullclaw`
- `aquarium-nullclaw-probe`

## Prerequisites

Expected local tools:

- `git`
- `docker`
- `docker compose`
- `pre-commit`
- Homebrew Python 3.12 at `/opt/homebrew/bin/python3.12`
- `infisical` CLI

Recommended installs:

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

## Step 3: Install Git Hooks

```bash
make hooks-install
```

What this enables:

- secret blocking with `gitleaks`
- shell linting with `shellcheck` and `shfmt`
- YAML and JSON sanity checks
- compose validation
- generated NullClaw config validation when present

## Step 4: Prepare Infisical

Create the real Infisical env file:

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

Expected result:

- `http://127.0.0.1:18080/api/status` responds
- the UI opens on `http://127.0.0.1:18080`

## Step 6: Create The First Infisical Admin

Open the UI at [http://127.0.0.1:18080](http://127.0.0.1:18080) and create the first user.

Then authenticate the local CLI:

```bash
INFISICAL_API_URL=http://127.0.0.1:18080 infisical login
```

The orchestrator depends on an operator token from the local Infisical CLI session unless `INFISICAL_OPERATOR_TOKEN` is exported manually.

Operational note:

- the orchestrator itself talks to Infisical on `http://127.0.0.1:18080`
- runtime containers automatically get `http://host.docker.internal:18080` in their generated env files so they can reach the host service from inside Docker

## Step 7: Initialize The Orchestrator

From the project root:

```bash
.venv/bin/orchestrator init
```

This verifies:

- Python 3.12 inside `.venv`
- `docker` and `infisical` availability
- Infisical reachability
- local `.aquarium/` state layout

## Step 8: Create The First Hosted Runtime

Normal runtime:

```bash
OPENROUTER_API_KEY=... \
TELEGRAM_BOT_TOKEN=... \
TELEGRAM_ALLOW_FROM=373793732 \
.venv/bin/orchestrator runtime create \
  --id test-nullclaw \
  --telegram \
  --gateway-port 3000
```

Probe runtime:

```bash
OPENROUTER_API_KEY=probe-distinct-key \
.venv/bin/orchestrator runtime create \
  --id probe \
  --no-telegram \
  --gateway-port 3002
```

What `runtime create` does:

- creates or reuses the Infisical project
- writes runtime secrets into `prod:/runtime`
- creates a read-only service token for the runtime
- writes an ignored runtime env file
- regenerates the shared compose file
- starts the target runtime gateway

## Step 9: Primary Checks

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

Check isolation:

```bash
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
```

## Step 10: Telegram Check

Send a message to the live bot from the allowlisted account `373793732`.

The probe runtime should not have Telegram enabled at all.
