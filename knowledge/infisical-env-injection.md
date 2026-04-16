# Infisical Env Injection

## Why We Added Infisical

NullClaw is our runtime, not our long-term secrets control plane.

For this project we treat self-hosted Infisical as the secrets source-of-truth and use NullClaw as the runtime consumer.

## Current Model

We now use:

- `infisical-stack/` for centralized secret storage
- `orchestrator/` for project creation, secret upsert, service-token creation, and runtime lifecycle
- `.aquarium/runtimes/<id>/runtime.env` for ignored runtime-local bootstrap env files

Primary compose names:

- `aquarium-infisical`
- `aquarium-nullclaw-runtimes`

## Secret Boundary

We intentionally use one Infisical project per hosted NullClaw runtime.

Current runtime projects:

- `test-nullclaw`
- `probe`

Current environment slug:

- `prod`

Current secret path:

- `/runtime`

This gives us a direct mapping for a future hosting UI:

- one hosted runtime instance
- one Infisical project
- one read-only runtime service token

## Secret Naming Rule

Secrets are stored in Infisical under the same names that NullClaw expects in environment variables.

Live runtime `test-nullclaw`:

- `OPENROUTER_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOW_FROM`

Probe runtime `probe`:

- `OPENROUTER_API_KEY`

The probe runtime intentionally does not receive Telegram credentials.

## Auth Model

V1 runtime auth is no longer based on Universal Auth machine identities.

We now use:

- operator auth: local `infisical login`
- runtime auth: one read-only service token per runtime project

Service-token scope:

- `prod:/runtime`

The operator token is used by the orchestrator for:

- listing or creating projects
- upserting secrets

The runtime service token is used only inside the runtime container to read runtime secrets.

Important networking detail:

- the host-side control plane talks to Infisical at `http://127.0.0.1:18080`
- the runtime containers must talk to Infisical at `http://host.docker.internal:18080`

The orchestrator rewrites local loopback Infisical URLs into a container-facing URL when it writes each runtime env file.

## Runtime Flow

Container startup path:

1. Docker starts the custom runtime image with Infisical CLI installed.
2. The runtime env file already contains `INFISICAL_TOKEN`.
3. [scripts/nullclaw-infisical-entrypoint.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/nullclaw-infisical-entrypoint.sh) detects that token and skips `infisical login`.
4. The entrypoint runs `infisical run --token ...`.
5. Injected runtime secrets become process environment variables.
6. [scripts/render-nullclaw-config.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/render-nullclaw-config.sh) renders `config.json` inside the ignored runtime home.
7. `nullclaw gateway` or `nullclaw agent` starts from that generated config.

Important consequence:

- application secrets are not tracked in the repo
- application secrets are not stored in NullClaw’s internal encrypted config store as source-of-truth
- service tokens remain local runtime bootstrap secrets inside ignored files

## Rotation Model

Secret rotation is now:

1. update the secret value in Infisical for the target project/path
2. create a fresh service token if needed
3. restart only the affected runtime

No tracked repo files should change during this process.

## Isolation Proof

The isolation test is now owned by the orchestrator:

```bash
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
```

Expected result:

- probe can read its own `OPENROUTER_API_KEY`
- target can read its own `OPENROUTER_API_KEY`
- probe cannot read target project secrets

## Why NullClaw Built-In Secret Storage Is Not The Source Of Truth

We are deliberately not using NullClaw’s internal encrypted config store as the primary secret system.

Reason:

- it is local to one instance
- it does not give us project-per-runtime governance
- it is weaker as a foundation for a hosting control plane

We still use NullClaw as the runtime, but secret ownership now belongs to Infisical.
