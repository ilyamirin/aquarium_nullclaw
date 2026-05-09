# Control Plane

Aquarium now has a web control plane built on `Django + Unfold`.

Tracked sources:

- Django settings and URL root: [controlplane/core](/Users/ilyagmirin/PycharmProjects/aquarium/controlplane/core)
- domain models, API views, admin views: [controlplane/domain](/Users/ilyagmirin/PycharmProjects/aquarium/controlplane/domain)
- management entrypoint: [manage.py](/Users/ilyagmirin/PycharmProjects/aquarium/manage.py)
- shared orchestration services: [orchestrator/service_layer.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/service_layer.py)
- Django bootstrap helper for CLI reuse: [orchestrator/django.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/django.py)

## Architecture

The runtime-management stack is now split into three layers:

- `controlplane/`
  web operator surface, RBAC boundary, DB models, JSON API, Unfold admin pages
- `orchestrator/service_layer.py`
  shared business logic for runtime lifecycle, limits, diagnostics, secrets, provider catalog, chat, and compose sync
- `orchestrator/cli.py`
  thin local operator adapter over the same service layer

The current direction is now explicitly **agent-first**:

- `Agent` is the primary product object
- `AgentBuildSpec` is the editable recipe
- `Deployment` is the execution record
- `Runtime` remains the internal execution substrate and compatibility layer

Important rule:

- the web control plane does **not** shell out to the CLI
- the CLI does **not** call the HTTP API
- both talk directly to the shared service layer

## State Model

Primary source of truth is now the Django SQLite database:

- `.aquarium/state/controlplane.sqlite3`

Still mirrored for compatibility:

- `.aquarium/state/runtimes.json`
- `.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml`

Why both exist:

- Django DB is the canonical control-plane state for UI/API
- the old JSON state is still mirrored so existing tooling and operational paths do not break during the transition

## Domain Models

Core models:

- `Workspace`
- `Agent`
- `AgentBuildSpec`
- `SkillCatalogEntry`
- `AgentSkillBinding`
- `Secret`
- `AgentSecretBinding`
- `Deployment`
- `Tenant`
- `Plan`
- `RuntimeProfile`
- `Runtime`
- `IntegrationConnection`
- `ProviderConnection`
- `ProviderModel`
- `SkillCatalogEntry`
- `RuntimeSecretRef`
- `RuntimeActionLog`
- `RuntimeDiagnosticSnapshot`
- `RuntimeChatSession`
- `RuntimeChatMessage`

`SkillCatalogEntry` is the schema foundation for the future agent operator skill catalog. It keeps the original local-catalog fields (`key`, `display_name`, `description`, `category`, `source_path`, `compatibility_rules`, `default_enabled`, `status`) and adds the operator-skills trust/dependency contract:

- `skill_type`: `behavior`, `hybrid`, or `executable`
- `source`: `internal`, `nullclaw-registry`, or `github`
- `trust_status`: `internal`, `reviewed`, `quarantine`, or `blocked`
- `source_url`: external review/source pointer, blank for internal skills
- `required_integrations`, `required_secrets`, `required_services`: dependency declarations stored as JSON arrays
- `permissions`: approved Aquarium capability permissions, not shell access
- `entrypoints`: approved Aquarium adapter entrypoint names for executable or hybrid skills

Internal skill entries default to `skill_type=behavior`, `source=internal`, and `trust_status=internal`. External import code must explicitly set external sources to `trust_status=quarantine` before any future review flow enables them.

Curated internal operator skills are tracked source, not database-only seed data:

- package source of truth: [skills](/Users/ilyagmirin/PycharmProjects/aquarium/skills)
- bootstrap loader: [orchestrator/service_layer.py](/Users/ilyagmirin/PycharmProjects/aquarium/orchestrator/service_layer.py)
- API surface: `GET /api/skills/catalog`

Each internal package follows the AgentSkills-style layout:

```text
skills/<skill-key>/
  SKILL.md
  manifest.json
  README.md
```

`SKILL.md` is the agent-facing operator instruction. `manifest.json` is the machine-readable source of truth for display metadata, dependencies, permissions, default-enabled state, and adapter entrypoints. The Django bootstrap path reads `skills/*/manifest.json` and upserts that metadata into `SkillCatalogEntry` through `bootstrap_reference_data()`, so repeated startup/import/migration flows do not create duplicates and catalog/API behavior follows the tracked package manifests. Manifest loading fails fast before any catalog write if required fields are missing, if two packages declare the same `key`, or if manifest-driven fields use the wrong JSON type. Scalar manifest fields (`key`, `display_name`, `description`, `category`, `type`, `source`, `trust_status`) must be strings, `default_enabled` must be a boolean, and dependency/capability fields (`required_integrations`, `required_secrets`, `required_services`, `permissions`, `entrypoints`) must be arrays of strings.

