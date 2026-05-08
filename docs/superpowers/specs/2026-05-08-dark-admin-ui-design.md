# Deep Ocean Operator Console Design

Date: 2026-05-08
Branch: `codex/dark-admin-ui`
Worktree: `.worktrees/dark-admin-ui`

## Goal

Redesign the Aquarium control-plane admin UI as a dark, agents-first operator console for platform administrators.

This is not a public customer portal and not a generic Django admin skin. It is a cockpit for building, launching, observing, and repairing NullClaw-like agents and their supporting runtime infrastructure.

## Design Direction

Chosen direction: **Deep Ocean Console**.

The interface should feel like a dark undersea lab control room:

- deep blue-black background, not pure black
- subtle oceanic radial gradients, haze, and grid/noise texture
- glass/metal panels with thin teal/cyan borders
- strong teal/cyan primary actions
- pale green for healthy/live states
- amber for warning states
- coral/red for dangerous or failed states
- large sans-serif typography, with confident spacing and short labels
- high-fancy treatment where it supports orientation: glow, status pulse, gradient borders, animated reveal

The UI must stay lapidary and operational. Fancy elements are allowed only when they clarify state, hierarchy, or action priority.

## Scope

Redesign the full operator surface:

- Home / Command Deck
- Agent Builder
- Agent Studio
- Workspace Vault
- Runtime Wizard
- Runtime Detail
- Runtime Diagnostics
- Runtime Chat
- Providers
- Models
- Integrations
- Secrets

The first implementation pass is allowed to change presentation structure, templates, CSS, and minimal page-local JavaScript.

Out of scope:

- backend model changes
- service-layer behavior changes
- API contract changes
- upstream `nullclaw/` changes
- SPA rewrite
- public customer-facing UI

## Information Architecture

The UI is **agents-first**.

Runtimes, secrets, LiteLLM limits, provider connections, diagnostics, and monitoring are infrastructure under the agent lifecycle.

### Home / Command Deck

The home page becomes the main operator command deck:

- top status strip for agents, running deployments, unhealthy items, provider state, secret state, monitoring
- prominent `Create Agent` command card
- agent inventory as cards, not a heavy table-first screen
- runtime inventory below as infrastructure layer
- recent actions as compact event feed
- quick links to Vault, Providers, Models, Integrations, Secrets, Grafana, Infisical

### Agent Builder

Agent creation uses a hybrid composer:

- one primary page for the normal path
- sections for Identity, Personality, Model, Channels, Skills, Limits, Secrets
- personality presets shown as expressive choice cards
- skills shown as capability cards with trust and dependency status
- secrets shown as bindings, not raw password fields
- draft creation and runtime launch remain explicit separate concepts

### Agent Studio

Agent Studio is the cockpit for one agent:

- identity and current status
- current build spec
- selected personality
- model and LiteLLM limits
- channel and secret bindings
- current deployment/runtime binding
- actions such as launch, stop, diagnostics, chat

### Runtime Pages

Runtime pages are infrastructure views:

- Runtime Wizard remains step-driven, compact, and secondary to Agent Builder
- Runtime Detail shows lifecycle, health, model, LiteLLM key metadata, limits, secrets, and service actions
- Diagnostics and Chat remain explicit operator tools

Runtime pages must preserve the existing read/write separation:

- normal GET views show cached/persisted state
- live checks happen only through explicit actions such as Probe, Refresh Diagnostics, Test Secret

### Configuration Pages

Providers, Models, Integrations, Secrets, and Vault use the same dark panel language:

- compact tables
- clear status pills
- action groups on the right
- short copy
- no white default admin surfaces

## Component Model

The redesign should be centralized through `controlplane/templates/admin/operator_base.html`.

Primary components:

- `op-shell`: global layout width, spacing, dark background, page reveal
- `op-topbar`: Aquarium identity, perimeter/control status, quick external links
- `op-nav`: primary navigation
- `op-hero`: page title and short operational summary
- `op-command-card`: large primary action card
- `op-panel`: glass/metal content panel
- `op-metric`: compact count/status/budget indicator
- `op-status-pill`: status badge with text and color
- `op-data-table`: compact dark table
- `op-composer-section`: form section for agent/runtime composition
- `op-choice-card`: selectable personality, skill, role, or channel card
- `op-event-feed`: recent action and diagnostic event list

Existing `op-*` names may be reused or replaced, but the resulting system should be coherent and reusable across all operator pages.

## Visual Rules

Typography:

- sans-serif only
- large page titles, roughly 32-44px
- body and form text around 15-17px
- concise labels
- help text only where it prevents operator mistakes

Layout:

- dense enough for operations, but not cramped
- prefer cards/panels over large white tables
- preserve mobile/tablet fallback with single-column stacking
- keep primary actions visually obvious

Color and status:

- healthy/live: pale green
- warning/degraded: amber
- error/danger: coral/red
- neutral: blue-gray
- primary action: teal/cyan

Motion:

- subtle page-load reveal
- hover lift/glow on command cards
- status pulse only for live/active states
- no distracting animation loops in dense data areas

## Interaction Behavior

Agent Builder:

- selecting a personality preset updates the prompt preview and textarea
- changing an already customized prompt must still protect against accidental overwrite
- selected cards must be visibly selected without relying only on color
- draft creation remains the default submit action

Runtime Wizard:

- steps remain explicit
- destructive or expensive actions are visually separated
- validation/backfill actions remain clear

Diagnostics:

- cached summaries render by default
- explicit live actions remain separate and visually labeled

Errors:

- show short alert panels
- explain the operational cause when known
- examples: Infisical unreachable, missing runtime key, LiteLLM rejected request, Telegram secret missing
- never leak secrets into visible error text

## Testing Strategy

Automated tests:

- keep existing Django tests passing
- add or update HTML assertions only where page structure changes affect required controls
- ensure forms preserve current field names and submit actions

Manual/browser smoke:

- open Home / Command Deck
- open Agent Builder
- choose personality preset and verify prompt behavior
- open Agent Studio
- open Workspace Vault
- open Runtime Wizard
- open Runtime Detail
- open Runtime Diagnostics
- open Runtime Chat
- open Providers, Models, Integrations, Secrets
- verify no browser console errors
- verify dark theme applies consistently

Regression constraints:

- no writes on normal GET views
- no upstream `nullclaw/` edits
- no secrets in rendered HTML except masked labels
- existing POST/API contracts remain intact

## Implementation Notes

Recommended implementation sequence:

1. Build the new visual system in `operator_base.html`.
2. Redesign Home as the Command Deck.
3. Redesign `_agent_builder_form.html`, `agent_wizard.html`, and `agent_studio.html`.
4. Redesign Runtime Wizard, Runtime Detail, Diagnostics, and Chat.
5. Redesign configuration pages.
6. Update tests and knowledge docs.
7. Run Django tests, lint, and browser smoke.

## Success Criteria

The redesign is successful when:

- the UI reads as one coherent dark operator console
- agents are clearly the primary product object
- runtimes are visible as infrastructure, not the top-level product
- all current operator actions remain available
- forms still submit through existing contracts
- status, health, limits, secrets, and diagnostics are easier to scan
- the interface feels bold and memorable without harming operator clarity
