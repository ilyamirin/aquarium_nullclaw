# Orchestrator

The Python 3.12 orchestrator is the primary control plane for this project.

Tracked sources:

- CLI entrypoint: [orchestrator/cli.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/cli.py)
- shared service layer: [orchestrator/service_layer.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/service_layer.py)
- Django bootstrap shim: [orchestrator/django.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/django.py)
- LiteLLM helpers: [orchestrator/litellm.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/litellm.py)
- Infisical integration: [orchestrator/infisical.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/infisical.py)
- compose generation: [orchestrator/compose.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/compose.py)
- state schema: [orchestrator/models.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/models.py)
- local state helpers: [orchestrator/state.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/state.py)

## Ownership

The orchestrator owns:

- workspace secret storage and agent-first deployment compilation
- runtime inventory
- per-runtime Infisical project creation
- runtime secret upsert
- runtime service-token creation
- shared NullClaw compose generation
- LiteLLM core bootstrap
- runtime OTEL bootstrap when monitoring is enabled
- per-runtime LiteLLM key creation, rotation, revoke, and inspection
- local ignored env files and runtime homes
- runtime lifecycle and health/status
- secret-isolation checks
- DB-backed runtime lifecycle services reused by the Django control plane

It does not modify upstream `nullclaw/`.

## Current Architecture

The old orchestrator-only model has been split into:

- `orchestrator/service_layer.py`
  shared business logic and runtime operations
- `orchestrator/cli.py`
  thin terminal adapter over the service layer
- `controlplane/`
  Django + Unfold operator UI and JSON API over the same service layer

Important rule:

- the CLI does not call the web API
- the web API does not shell out to the CLI
- both use the same Python services directly

The service layer now has two concurrent contracts:

- legacy/runtime-first services for compatibility and existing operator flows
- new agent-first services that compile `AgentBuildSpec` into runtime inputs before provisioning execution

## Local State Layout

Ignored local state lives under `.aquarium/`:

- `.aquarium/state/controlplane.sqlite3`
- `.aquarium/state/runtimes.json`
- `.aquarium/state/litellm-pricing.json`
- `.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml`
- `.aquarium/runtimes/<id>/runtime.env`
- `.aquarium/runtimes/<id>/home/`
- `.aquarium/runtimes/<id>/home/config.json`
- `.aquarium/runtimes/<id>/home/workspace/`

Secrets are intentionally absent from `runtimes.json`.

Current source-of-truth rule:

- Django DB in `.aquarium/state/controlplane.sqlite3` is now primary
- `.aquarium/state/runtimes.json` is still mirrored for compatibility and recovery

Additional DB-backed agent state now lives only in the Django SQLite DB:

- workspaces
- agents
- build specs
- skill catalog entries
- workspace secrets
- deployments

Additional ignored bootstrap file outside `.aquarium/`:

- `monitoring-stack/.env`

## Runtime Schema

Mirrored per-runtime metadata still includes:

- `id`
- `enabled`
- `gateway_port`
- `telegram_enabled`
- `model`
- `runtime_role`
- `tenant_id`
- `plan_id`
- `infisical_project_slug`
- `infisical_project_id`
- `infisical_env`
- `infisical_path`
- `litellm_key_name`
- `litellm_budget_usd`
- `litellm_rpm_limit`
- `litellm_tpm_limit`
- `litellm_model_alias`
- `litellm_price_input_per_million_usd`
- `litellm_price_output_per_million_usd`
- `runtime_env_file`
- `runtime_home`
- `workspace_dir`
- `generated_config_path`

## DB And Compatibility Contract

The control plane imports existing state through:

```bash
.venv/bin/python manage.py import_runtime_state
```

After that:

- DB rows back the UI and JSON API
- compose generation reads from DB-backed services
- JSON state continues to be rewritten from DB after runtime mutations

## Shared Compose Contract

Generated compose file:

- `.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml`

Project name:

- `aquarium-nullclaw-runtimes`

Per-runtime services:

- `gateway-<runtime-id>`
- `agent-<runtime-id>`

## Current Runtime IDs

Current platform runtimes:

- `test-nullclaw`
- `probe`
- `limit-probe`

Expected ports:

- `test-nullclaw` -> `3000`
- `probe` -> `3002`
- `limit-probe` -> `3003`

## CLI Surface

Primary commands:

```bash
.venv/bin/orchestrator init
.venv/bin/orchestrator litellm bootstrap
.venv/bin/orchestrator litellm status
.venv/bin/orchestrator runtime create --id test-nullclaw --telegram --gateway-port 3000
.venv/bin/orchestrator runtime create --id probe --no-telegram --gateway-port 3002
.venv/bin/orchestrator runtime create --id limit-probe --no-telegram --gateway-port 3003 --runtime-role limit-probe
.venv/bin/orchestrator runtime up --id test-nullclaw
.venv/bin/orchestrator runtime stop --id test-nullclaw
.venv/bin/orchestrator runtime delete --id probe
.venv/bin/orchestrator runtime list
.venv/bin/orchestrator runtime status --id test-nullclaw
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
.venv/bin/orchestrator runtime rotate-key --id test-nullclaw
.venv/bin/orchestrator runtime revoke-key --id probe
.venv/bin/orchestrator runtime inspect-key --id limit-probe
.venv/bin/orchestrator runtime limits --id limit-probe
.venv/bin/orchestrator runtime sync-limits --id limit-probe
```

## What `runtime create` Does Now

`runtime create` is now the complete provisioning path.

For each runtime it:

- ensures LiteLLM is reachable
- ensures the runtime's Infisical project exists
- creates or rotates the runtime's LiteLLM key
- stores `LITELLM_API_KEY` in that runtime's Infisical project
- removes legacy `OPENROUTER_API_KEY` from that runtime project
- writes a new runtime service token into the ignored runtime env file
- writes OTEL env into the runtime env file when `monitoring-stack/.env` exists
- regenerates the shared compose file
- recreates the runtime container

## Runtime Apply Contract

Control-plane initiated runtime mutations now auto-apply:

- updating runtime budget, RPM, or TPM persists the DB state and immediately syncs the LiteLLM virtual key
- updating the runtime model alias also rewrites the runtime bootstrap env and recreates the runtime container
- saving runtime secrets rewrites bootstrap env and recreates the runtime so Infisical-backed env and rendered config are refreshed
- saving or deleting runtime-scoped integrations rewrites bootstrap env and recreates the runtime so channel/search settings take effect immediately
- `runtime sync-limits` remains the manual repair path for re-pushing the current LiteLLM limit state

## Agent-First Apply Contract

Current agent-first services in [orchestrator/service_layer.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/service_layer.py):

- `ensure_workspace`
- `bootstrap_skill_catalog`
- `upsert_workspace_secret`
- `create_draft_agent`
- `launch_agent`
- `stop_agent`
- `agent_payload`
- `agent_detail_payload`

Current behavior:

- workspace secrets are stored in the existing Infisical backend, not in Django
- draft agent creation persists only configuration objects
- launch validates the build spec, resolves workspace secret bindings, compiles the ordered skill stack into runtime settings, and then calls the existing runtime provisioning path
- deployment history is now separate from runtime lifecycle state
- runtime IDs currently reuse the agent slug as the execution identifier

## Why This Replaced The Manual Stack Split

The older `nullclaw-stack/` and `nullclaw-probe-stack/` flow proved the concept, but it does not scale into a control plane.

The orchestrator gives us:

- one control surface for many runtimes
- one shared compose project for runtimes
- a DB-backed control plane that a web UI can operate safely
- a mirrored typed local state file for compatibility
- repeatable LiteLLM key lifecycle
- a clean split between tracked control-plane code and ignored runtime instances

## Important Operational Notes

- the orchestrator is the runtime source-of-truth
- the orchestrator is also the LiteLLM-key provisioning layer
- LiteLLM is the real enforcement layer for budget/RPM/TPM limits
- runtime env now pins `NULLCLAW_MAX_ACTIONS_PER_HOUR=1000000` so NullClaw-side action throttling does not shadow LiteLLM limits
- `nullclaw-stack/` and `nullclaw-probe-stack/` are legacy/manual references only
