# AGENTS.md — aquarium Project Rules

Scope: repository root, excluding the upstream-specific rules inside `nullclaw/AGENTS.md`.

## Project Shape

This repository contains:

- `nullclaw/` — upstream NullClaw source tree, treated as an imported runtime project
- `orchestrator/` — the Python 3.12 control plane that owns runtime lifecycle, local state, compose generation, and Infisical integration
- `.aquarium/` — ignored local runtime inventory, generated compose, service-token env files, and per-runtime state
- `infisical-stack/` — local self-hosted Infisical deployment used as the secrets source-of-truth
- `litellm-stack/` — internal LiteLLM gateway and UI/API plane that sits between NullClaw runtimes and model providers
- `knowledge/` — the project knowledge base and operational source-of-truth
- `nullclaw-stack/` and `nullclaw-probe-stack/` — legacy/manual wrapper artifacts kept for reference during the transition

Compose project names are part of the contract:

- primary runtime plane: `aquarium-nullclaw-runtimes`
- secrets backend: `aquarium-infisical`
- LLM gateway: `aquarium-litellm`
- legacy/manual stacks: `aquarium-nullclaw`, `aquarium-nullclaw-probe`

The upstream `nullclaw/AGENTS.md` applies only when working inside `nullclaw/`.
This root `AGENTS.md` applies to the wrapper stack, deployment flow, project docs, orchestrator, and future hosting/UI platform work.

## Git and Upstream Boundary

This repository tracks only the wrapper project.

Rules:

- do not modify `nullclaw/` as part of normal wrapper work
- do not add `nullclaw/` to this repository
- treat `nullclaw/` as a local upstream reference checkout
- keep generated runtime data and local secrets untracked
- keep `.aquarium/`, runtime env files, generated `config.json`, and local Infisical state out of git

If upstream NullClaw must be changed in the future, that should happen in its own repository flow, not as an incidental wrapper edit here.

## Knowledge Base Is Mandatory

The `knowledge/` directory is a required project artifact, not optional documentation.

Agents working in this repository must update the relevant knowledge files whenever they change:

- Python orchestrator commands, state schema, or local directory layout
- Docker Compose topology or compose project names
- environment variable contract
- runtime config generation
- service startup or shutdown flow
- logs, telemetry, diagnostics, or observability behavior
- secrets handling approach
- Infisical bootstrap, service tokens, or env-injection flow
- Telegram or model integration behavior
- testing procedures, expected outcomes, or known issues
- design decisions that matter for the future UI platform or hosting control layer
- git layout, ignore rules, hooks, security checks, or developer workflow

Do not leave important operational knowledge only in chat history.
If a change would matter to someone trying to operate, debug, or build a UI around this stack later, it must be reflected in `knowledge/`.

## Documentation Standard

Knowledge files must be:

- detailed enough to restore context after a long gap
- practically useful for operating the stack
- explicit about both "what" and "why"
- updated as source-of-truth, not as afterthought summary notes

Prefer documenting:

- exact file locations
- exact commands
- exact environment variables
- exact container/service roles
- exact assumptions and constraints
- exact known risks or next steps

## Hooks and Security Workflow

This repository uses `pre-commit` as the hook runner.

Agents changing the repo structure or developer workflow must keep these aligned:

- `.gitignore`
- `.pre-commit-config.yaml`
- security helper scripts under `scripts/`
- `pyproject.toml` if Python tooling changes
- knowledge docs describing git, hooks, scanner behavior, and orchestrator workflow

Local security baseline:

- `gitleaks` is the mandatory secret blocker
- `Trivy` is the recommended filesystem/config/container scanner
- `Semgrep` is the recommended next-layer scanner once this wrapper grows into real application/UI code

Do not weaken the secret-blocking baseline without documenting why.

## Operational Intent

This repository is being shaped into a hostable NullClaw management environment.
The Python orchestrator is now the primary runtime-management path.

Changes should support not only current manual operation, but also future UI-driven control over:

- runtime lifecycle
- config management
- secrets contract and per-instance secret isolation
- LiteLLM key lifecycle, budgets, and provider routing
- diagnostics and logs
- health status
- testing and rollout workflows

When making changes, preserve clarity for that future platform layer.

## LLM Gateway Boundary

The current platform contract is LiteLLM-first.

Rules:

- hosted NullClaw runtimes must not receive provider master keys
- provider credentials belong only to the LiteLLM core secret scope
- runtimes receive only a per-runtime LiteLLM key, LiteLLM base URL, and non-LLM secrets such as Telegram credentials
- LiteLLM budget and rate-limit behavior is part of the operational contract and must be documented when changed
- if LiteLLM responses and NullClaw error handling do not map cleanly, document the mismatch in `knowledge/` instead of hiding it
