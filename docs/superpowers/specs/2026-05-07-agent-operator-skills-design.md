# Agent Operator Skills Design

Date: 2026-05-07

## Summary

Aquarium needs a curated pack of selectable agent skills for AI agent platform and operator assistants. Operators should be able to enable skills with checkboxes while creating or editing an agent. Skills may be behavioral, hybrid, or executable, but executable behavior must be constrained to approved platform adapters instead of arbitrary third-party code execution.

The first version should support a trusted internal skill catalog, plus a quarantine and review path for external NullClaw-compatible skills. If a suitable NullClaw-recommended skill exists, Aquarium should prefer it. If not, Aquarium should provide an internal skill with the same AgentSkills-style packaging model.

## Current Context

The control plane already has the required foundation:

- `SkillCatalogEntry` stores skill metadata.
- `AgentSkillBinding` binds selected skills to an agent build spec.
- `/api/skills/catalog` exposes enabled catalog entries.
- The agent wizard already renders skill checkboxes.
- Launching an agent compiles selected skills into the runtime settings and prompt contract.

The missing product layer is a trustworthy skill catalog, dependency-aware UI states, and a safe execution model for skills that need real platform actions.

## Skill Types

Aquarium will classify skills into three types:

- `behavior`: prompt and workflow guidance only. No secrets, integrations, or executable capability required.
- `hybrid`: prompt guidance plus optional access to approved platform capabilities when dependencies are configured.
- `executable`: a skill that can perform actions, but only through Aquarium-approved adapters and permissions.

Executable skills must not run arbitrary shell commands or unreviewed downloaded code in v1.

## Trust Model

Skill source and trust status are separate.

Supported sources:

- `internal`: authored and shipped in this repository.
- `nullclaw-registry`: imported from a NullClaw-compatible or NullClaw-recommended source.
- `github`: imported from a GitHub repository.

Supported trust states:

- `internal`: trusted because the skill ships with Aquarium.
- `reviewed`: externally sourced but approved by an operator.
- `quarantine`: imported but not enabled for agents.
- `blocked`: rejected and unavailable for selection.

External imports must land in `quarantine`. An operator must review metadata, instructions, dependencies, requested permissions, and source URL before marking the skill `reviewed`.

## Permission Model

Executable skills receive capability permissions, not raw system access.

Initial permissions:

- `runtime_read`: read runtime metadata and status.
- `runtime_lifecycle`: start, stop, restart, recreate, or smoke-test runtimes.
- `diagnostics_read`: query normalized diagnostics, logs, traces, and metrics.
- `litellm_admin`: inspect keys, budgets, RPM/TPM limits, and limit failures.
- `secrets_metadata_read`: inspect secret coverage and missing-secret status without exposing secret values.
- `integration_test`: run typed integration checks.
- `gitea_api`: call the configured Gitea adapter.
- `kanboard_api`: call the configured Kanboard adapter.
- `search_api`: call the configured search adapter.

The runtime should only expose actions for permissions explicitly granted by selected skills and enabled by the operator.

## Dependency Model

Every skill can declare dependencies:

- required integrations, such as `telegram`, `gitea`, `kanboard`, or `search`
- required secrets, such as `TELEGRAM_BOT_TOKEN`, `GITEA_TOKEN`, or `KANBOARD_PASSWORD`
- required platform services, such as `monitoring`, `litellm`, or `infisical`
- required permissions, such as `diagnostics_read` or `runtime_lifecycle`

The UI should show unavailable skills as disabled with a concrete reason. For example, `gitea-operator` should be visible but disabled until a Gitea integration and token exist.

## Initial Skill Catalog

The v1 catalog should contain 11 operator-focused skills.

| Key | Type | Purpose | Requirements |
| --- | --- | --- | --- |
| `runtime-operator` | executable/internal | Start, stop, restart, inspect, and smoke-test runtimes. | control API, `runtime_lifecycle` |
| `incident-analyst` | hybrid/internal | Explain runtime failures from symptoms, status, diagnostics, and recent actions. | optional monitoring, `diagnostics_read` |
| `log-trace-investigator` | executable/internal | Query Loki, Tempo, and Mimir and summarize likely causes. | monitoring, `diagnostics_read` |
| `litellm-limits-manager` | executable/internal | Inspect budgets, RPM/TPM limits, key state, and limit-related failures. | LiteLLM, `litellm_admin` |
| `secret-checker` | executable/internal | Check missing secrets and secret coverage without exposing raw values. | Infisical metadata, `secrets_metadata_read` |
| `telegram-operator` | hybrid/internal | Diagnose and shape behavior for Telegram-facing runtimes. | Telegram integration |
| `release-smoke-tester` | executable/internal | Run post-create and post-update smoke checks. | runtime gateway, `runtime_read` |
| `support-triage` | behavior/internal | Classify operator or customer requests and suggest next steps. | none |
| `ops-reporter` | behavior/internal | Produce concise status updates, summaries, and action reports. | none |
| `gitea-operator` | executable/external-or-internal | Work with repositories, issues, and PR-style workflows. | Gitea integration, `gitea_api` |
| `kanboard-operator` | executable/external-or-internal | Work with Kanboard projects, tasks, columns, and status updates. | Kanboard integration, `kanboard_api` |