The v1 internal catalog contains:

- `runtime-operator`
- `incident-analyst`
- `log-trace-investigator`
- `litellm-limits-manager`
- `secret-checker`
- `telegram-operator`
- `release-smoke-tester`
- `support-triage`
- `ops-reporter`
- `gitea-operator`
- `kanboard-operator`

Trust model for this catalog:

- internal packages always use `source=internal`, `trust_status=internal`, and `status=active`
- executable skills declare capability permissions such as `runtime_lifecycle`, `diagnostics_read`, `litellm_admin`, `secrets_metadata_read`, `gitea_api`, or `kanboard_api`
- executable skills may use only approved Aquarium adapter entrypoints listed in the catalog metadata
- no v1 internal skill grants arbitrary shell execution, direct host access, raw secret access, or unreviewed downloaded code execution
- integration-specific skills remain visible in the catalog and are disabled by the UI until their declared dependencies are available

Runtime skill selection:

- operator entrypoints: runtime wizard step 3 and the runtime detail `Operator Skills` section
- API catalog: `GET /api/skills/catalog`
- runtime create/update API accepts `skill_keys`
- selected skills are stored in `Runtime.settings`
- stored keys: `skill_stack`, `skill_permissions`, `skill_entrypoints`, and `skill_prompt_sections`
- `skill_stack` preserves operator selection order and removes duplicate keys
- `skill_permissions` and `skill_entrypoints` are derived from reviewed catalog metadata
- `skill_prompt_sections` stores the selected `SKILL.md` instruction bodies for future runtime prompt/adaptor compilation
- dependency status is computed from runtime channels, runtime integration records, runtime secret refs, and platform service availability

Current dependency behavior:

- `controlplane`, `infisical`, `litellm`, and `runtime-gateway` are considered available platform services in the local operator flow
- `monitoring` is available when `monitoring-stack/.env` exists
- integration dependencies such as `telegram`, `search`, `gitea`, and `kanboard` must be present through runtime channels/settings or integration records
- secret dependencies are matched against runtime secret refs by backend secret name
- unavailable skills are shown with concrete missing dependency reasons and cannot be newly selected from the UI
- already-selected skills remain visible on runtime detail with dependency warnings so an operator can remove or repair them

Current runtime profiles:

- `live`
- `probe`
- `limit-probe`
- `playground`
- `custom`

## Bootstrap And Run

Run migrations:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium
make controlplane-migrate
```

Import existing runtime state:

```bash
make controlplane-import-state
```

Create or refresh the local operator:

```bash
make controlplane-bootstrap-operator
```

That creates:

- username: `admin`
- password: `admin`
- email: `admin@aquarium.local`

SSO-compatible entrypoints:

- `LOGIN_URL` now points to `/auth/login/`
- `LOGOUT_REDIRECT_URL` now points to `/auth/logout/`
- `controlplane.domain.auth.AutheliaRemoteUserMiddleware` auto-creates/logs in a staff operator when the configured Authelia header is present
- default header name is `HTTP_REMOTE_USER`
- `AUTHELIA_LOGIN_URL`, `AUTHELIA_LOGOUT_URL`, and `AUTHELIA_HEADER_USER` are environment-overridable

Run the web UI locally:

```bash
make controlplane-run
```

Local endpoint:

- [http://127.0.0.1:15000/admin/](http://127.0.0.1:15000/admin/)

Perimeter bootstrap and local operator entrypoints:

- `make perimeter-bootstrap` writes `perimeter-stack/.env` without rotating existing Authelia secrets on rerun
- if `perimeter-stack/authelia/users_database.yml` is missing, bootstrap creates it once with either:
  - `AUTHELIA_ADMIN_PASSWORD_HASH`
  - `AUTHELIA_ADMIN_PASSWORD`
  - or a one-time generated local admin password printed during bootstrap
- default local public operator URLs are:
  - `https://app.aquarium.local`
  - `https://auth.aquarium.local`
  - `https://grafana.aquarium.local`
  - `https://secrets.aquarium.local`
- local browser automation can also use the perimeter aliases:
  - `https://app.lvh.me`
  - `https://auth.lvh.me`
  - `https://grafana.lvh.me`
  - `https://secrets.lvh.me`
