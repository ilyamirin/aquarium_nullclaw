# Aquarium Agent Cloud V1 Design

Date: 2026-05-07
Status: Approved design draft
Scope: Product and platform architecture for turning Aquarium into a single-operator cloud for building and running agents

## 1. Purpose

Aquarium should evolve from a runtime-oriented control plane into an agent-first cloud platform.

The v1 goal is not multi-tenant SaaS. The v1 goal is a single operator workspace where one authenticated user can:

- sign in through Authelia SSO
- create an agent in a UI
- define the agent personality
- select ordered skills from a curated local catalog
- bind or create secrets inline
- choose a model and full runtime build spec
- save the agent as a draft
- explicitly launch the agent
- interact with it primarily through Telegram
- use a simple internal channel for smoke tests and debugging

The key architectural principle is:

- `Agent` is the main product object
- `Runtime` is an internal execution artifact

## 2. Product Definition

Aquarium v1 becomes a single-operator cloud for agents.

The main user-facing object is `Agent`.

An agent is a configuration object that defines:

- name
- description
- personality prompt
- ordered skill stack
- bound secrets
- model selection
- runtime behavior
- environment profile
- startup policy
- observability profile
- Telegram-first channel configuration

Users do not create runtimes directly.
Users create and edit agents, then press `Launch`.
Launch produces a deployment, and the deployment materializes into a runtime.

## 3. Non-Goals for V1

The following are explicitly out of scope for v1:

- multi-tenant SaaS isolation
- organization/team membership workflows
- arbitrary user-uploaded skills
- public skill marketplace
- rich persona layer composition
- agent version publishing workflows
- rollback/release management
- multiple runtime template families
- external channel parity across many channels

This keeps v1 focused on one strong path rather than a diluted platform shell.

## 4. Identity and Secrets

## 4.1 Identity

Authelia becomes the SSO boundary for Aquarium.

Requirements:

- the main UI authenticates through Authelia
- Aquarium derives the operator identity from the authenticated Authelia session
- standalone Django-native login is no longer the primary product auth flow

Because v1 is a single operator workspace, the identity model stays intentionally light:

- one operator
- one workspace
- no org invites
- no membership table required for v1 product UX

The system may still keep an explicit workspace object in the data model so the platform can grow later without rewriting its core shape.

## 4.2 Secrets

Authelia handles authentication, not secret storage.

If the current secret backend is still required as the storage and injection system, Aquarium should keep it for v1 rather than forcing a risky replacement.

Product contract:

- the user sees a workspace-vault style secret experience
- secrets can be created inline while building an agent
- secrets can also be reused across agents
- the UI should remain write-only for sensitive values wherever possible

Trust boundary rules:

- provider master credentials must not leak into generic runtime scopes
- agent deployments receive only the secrets they actually need
- secret bindings are attached by reference and resolved at launch time

Conceptually:

- Authelia answers `who are you`
- Aquarium answers `what agents, deployments, and secret references exist in your workspace`
- the secret backend answers `how secrets are stored and injected`

## 5. Main Product Surfaces

## 5.1 Agent Home

The home page becomes an agent list rather than a runtime inventory.

Each agent row should show:

- name
- status: `draft`, `ready`, `launching`, `running`, `stopped`, `degraded`, `error`
- primary channel
- selected model
- last launch time
- last interaction time
- quick actions: open, launch, stop, relaunch

This page is the main operator workspace dashboard.

## 5.2 Create Agent Wizard

The wizard is optimized for quick first success.

Recommended steps:

1. Identity
   - name
   - short description
2. Personality
   - single main system prompt field
3. Model and runtime
   - model selection
   - full build spec fields required in v1
4. Secrets and channel
   - bind existing secrets
   - create new secrets inline
   - configure Telegram-first channel setup
5. Skills
   - choose from curated local catalog
   - define explicit order
6. Review
   - validate and create draft

Important product rule:

- `Create Agent` creates a draft only
- it does not launch automatically

## 5.3 Agent Studio

Agent Studio is the center of the product.

It is configuration-first, not runtime-first.

Primary sections:

- Overview
- Personality
- Skills
- Secrets
- Build Spec
- Channel
- Launch Controls
- Internal Test
- Diagnostics

Expected behavior:

- the left-to-right mental model is `edit -> validate -> launch`
- diagnostics and execution details exist, but they do not dominate the page identity

## 5.4 Workspace Vault

There should be a dedicated secrets area outside the builder too.

It should support:

- list secrets
- create secret metadata
- edit bindings/labels where appropriate
- inspect secret usage
- rotate and rebind

This supports the inline secret UX without forcing all secret operations into a single massive form.

## 5.5 Deployments and Diagnostics

Deployment and runtime views remain present, but secondary.

They are for:

- launch state
- logs
- health
- recent failures
- debugging and support

The product should not drift back into runtime-first language.
Users inspect deployments because they belong to agents.

## 6. Core Data Model