Optional follow-up skill:

- `web-researcher`: search and summarize external information through the configured search provider.

## Skill Package Format

Aquarium should use an AgentSkills-style package format:

```text
skills/<skill-key>/
  SKILL.md
  manifest.json
  README.md
  adapters/
```

`SKILL.md` contains the agent-facing instructions.

`manifest.json` contains machine-readable metadata:

```json
{
  "key": "runtime-operator",
  "display_name": "Runtime Operator",
  "type": "executable",
  "source": "internal",
  "trust_status": "internal",
  "required_integrations": [],
  "required_secrets": [],
  "required_services": ["controlplane"],
  "permissions": ["runtime_read", "runtime_lifecycle"],
  "entrypoints": ["runtime.status", "runtime.restart", "runtime.smoke_test"]
}
```

Adapters are internal Aquarium service-layer bindings, not arbitrary external scripts.

## UI Behavior

The agent wizard and agent studio should render skills as checkbox cards grouped by category:

- Runtime Operations
- Diagnostics
- Limits and Secrets
- Channels and Integrations
- Operator Workflow

Each card should show:

- display name
- short description
- type badge
- trust badge
- dependency status
- required integrations and permissions

Disabled skills remain visible with the reason they cannot be enabled.

## Runtime Behavior

When an agent launches:

1. The selected skill list is stored on the build spec through `AgentSkillBinding`.
2. Behavior instructions are compiled into the agent prompt.
3. Executable permissions are compiled into runtime settings.
4. Only approved adapters for the selected skills are exposed to the runtime.
5. Runtime settings retain the selected `skill_stack` for diagnostics and audit.

If an executable skill dependency becomes unavailable after launch, the skill should degrade with an explicit error instead of silently attempting the action.

## External Import Flow

The import flow for external skills:

1. Operator enters a NullClaw-compatible source or GitHub URL.
2. Aquarium fetches metadata and package files.
3. The skill is stored as `quarantine`.
4. Aquarium displays source, files, requested permissions, dependencies, and warnings.
5. Operator approves or blocks the skill.
6. Approved skills become selectable if dependencies are satisfied.

The default v1 implementation can omit package fetching if it records the source URL and manual review metadata. The trust model should still be present from the start.

## Error Handling

Common failures should be explicit:

- Missing integration: skill is disabled and the UI links to the integration setup.
- Missing secret: skill is disabled and the UI links to secrets management.
- Monitoring unavailable: diagnostics skills run in degraded mode and show which backend is unreachable.
- Permission denied: executable adapter returns a structured authorization error.
- External source unavailable: import remains failed with the source URL and raw error.
- Unreviewed external skill: skill remains in quarantine and cannot be selected.

## Testing

Design acceptance tests:

- catalog bootstraps all internal skills
- `/api/skills/catalog` returns type, trust status, dependencies, and permissions
- agent wizard disables unavailable skills with reasons
- selected behavior skills compile into the prompt
- selected executable skills compile into allowed runtime permissions
- unavailable executable adapters return structured errors
- external import creates a quarantined skill
- quarantined skills cannot be selected
- reviewed external skills can be selected only when dependencies are satisfied
- skill metadata never exposes secret values

## Scope Boundaries

In scope for v1:

- curated internal skill pack
- external import metadata and quarantine model
- dependency-aware checkbox UI
- permission model for approved adapters
- prompt compilation for behavior and hybrid skills

Out of scope for v1:

- arbitrary third-party code execution
- marketplace-like one-click install
- user-authored executable scripts
- automatic trust decisions based only on GitHub stars or repository popularity
- exposing raw Infisical secrets to skills

## Open Decisions Closed By This Spec

- Skill catalog target: AI agent platform/operator assistant.
- First version style: hybrid catalog with executable skills.
- External source policy: external skills allowed only through quarantine and review.
- Fallback policy: internal skills are acceptable when no trusted NullClaw-recommended skill exists.
- Execution policy: executable skills use Aquarium adapters, not arbitrary shell access.
