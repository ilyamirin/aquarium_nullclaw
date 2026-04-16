# Orchestrator

The Python 3.12 orchestrator is now the primary runtime-management layer for this project.

Tracked sources:

- CLI entrypoint: [orchestrator/cli.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/cli.py)
- Infisical integration: [orchestrator/infisical.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/infisical.py)
- shared compose generation: [orchestrator/compose.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/compose.py)
- state schema: [orchestrator/models.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/models.py)
- local state helpers: [orchestrator/state.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/state.py)

## Runtime Ownership

The orchestrator owns:

- runtime inventory
- per-runtime Infisical project creation/reuse
- secret upsert into Infisical
- read-only service-token creation
- generation of the shared runtime compose file
- runtime-local env files and runtime homes
- start/stop/status/delete flows
- isolation checks

It does not modify upstream `nullclaw/`.

## Local State Layout

Ignored local state lives under `.aquarium/`:

- `.aquarium/state/runtimes.json`
- `.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml`
- `.aquarium/runtimes/<id>/runtime.env`
- `.aquarium/runtimes/<id>/home/`
- `.aquarium/runtimes/<id>/home/config.json`
- `.aquarium/runtimes/<id>/home/workspace/`

State file fields per runtime:

- `id`
- `gateway_port`
- `telegram_enabled`
- `model`
- `infisical_project_slug`
- `infisical_project_id`
- `infisical_env`
- `infisical_path`
- `runtime_env_file`
- `runtime_home`
- `workspace_dir`
- `generated_config_path`

Secrets are intentionally absent from the state file.

## Shared Compose Contract

Generated compose file:

- `.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml`

Project name:

- `aquarium-nullclaw-runtimes`

Per runtime services:

- `gateway-<runtime-id>`
- `agent-<runtime-id>`

This lets multiple hosted NullClaw runtimes live in one Compose project while still keeping isolated env files and isolated runtime homes.

## Current Runtime IDs

Acceptance runtimes:

- `test-nullclaw`
- `probe`

Expected ports:

- `test-nullclaw` -> `3000`
- `probe` -> `3002`

## CLI Surface

The public operator interface is:

```bash
.venv/bin/orchestrator init
.venv/bin/orchestrator runtime create --id test-nullclaw ...
.venv/bin/orchestrator runtime create --id probe --no-telegram ...
.venv/bin/orchestrator runtime up --id test-nullclaw
.venv/bin/orchestrator runtime stop --id test-nullclaw
.venv/bin/orchestrator runtime delete --id probe
.venv/bin/orchestrator runtime list
.venv/bin/orchestrator runtime status --id test-nullclaw
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
```

`runtime create` is the main provisioning path. It creates or reuses the Infisical project, writes secrets, creates a new service token, writes the ignored runtime env file, regenerates the shared compose file, and starts the gateway service.

## Why This Replaced The Manual Stack Split

The earlier `nullclaw-stack/` and `nullclaw-probe-stack/` flow was good enough to prove the runtime and secret model, but it does not scale into a host-control plane.

The orchestrator is a better foundation because it gives us:

- one control path for any number of runtimes
- one shared compose project
- a local state file that a future UI can read and mutate
- clean separation between tracked schema/code and ignored runtime instances
- project-per-runtime secret boundaries in Infisical without duplicating compose projects

## Important Operational Note

The orchestrator is now the source-of-truth for runtime lifecycle.

The older `nullclaw-stack/` and `nullclaw-probe-stack/` artifacts are legacy/manual references only.
They remain useful for comparison and for shell wrapper reuse, but new runtime creation should happen through the orchestrator.
