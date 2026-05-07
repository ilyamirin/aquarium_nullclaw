# Infisical Env Injection

## Why We Added Infisical

NullClaw is our runtime, not our long-term secrets control plane.

For this project we treat self-hosted Infisical as the secrets source-of-truth and use:

- LiteLLM as the provider-facing gateway
- NullClaw as the runtime consumer
- the orchestrator as the provisioning layer

## Current Model

We now use:

- `infisical-stack/` for centralized secret storage
- `litellm-stack/` for provider-facing LLM access
- `orchestrator/` for project creation, secret upsert, service-token creation, and runtime lifecycle
- `.aquarium/runtimes/<id>/runtime.env` for ignored runtime-local bootstrap env files

Primary compose names:

- `aquarium-infisical`
- `aquarium-litellm`
- `aquarium-nullclaw-runtimes`

## Secret Boundary

We intentionally use one Infisical project per hosted runtime plus one dedicated LiteLLM core project.

Current projects:

- `litellm-core`
- `test-nullclaw`
- `probe`
- `limit-probe`

Current environment slug:

- `prod`

Current secret path:

- `/runtime`

## Secret Naming Rule

Secrets are stored under the names the consuming layer expects.

### `litellm-core`

- `LITELLM_MASTER_KEY`
- `OPENROUTER_API_KEY`

### `test-nullclaw`

- `LITELLM_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_ALLOW_FROM`

### `probe`

- `LITELLM_API_KEY`

### `limit-probe`

- `LITELLM_API_KEY`

The runtime projects intentionally do not keep provider master keys.

## Auth Model

We now use:

- operator auth: local `infisical login`
- runtime auth: one read-only service token per runtime project
- LiteLLM core auth: one read-only service token for `litellm-core`

Service-token scope:

- `prod:/runtime`

Important networking detail:

- the host-side control plane talks to Infisical at `http://127.0.0.1:18080`
- containers must talk to Infisical at `http://host.docker.internal:18080`
- the supported browser UI entry is now `http://secrets.aquarium.local`

The orchestrator rewrites loopback host URLs to container-facing host URLs when it writes runtime env files and LiteLLM stack env.

## Runtime Flow

Runtime container startup:

1. Docker starts the custom runtime image with Infisical CLI installed.
2. The runtime env file already contains `INFISICAL_TOKEN`.
3. [scripts/nullclaw-infisical-entrypoint.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/nullclaw-infisical-entrypoint.sh) detects that token and skips `infisical login`.
4. The entrypoint runs `infisical run --token ...`.
5. Runtime secrets such as `LITELLM_API_KEY` become process environment variables.
6. [scripts/render-nullclaw-config.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/render-nullclaw-config.sh) renders `config.json`.
7. NullClaw starts and talks to LiteLLM instead of directly to OpenRouter.

LiteLLM container startup:

1. Docker starts the custom LiteLLM image with Infisical CLI installed.
2. The stack env already contains `INFISICAL_TOKEN`.
3. [scripts/litellm-infisical-entrypoint.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/litellm-infisical-entrypoint.sh) injects `LITELLM_MASTER_KEY` and `OPENROUTER_API_KEY`.
4. LiteLLM starts with its generated config and becomes the only provider-facing component.

## Rotation Model

### Runtime key rotation

```bash
.venv/bin/orchestrator runtime rotate-key --id test-nullclaw
```

This creates a fresh LiteLLM key, stores it in the runtime project, and refreshes the runtime.

### Provider-key rotation

```bash
OPENROUTER_API_KEY=... \
.venv/bin/orchestrator litellm bootstrap
cd /Users/ilyagmirin/PycharmProjects/aquarium/litellm-stack
docker compose up -d
```

This refreshes the provider master secret inside `litellm-core` and restarts the gateway layer.

## Isolation Proof

The orchestrator-owned proof:

```bash
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
```

Expected:

- `probe` can read only its own `LITELLM_API_KEY`
- `test-nullclaw` can read only its own `LITELLM_API_KEY`
- `probe` cannot read target project secrets

Current verified status:

- this passes

## Why NullClaw Built-In Secret Storage Is Not The Source Of Truth

We are deliberately not using NullClaw's internal encrypted config store as the primary secret system.

Reason:

- it is local to one instance
- it does not give us project-per-runtime governance
- it does not model the provider boundary we want
- we need a future control plane to manage secrets and runtime keys separately

NullClaw remains the runtime, but secret ownership belongs to Infisical and provider ownership belongs to LiteLLM.