- the containerized perimeter control plane starts through `scripts/controlplane-container-start.sh`, which applies Django migrations before `runserver`

Use `make controlplane-check` for a quick Django health/config check.

## Operator UI

The operator UI is the Django admin styled through Unfold, with a project-specific dark visual system called **Deep Ocean Operator Console**.

Deep Ocean rules:

- agents are the primary product object
- runtimes are shown as infrastructure under agent lifecycle
- `controlplane/templates/admin/operator_base.html` owns the shared shell, tokens, panels, buttons, forms, status pills, choice cards, tables, and responsive rules
- form helpers use the `op-help` pattern: short visible text directly under labels, not hidden tooltips
- important caveats use `op-field-note`, which is still compact but more visually prominent than normal helper copy
- normal `GET` pages must remain read-only and render cached/persisted state
- live diagnostics, secret verification, smoke checks, runtime probes, and destructive actions must stay explicit operator actions
- UI templates must preserve existing POST field names and API contracts
- secrets must render only as masked labels, backend references, or write-only inputs
- the interface should stay terse: short labels, large sans-serif type, dark panels, clear state color, and no decorative motion that hides operational meaning

Current pages and flows:

- Command Deck at `/admin/`
- Create Agent wizard at `/admin/agents/new/`
- Agent Studio at `/admin/agents/<agent_slug>/`
- Workspace Vault at `/admin/vault/`
- Runtime list and custom runtime detail
- Runtime wizard with staged setup flow
- Runtime diagnostics page
- Runtime chat page
- Provider connections
- Model catalog
- Integrations
- Secrets status
- Runtime action log

The important operator decision is now explicit:

- raw Django model forms are secondary
- the main product surface is now agent-first
- the dedicated runtime page at `/admin/runtimes/<runtime_id>/` remains available as a secondary execution/diagnostics surface during migration

Agent-first surfaces:

- `/admin/` is the agents-first **Command Deck**
- `/admin/` shows the inline Agent Composer, Agent Fleet cards, runtime infrastructure, and recent actions
- `/admin/agents/new/` creates a **draft** only through the full Agent Builder route
- `/admin/agents/<slug>/` is the configuration-first Agent Studio cockpit
- launch and stop are explicit actions from Agent Studio
- internal test chat still routes through the existing runtime chat page when a deployment exists
- launch materializes the final `AgentBuildSpec.personality_prompt` plus selected skill descriptions into the runtime system prompt
- the generated runtime config defines a named NullClaw agent profile using the runtime id, so internal chat can invoke the correct profile with `nullclaw agent --agent <runtime-id>`

Agent Builder personality presets:

- the static catalog lives in `controlplane/domain/personality_presets.py`
- the current seven presets are `Mara / The Field Operator`, `Viktor / The Hard Reviewer`, `Noa / The Scout`, `Sana / The Diplomat`, `Kiro / The Builder`, `Elin / The Mentor`, and `Rook / The Wild Card`
- `_agent_builder_context` passes `personality_presets` and a safe JSON prompt map to both `/admin/` and `/admin/agents/new/`
- the shared builder partial `controlplane/templates/admin/_agent_builder_form.html` renders a hybrid Agent Composer with `Identity`, `Personality`, `Model`, `Channels`, `Skills`, `Limits`, and `Secrets` sections
- technical fields in the builder carry short helpers explaining operational impact, for example `Slug` as the permanent technical name used in URLs/runtime ids/Docker/Infisical/local folders, `Gateway Port`, LiteLLM budget/RPM/TPM, and Telegram secret bindings
- personality presets render as homogeneous `op-choice-card` radio cards together with the `Custom Prompt` card
- selecting a preset hides the `Personality Prompt` textarea and uses that preset text at launch
- selecting `Custom Prompt` opens the textarea and makes it the submitted system prompt source; first selection starts from an empty custom prompt unless the operator already typed one
- preset text is inspectable through `Review prompt text`; the disclosure is hidden in `Custom Prompt` mode to avoid implying that a generated prompt exists
- avoid ambiguous labels such as `View generated prompt`
- ordered skills render as capability cards with trust/type badges
- each card is a creation-time helper showing display name, subtitle, short description, and `Best for`
- selecting a card uses local JavaScript to fill the textarea and update the generated prompt preview
- long preset prompts are hidden behind the `Review prompt text` disclosure so the page stays compact
- editing the textarea keeps `Custom Prompt` selected
- switching from `Custom Prompt` back to a preset asks for browser confirmation before replacing typed custom text
- JavaScript is progressive enhancement only; if it fails, the textarea remains usable and remains the submitted source of truth
- v1 does not submit or store a preset ID; only the final `personality_prompt` textarea value is saved on the build spec
- because only the final prompt text is persisted, future edits to the static preset catalog do not mutate existing agents