## 6.1 Workspace

Even in a single-operator v1, `Workspace` should exist explicitly.

Suggested fields:

- `id`
- `authelia_subject`
- `display_name`
- `created_at`
- `updated_at`

## 6.2 Agent

This is the main product object.

Suggested fields:

- `id`
- `workspace_id`
- `name`
- `slug`
- `description`
- `status`
- `current_build_spec_id`
- `current_deployment_id`
- `primary_channel`
- `created_at`
- `updated_at`
- `last_launched_at`
- `last_interaction_at`

Suggested status values:

- `draft`
- `ready`
- `launching`
- `running`
- `stopped`
- `degraded`
- `error`

## 6.3 AgentBuildSpec

This is the full editable recipe for the agent.

Suggested fields:

- `id`
- `agent_id`
- `personality_prompt`
- `model_alias`
- `runtime_template`
- `environment_profile`
- `startup_policy`
- `observability_profile`
- `autonomy_limits`
- `safety_limits`
- `channel_config`
- `build_state`
- `created_at`
- `updated_at`

For v1, `runtime_template` should exist in the schema even if only one generic runtime template is supported.

## 6.4 SkillCatalogEntry

This represents the curated local skill catalog.

Suggested fields:

- `id`
- `key`
- `display_name`
- `description`
- `category`
- `source_path`
- `compatibility_rules`
- `default_enabled`
- `status`

## 6.5 AgentSkillBinding

Because skill order matters, skills must be modeled as explicit bindings rather than unordered tags.

Suggested fields:

- `id`
- `build_spec_id`
- `skill_id`
- `position`
- `enabled`

This allows Aquarium to construct a deterministic instruction stack.

## 6.6 Secret

Workspace-scoped secret metadata.

Suggested fields:

- `id`
- `workspace_id`
- `kind`
- `name`
- `backend_ref`
- `usage_scope`
- `created_at`
- `updated_at`

## 6.7 AgentSecretBinding

A secret object and its use inside an agent are different things, so bindings should be explicit.

Suggested fields:

- `id`
- `build_spec_id`
- `secret_id`
- `mount_key`
- `logical_role`
- `required`

## 6.8 Deployment

This is the bridge between product object and execution event.

Suggested fields:

- `id`
- `agent_id`
- `build_spec_id`
- `status`
- `runtime_ref`
- `launched_at`
- `stopped_at`
- `last_error`

Suggested deployment status values:

- `pending`
- `launching`
- `running`
- `stopped`
- `failed`

## 6.9 Runtime

Runtime remains a real execution concept in the orchestrator, but it becomes subordinate to deployment.

Important modeling rule:

- the system should always answer `which agent and deployment owns this runtime` before exposing runtime details

## 7. Skill Model

V1 uses a curated local skill catalog.

There is no open marketplace and no arbitrary upload path in the first release.

Skills apply to agents as an ordered instruction stack.

Implications:

- order must be user-visible and editable
- the compile layer must preserve this order
- the effective agent prompt/instruction package must be deterministic

The first version does not require per-skill configuration objects beyond enabled/disabled state and order.
That complexity can be added later if certain skills require explicit parameters.

## 8. Personality Model

V1 uses a single main system prompt field.

There is no structured identity editor in the first release.

This is deliberate:

- faster UX
- lower UI complexity
- easier mental model
- faster path to a working builder

Later expansions can split personality into layered fields, but v1 should remain simple and direct.

## 9. Launch Target and Runtime Strategy

V1 uses one generic runtime template.

Implications:

- the platform does not branch into many agent runtime families yet
- agent differences live in configuration, not in runtime taxonomy
- provisioning and debugging stay simpler

This matches the architecture choice that `Agent` is the main product object and runtime is a generic execution substrate.

## 10. Launch Flow

## 10.1 Draft Creation

When the user completes the wizard:

- create `Agent`
- create initial `AgentBuildSpec`
- create ordered `AgentSkillBinding` records
- create `AgentSecretBinding` references
- set agent status to `draft` or `ready` depending on validation completeness

No runtime is launched at this stage.

## 10.2 Launch

When the user presses `Launch`, Aquarium should:

1. Validate the build spec
   - required secrets exist
   - Telegram configuration is valid
   - model alias is valid
   - skill stack is resolvable
   - runtime template and profiles are valid

2. Create deployment record
   - `pending` or `launching`

3. Compile effective runtime inputs
   - effective personality prompt
   - ordered skill instruction stack
   - resolved secret injections
   - runtime env/config artifacts
   - Telegram configuration
   - LiteLLM constraints and key references

4. Provision or recreate runtime
   - instantiate the generic runtime from the compiled build spec
   - attach runtime reference to deployment

5. Surface launch result
   - `running` on success
   - `failed` on error

## 10.3 Relaunch

Relaunch should be a normal platform operation.

Expected behavior:

- if build spec changed, rebuild from the current spec
- create a fresh deployment record
- recreate or replace runtime
- preserve prior deployment history

This keeps the execution model clean:

- agent is long-lived
- build spec is editable
- deployments are historical
- runtime is disposable

## 11. External and Internal Interaction

## 11.1 External Channel

Telegram is the primary external channel in v1.

This means launch validation must include Telegram readiness:

- token exists
- access policy or allowed user config is valid
- setup routines succeed
- channel health can be shown independently from runtime health

The platform must not treat `runtime running` as equivalent to `agent reachable in Telegram`.

## 11.2 Internal Channel

A simple internal test channel remains in the platform.

Its role is limited:

- smoke test
- quick validation
- debugging

It is not the main product interaction surface.

This distinction protects the product from drifting back into “playground-first” behavior.

## 12. Service Layer and Internal Architecture

Aquarium already has strong orchestration and lifecycle code.
That should remain the execution engine.

The architectural change is to add an agent-aware compile/deploy layer above it.

Target layering:

- UI edits agent objects
- service layer validates and compiles build specs
- deployment layer translates build specs into execution requests
- orchestrator provisions runtime execution
- diagnostics and history map back from runtime to deployment and agent

Important rule:

- the web UI should not shell out to the CLI
- the CLI should not become the main integration surface for the product
- shared service-layer logic remains the correct architectural center

## 13. Validation and Error Handling

Validation should exist in two layers.

## 13.1 Builder-Time Validation

Fast UI validation for:

- missing required fields
- malformed prompt
- missing required secrets
- invalid Telegram config
- invalid model alias
- invalid skill ordering

## 13.2 Launch-Time Validation

Operational validation for:

- secret resolution
- config compilation
- LiteLLM key provisioning
- Telegram setup
- runtime boot

Errors should be shown in the correct surface:

- editor-level issues in their section
- launch issues in deployment/launch state
- runtime boot issues in diagnostics
- channel issues in channel health

This keeps error semantics accurate and prevents false “green” states.

## 14. Testing Strategy

V1 testing should cover four layers.

## 14.1 Model and Service Layer

- agent creation
- build spec updates
- ordered skill binding behavior
- secret binding logic
- deployment transitions
- launch compilation

## 14.2 Orchestrator Integration

- compile build spec into runtime env/config
- generic runtime provisioning
- relaunch and recreate behavior
- Telegram-first deployment path
- LiteLLM wiring and constraints

## 14.3 UI Tests

- create-agent wizard
- Agent Studio editing flow
- inline secret create/reference flow
- launch and relaunch actions
- internal test channel
- deployment and diagnostics visibility

## 14.4 End-to-End Tests

- sign in with Authelia
- create draft agent
- bind secrets
- order skills
- launch
- smoke test through internal channel
- validate Telegram external path
- stop or relaunch

## 15. Migration Shape from Current Aquarium

V1 should not be implemented as a cosmetic rename.

But it also should not throw away the existing Aquarium platform engine.

Recommended migration stance:

- preserve the orchestrator and runtime provisioning logic
- preserve the current secret injection backend if still needed
- preserve diagnostics, monitoring, and LiteLLM integration patterns
- introduce new agent-first data model and product surfaces above them

This avoids rewriting the platform from zero while still giving the product a new center of gravity.

## 16. Recommended Implementation Phases

Phase 1. Identity and entrypoint reset

- Authelia SSO integration
- workspace concept
- new app entry flow

Phase 2. Agent-first data model

- introduce `Agent`, `AgentBuildSpec`, `Deployment`, skill and secret bindings
- link runtimes as subordinate execution artifacts

Phase 3. Create Agent Wizard and Agent Home

- draft creation flow
- agent list/dashboard

Phase 4. Agent Studio

- personality editor
- ordered skill selection
- secret binding UX
- full build spec editing

Phase 5. Launch compilation and deployment pipeline

- compile build spec into runtime artifacts
- create deployment records
- wire into orchestrator

Phase 6. Telegram-first production flow

- channel validation
- external interaction path

Phase 7. Diagnostics and internal test channel polish

- internal smoke test chat
- deployment diagnostics
- status model refinement

## 17. Recommended Architectural Decision

The correct v1 direction is:

- `Approach B: Agent-First Platform Core`

Reason:

- it matches the intended product shape
- it keeps future scaling paths open
- it aligns system language with user language
- it avoids building a thin product shell over a runtime-centric core that would become future debt

## 18. Final Summary

Aquarium v1 should become a builder-first, agent-first cloud platform for a single operator.

Its defining properties are:

- Authelia SSO
- one workspace
- agents as the primary product object
- draft-first creation
- explicit launch
- one generic runtime template
- Telegram-first external channel
- simple internal test channel
- curated ordered skills
- inline secret create/reference UX
- deployment history between build spec and runtime

This design preserves the strongest parts of current Aquarium while giving it a much clearer future as a cloud for agents rather than only a control plane for managed runtimes.
