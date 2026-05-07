# Knowledge Base

This directory is the internal project memory for Aquarium.

Public-facing demo documentation now lives in `docs/`.

Use the two layers intentionally:

- `docs/`
  public GitHub-facing architecture, walkthrough, and security story
- `knowledge/`
  internal operator memory, exact runbooks, and implementation source-of-truth

Current platform shape:

- `Authelia` is the intended SSO boundary for the control plane
- `Agent` is becoming the primary product object in the UI/API
- `NullClaw` is the hosted runtime
- `LiteLLM` is the mandatory LLM gateway
- `Infisical` is the secrets source-of-truth
- `Grafana + Alloy + Loki + Tempo + Mimir` is the local monitoring plane
- `orchestrator/` is the runtime and LiteLLM key control plane

If you are returning to the project after a break and need the operational truth, start here.

If you want the public demo story first, start with:

- [`../README.md`](../README.md)
- [`../docs/architecture.md`](../docs/architecture.md)
- [`../docs/demo-walkthrough.md`](../docs/demo-walkthrough.md)
- [`../docs/security-model.md`](../docs/security-model.md)

## Layout

- [install-and-setup.md](install-and-setup.md)
  End-to-end bootstrap document for prerequisites, `.venv`, hooks, Infisical, orchestrator install, and the first runtime creation.
- [orchestrator.md](orchestrator.md)
  Primary control-plane document: local state layout, generated compose, CLI commands, and runtime lifecycle rules.
- [controlplane.md](controlplane.md)
  Django + Unfold web control plane, DB-backed state model, Authelia-compatible entrypoints, agent-first UI/API, and management commands.
- [litellm-gateway.md](litellm-gateway.md)
  LiteLLM-first gateway model, provider boundary, runtime keys, bootstrap flow, UI/API access, budgets, and current compatibility findings.
- [administration.md](administration.md)
  Operator runbook for health checks, logs, restarts, rotations, isolation checks, and recovery.
- [monitoring-stack.md](monitoring-stack.md)
  Monitoring architecture, signal flow, Infisical bootstrap model, endpoints, and operator workflow for Grafana/Alloy/Loki/Tempo/Mimir.
  Implementation plan for the future service admin UI, client admin UI, and playground runtime/integrations.
- [infisical-env-injection.md](infisical-env-injection.md)
  Centralized secret model, project-per-runtime isolation, service-token auth, and runtime env injection flow.
- [nullclaw-overview.md](nullclaw-overview.md)
  What NullClaw is, what parts of upstream we use, and why the current stack is shaped this way.
- [nullclaw-config.md](nullclaw-config.md)
  Environment variables, generated config structure, security defaults, and runtime integration decisions.
- [nullclaw-operations.md](nullclaw-operations.md)
  How to start Infisical, create runtimes, inspect health, view logs, and operate the services.
- [nullclaw-testing.md](nullclaw-testing.md)
  Smoke tests, Telegram checks, isolation proof, and known gaps.
- [git-security.md](git-security.md)
  Git repo layout, ignore rules, hook workflow, and scanner rationale.

## Repository Map

- Upstream runtime source: [`../nullclaw/`](../nullclaw/)
- Python control plane: [`../orchestrator/`](../orchestrator/)
- Generated local runtime state: `.aquarium/`
- Secrets backend: [`../infisical-stack/`](../infisical-stack/)
- LiteLLM gateway: [`../litellm-stack/`](../litellm-stack/)
- Monitoring stack: [`../monitoring-stack/`](../monitoring-stack/)
- Legacy/manual wrappers: [`../nullclaw-stack/`](../nullclaw-stack/), [`../nullclaw-probe-stack/`](../nullclaw-probe-stack/)

Compose project names:

- `aquarium-nullclaw-runtimes`
- `aquarium-infisical`
- `aquarium-litellm`
- `aquarium-monitoring`
- legacy/manual only: `aquarium-nullclaw`, `aquarium-nullclaw-probe`

## Start Here

If you want to run the project from scratch, use this order:

1. [install-and-setup.md](install-and-setup.md)
2. [orchestrator.md](orchestrator.md)
3. [controlplane.md](controlplane.md)
4. [litellm-gateway.md](litellm-gateway.md)
5. [monitoring-stack.md](monitoring-stack.md)
6. [administration.md](administration.md)
7. [infisical-env-injection.md](infisical-env-injection.md)
8. [nullclaw-config.md](nullclaw-config.md)
9. [nullclaw-operations.md](nullclaw-operations.md)
10. [nullclaw-testing.md](nullclaw-testing.md)
11. [git-security.md](git-security.md)

If you want the architectural context first, start with:

1. [nullclaw-overview.md](nullclaw-overview.md)
2. [litellm-gateway.md](litellm-gateway.md)

If you specifically need the LiteLLM setup and operator path, read in this order:

1. [install-and-setup.md](install-and-setup.md)
2. [litellm-gateway.md](litellm-gateway.md)
3. [administration.md](administration.md)

If you specifically need the new agent-cloud direction, read in this order:

1. [controlplane.md](controlplane.md)
2. [orchestrator.md](orchestrator.md)
3. [`../docs/superpowers/specs/2026-05-07-agent-cloud-v1-design.md`](../docs/superpowers/specs/2026-05-07-agent-cloud-v1-design.md)

If you specifically need Agent Builder personality presets, read:

1. [controlplane.md](controlplane.md)
2. [`../docs/superpowers/specs/2026-05-07-nullclaw-personality-presets-design.md`](../docs/superpowers/specs/2026-05-07-nullclaw-personality-presets-design.md)