That runtime page aggregates:

- overview
- lifecycle controls
- limits and key actions
- channels and integrations
- runtime and integration secrets
- diagnostics summary and snippets
- recent actions
- recent chat sessions

Runtime UI convention:

- runtime pages use `op-runtime-cockpit`
- Runtime Wizard uses `op-pressure-rail` for staged setup
- Runtime Wizard fields carry the same `op-help` convention because it exposes lower-level infrastructure terms such as runtime id, tenant, plan, provider model, and channel/tool toggles
- Runtime Detail is the infrastructure cockpit for lifecycle, LiteLLM, secrets, integrations, diagnostics, and recent events
- Runtime Diagnostics shows cached diagnostic summaries first
- Runtime Chat is an internal operator/debug channel, not a user-facing chat product

Current runtime actions from admin:

- start
- stop
- restart via recreate
- rotate LiteLLM key
- sync limits
- run smoke test
- refresh diagnostics

Runtime apply contract:

- `Update limits` now persists DB state and immediately applies the LiteLLM virtual-key update
- changing the runtime model alias also rewrites the runtime bootstrap env and recreates the runtime
- saving runtime secrets recreates the runtime so Infisical-backed process env and rendered config are refreshed
- saving runtime-scoped integrations recreates the runtime so channel and search settings take effect without a separate operator step
- `Sync limits` remains available as a manual repair action when operators want to re-push the current LiteLLM limit state

The dedicated operator sections outside the runtime page are:

- `/admin/`
- `/admin/providers/`
- `/admin/models/`
- `/admin/integrations/`
- `/admin/secrets/`

Configuration page convention:

- providers, models, integrations, and secrets use `op-config-deck`
- each configuration page starts with a short `op-hero op-panel`
- existing records stay in compact dark tables or panels
- create/update/test/delete forms keep existing action names and field names
- write-only secret inputs must never echo stored secret values

Navigation behavior:

- all operator pages share one Unfold-native layout and header navigation
- Unfold sidebar now links directly to the operator pages
- raw model-admin pages are hidden from the main menu/index
- raw `/admin/domain/...` model routes are redirected back into operator pages
- `/admin/dashboard/` and `/admin/runtimes/` remain only as compatibility redirects back to `/admin/`

Current admin root behavior:

- `/admin/` is the single operator Command Deck
- it contains direct links to the working configuration sections
- it contains Agent Fleet cards before the runtime infrastructure table
- it contains the runtime infrastructure table with direct links to each runtime's detail, diagnostics, and chat
- browser titles are standardized to `... | Aquarium Control Plane`

Browser smoke after UI changes:

- `/admin/`
- `/admin/agents/new/`
- `/admin/vault/`
- `/admin/runtime-wizard/`
- `/admin/providers/`
- `/admin/models/`
- `/admin/integrations/`
- `/admin/secrets/`
- at least one runtime detail, diagnostics, and chat page when a runtime exists

## Control API

The JSON API is operator-first and lives under `/api/`.

Implemented resource groups:

- `/api/agents`
- `/api/agents/<id>`
- `/api/agents/<id>/launch`
- `/api/agents/<id>/stop`
- `/api/skills/catalog`
- `/api/workspace/secrets`
- `/api/runtimes`
- `/api/runtimes/<id>/limits`
- `/api/runtimes/<id>/keys/<action>`
- `/api/runtimes/<id>/diagnostics/<kind>`
- `/api/runtimes/<id>/secrets`
- `/api/runtimes/<id>/chat/sessions`
- `/api/providers/catalog`
- `/api/provider-connections`
- `/api/integrations`
- `/api/models/catalog`
- `/api/models/custom`
- `/api/runtime-wizard/*`
- `/api/secrets/integrations`
- `/api/secrets/provider-connections`

Security posture:

- login required
- staff-only
- anonymous requests are redirected to `/auth/login/`
- non-staff authenticated users receive `403`

Workspace/agent contract:

- single operator / single workspace for v1
- workspace secrets are stored in the current secret backend and surfaced as write-only metadata in the UI/API
- agent creation stores config first; launch resolves secret bindings and compiles them into runtime inputs
- personality presets affect only draft creation UX by pre-filling `AgentBuildSpec.personality_prompt`; they are not runtime dependencies and do not change launch semantics

