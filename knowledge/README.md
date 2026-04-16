# Knowledge Base

This directory is the project memory for our local NullClaw hosting wrapper.

Read this first when returning to the project after a break.

## Layout

- [install-and-setup.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/install-and-setup.md)
  End-to-end bootstrap document for prerequisites, `.venv`, hooks, Infisical, orchestrator install, and the first runtime creation.
- [orchestrator.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/orchestrator.md)
  Primary control-plane document: local state layout, generated compose, CLI commands, and runtime lifecycle rules.
- [administration.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/administration.md)
  Operator runbook for health checks, logs, restarts, rotations, isolation checks, and recovery.
- [infisical-env-injection.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/infisical-env-injection.md)
  Centralized secret model, project-per-runtime isolation, service-token auth, and runtime env injection flow.
- [nullclaw-overview.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/nullclaw-overview.md)
  What NullClaw is, what parts of upstream we use, and why the current stack is shaped this way.
- [nullclaw-config.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/nullclaw-config.md)
  Environment variables, generated config structure, security defaults, and runtime integration decisions.
- [nullclaw-operations.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/nullclaw-operations.md)
  How to start Infisical, create runtimes, inspect health, view logs, and operate the services.
- [nullclaw-testing.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/nullclaw-testing.md)
  Smoke tests, Telegram checks, isolation proof, and known gaps.
- [git-security.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/git-security.md)
  Git repo layout, ignore rules, hook workflow, and scanner rationale.

## Repository Map

- Upstream runtime source: [nullclaw](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw)
- Python control plane: [orchestrator](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator)
- Generated local runtime state: `.aquarium/`
- Secrets backend: [infisical-stack](/Users/ilyagmirin/PycharmProjects/aquarium/infisical-stack)
- Legacy/manual wrappers: [nullclaw-stack](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw-stack), [nullclaw-probe-stack](/Users/ilyagmirin/PycharmProjects/aquarium/nullclaw-probe-stack)

Compose project names:

- `aquarium-nullclaw-runtimes`
- `aquarium-infisical`
- legacy/manual only: `aquarium-nullclaw`, `aquarium-nullclaw-probe`

## Start Here

If you want to run the project from scratch, use this order:

1. [install-and-setup.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/install-and-setup.md)
2. [orchestrator.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/orchestrator.md)
3. [administration.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/administration.md)
4. [infisical-env-injection.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/infisical-env-injection.md)
5. [nullclaw-config.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/nullclaw-config.md)
6. [nullclaw-operations.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/nullclaw-operations.md)
7. [nullclaw-testing.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/nullclaw-testing.md)
8. [git-security.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/git-security.md)

If you want the architectural context first, start with:

1. [nullclaw-overview.md](/Users/ilyagmirin/PycharmProjects/aquarium/knowledge/nullclaw-overview.md)