## Diagnostics Model

The control plane does not replace Grafana/Loki/Tempo/Mimir.

It aggregates and links:

- runtime health summary
- generated config view
- recent Loki query result
- recent Tempo trace search result
- recent Mimir probe query result
- secret verification status

Important safety rule:

- generated config returned through the control plane masks token-, password-, secret-, and `api_key`-like values before rendering or returning them
- runtime and provider secret APIs expose metadata and masked labels only; they do not return secret values

Current diagnostics UI policy:

- show summary first
- show short log/trace/metric snippets
- link out to Grafana/Loki/Tempo/Mimir for full exploration
- keep raw payloads only as secondary expandable details

Important read/write rule:

- `GET` operator pages now read cached state only
- admin home, runtime detail, and diagnostics summary do not refresh diagnostics or verify secrets during page render
- live diagnostics refresh remains an explicit action/API path
- this change exists to avoid SQLite lock contention from ordinary UI navigation

## Runtime Chat

The built-in chat is a minimal operator/debug surface.

Current behavior:

- one runtime at a time
- persisted session and message history in Django DB
- buffered execution through `docker compose run --rm agent-<runtime-id> agent -m "<message>"`
- response stored back in `RuntimeChatMessage`

This is intentionally not a full `OpenWebUI` replacement.

## SQLite Notes

The control plane still uses SQLite for the local/demo repository.

Current hardening:

- SQLite connection timeout is set to 20 seconds
- a connection hook applies `PRAGMA journal_mode=WAL`
- a connection hook applies `PRAGMA busy_timeout=20000`

This is a safety improvement, not the primary fix for lock issues.
The primary fix is that read-only UI/API paths no longer perform background reconciliation or diagnostics writes.

## Providers, Models, And Secrets

Provider connections are managed as typed records, not as raw Infisical browsing.

Current behavior:

- provider connection upsert writes provider API secret material into `litellm-core`
- provider/model changes regenerate `litellm-stack/config.yaml`
- provider secret list endpoints expose metadata and masked labels, not raw secret values
- runtime budget, RPM, and TPM settings are LiteLLM-only controls; they do not rely on a restrictive NullClaw-side rate cap

Typed secret coverage in `v1` includes:

- provider API keys
- provider base URLs
- Telegram bot credentials
- Telegram allowlist

The render pipeline is also prepared for:

- Slack
- Mattermost
- HTTP/search settings

## Import And Backfill

Importing mirrored runtime state now does two things:

1. loads `Runtime`, `Tenant`, `Plan`, and profile relationships into the Django DB
2. backfills related operator records so the admin does not look empty

Backfilled records include when possible:

- `IntegrationConnection`
- `RuntimeSecretRef`
- `RuntimeDiagnosticSnapshot`
- initial `RuntimeActionLog`
- platform `ProviderConnection`
- platform-default `ProviderModel`

Current platform baseline backfill:

- `platform-openrouter`
- model alias `openai/qwen/qwen3.6-plus`

These are reconstructed from the existing LiteLLM wrapper state so `Providers` and `Models` are not empty on migrated installations.

Manual backfill command:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium
.venv/bin/python manage.py backfill_runtime_related
```

Or for one runtime:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium
.venv/bin/python manage.py backfill_runtime_related --runtime-id test-nullclaw
```

## CLI Compatibility

The existing CLI still works and now runs through the same service layer as the web UI/API.

Confirmed commands after the refactor:

- `.venv/bin/orchestrator runtime list`
- `.venv/bin/orchestrator runtime status --id test-nullclaw`
- `.venv/bin/orchestrator runtime limits --id probe`

## Tests

Current automated control-plane coverage:

- config masking for generated runtime config
- import from mirrored JSON state into Django DB
- operator-only API access
- runtime list and limits endpoints
- runtime wizard validation and create flow
- masked provider secret listing
- Unfold admin dashboard and diagnostics page rendering

Current operator UI layout contract:

- operator pages intentionally override the Unfold `#main.bg-white` wrapper so the Aquarium dark background reaches the full viewport
- agent builder choice cards must not use percentage `min-height`; grid stretch is enough, and percentage min-height can make cards overflow their step panels
- layout smoke checks should verify no horizontal scroll, no sibling section overlap, and no child overflow inside `.op-composer-section`

Primary test command:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium
.venv/bin/pytest
```
