# Dark Admin UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Aquarium control-plane admin UI into a dark, agents-first Deep Ocean operator console while preserving existing backend, POST, and API contracts.

**Architecture:** Centralize the visual system in `controlplane/templates/admin/operator_base.html`, then migrate each operator page onto reusable dark console components. Keep Django templates/server-rendered flows, use only page-local JavaScript already needed by the agent composer, and verify that all existing operator routes still render and submit through the current field names.

**Tech Stack:** Django templates, Django test client, existing control-plane service layer, existing `op-*` class convention, pytest, Playwright/manual browser smoke.

---

## File Structure

Modify these files:

- `controlplane/templates/admin/operator_base.html`: global Deep Ocean shell, CSS tokens, nav, panels, buttons, forms, status pills, responsive behavior.
- `controlplane/templates/admin/operator_home.html`: agents-first Command Deck and compact infrastructure layer.
- `controlplane/templates/admin/_agent_builder_form.html`: hybrid Agent Composer sections, personality cards, skill cards, secret binding panels.
- `controlplane/templates/admin/agent_wizard.html`: dark page wrapper around the composer.
- `controlplane/templates/admin/agent_studio.html`: agent cockpit layout.
- `controlplane/templates/admin/workspace_vault.html`: dark secret/vault panels.
- `controlplane/templates/admin/runtime_wizard.html`: compact infrastructure wizard with pressure rail.
- `controlplane/templates/admin/runtime_detail.html`: runtime infrastructure cockpit.
- `controlplane/templates/admin/runtime_diagnostics.html`: cached diagnostics and explicit refresh/test action panels.
- `controlplane/templates/admin/runtime_chat.html`: dark operator chat console.
- `controlplane/templates/admin/providers.html`: dark configuration deck for provider connections.
- `controlplane/templates/admin/models.html`: dark configuration deck for models.
- `controlplane/templates/admin/integrations.html`: dark configuration deck for integrations.
- `controlplane/templates/admin/secrets.html`: dark configuration deck for runtime secrets.
- `tests/test_controlplane.py`: route/rendering regression tests and class/contract assertions.
- `knowledge/controlplane.md`: document the new Deep Ocean operator console conventions and testing expectations.

Do not modify:

- `controlplane/domain/models.py`
- `orchestrator/service_layer.py`
- upstream `nullclaw/`
- API route names or existing POST field names

## Task 1: Lock The Current UI Contracts With Failing Dark-Shell Tests

**Files:**
- Modify: `tests/test_controlplane.py`

- [ ] **Step 1: Add tests that describe the new dark shell contract**

Append these tests near the existing admin UI tests in `tests/test_controlplane.py`:

```python
def test_operator_home_uses_deep_ocean_command_deck(client, admin_user):
    client.force_login(admin_user)

    response = client.get("/admin/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "op-deep-ocean" in body
    assert "Command Deck" in body
    assert "Agent Fleet" in body
    assert "Runtime Infrastructure" in body
    assert "Create Agent" in body


def test_agent_builder_uses_composer_sections_and_choice_cards(client, admin_user):
    client.force_login(admin_user)

    response = client.get("/admin/agents/new/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "op-agent-composer" in body
    assert "Identity" in body
    assert "Personality" in body
    assert "Model" in body
    assert "Channels" in body
    assert "Skills" in body
    assert "Limits" in body
    assert "Secrets" in body
    assert "op-choice-card" in body


def test_runtime_and_config_pages_keep_dark_operator_shell(client, admin_user):
    client.force_login(admin_user)

    urls = [
        "/admin/runtime-wizard/",
        "/admin/providers/",
        "/admin/models/",
        "/admin/integrations/",
        "/admin/secrets/",
        "/admin/vault/",
    ]

    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        body = response.content.decode()
        assert "op-deep-ocean" in body, url
        assert "op-panel" in body, url
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
../../.venv/bin/pytest tests/test_controlplane.py -k "deep_ocean or composer_sections or dark_operator_shell" -v
```

Expected: FAIL because the current templates do not yet include `op-deep-ocean`, `Command Deck`, `op-agent-composer`, and the new panel classes consistently.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_controlplane.py
git commit -m "Add dark admin UI contract tests"
```

## Task 2: Build The Deep Ocean Visual System In The Base Template

**Files:**
- Modify: `controlplane/templates/admin/operator_base.html`
- Test: `tests/test_controlplane.py`

- [ ] **Step 1: Update the root shell classes**

In `operator_base.html`, make the main operator wrapper include the new shell marker:

```html
<div class="op-deep-ocean">
  <div class="op-shell">
    ...
  </div>
</div>
```

Keep existing Django template blocks:

```django
{% block operator_header_actions %}{% endblock %}
{% block operator_body %}{% endblock %}
```

- [ ] **Step 2: Replace the light CSS tokens with Deep Ocean tokens**

In the `<style>` block in `operator_base.html`, define these CSS variables at the top:

```css
:root {
  --op-bg-0: #030a12;
  --op-bg-1: #061826;
  --op-bg-2: #092335;
  --op-panel: rgba(7, 25, 38, 0.78);
  --op-panel-strong: rgba(9, 32, 48, 0.94);
  --op-border: rgba(99, 232, 230, 0.18);
  --op-border-strong: rgba(99, 232, 230, 0.38);
  --op-text: #e8fbff;
  --op-muted: #8fb5c2;
  --op-dim: #5f8391;
  --op-cyan: #63e8e6;
  --op-teal: #1fc7b6;
  --op-green: #a4f4c8;
  --op-amber: #ffd166;
  --op-coral: #ff6b6b;
  --op-purple: #9d8cff;
  --op-shadow: 0 24px 80px rgba(0, 0, 0, 0.36);
  --op-radius-lg: 28px;
  --op-radius-md: 18px;
  --op-radius-sm: 12px;
}
```

Set the page background and typography:

```css
body {
  background:
    radial-gradient(circle at 15% 5%, rgba(31, 199, 182, 0.18), transparent 34rem),
    radial-gradient(circle at 85% 0%, rgba(99, 232, 230, 0.12), transparent 30rem),
    linear-gradient(135deg, var(--op-bg-0), var(--op-bg-1) 45%, #02060b);
  color: var(--op-text);
  font-family: "Space Grotesk", "Aptos", "SF Pro Display", "Segoe UI", sans-serif;
}

.op-deep-ocean {
  min-height: 100vh;
  position: relative;
}

.op-deep-ocean::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(99, 232, 230, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(99, 232, 230, 0.035) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(to bottom, rgba(0, 0, 0, 0.75), transparent 85%);
}
```

- [ ] **Step 3: Add reusable dark components**

Ensure `operator_base.html` contains definitions for these classes:

```css
.op-panel,
.op-card,
.op-command-card {
  background: linear-gradient(145deg, var(--op-panel), rgba(4, 16, 26, 0.88));
  border: 1px solid var(--op-border);
  border-radius: var(--op-radius-lg);
  box-shadow: var(--op-shadow);
  backdrop-filter: blur(18px);
}

.op-command-card {
  position: relative;
  overflow: hidden;
}

.op-command-card::after {
  content: "";
  position: absolute;
  inset: auto -20% -45% 20%;
  height: 140px;
  background: radial-gradient(circle, rgba(99, 232, 230, 0.28), transparent 68%);
}

.op-button.primary {
  background: linear-gradient(135deg, var(--op-cyan), var(--op-teal));
  border-color: rgba(99, 232, 230, 0.72);
  color: #021016;
}

.op-status-pill,
.op-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border-radius: 999px;
  border: 1px solid var(--op-border);
}
```

Keep backwards compatibility for current template classes: `.op-card`, `.op-badge`, `.op-button`, `.op-table`, `.op-form`, `.op-field`, `.op-input`, `.op-note`, `.op-empty`.

- [ ] **Step 4: Add responsive behavior**

Add mobile stacking rules:

```css
@media (max-width: 900px) {
  .op-shell {
    padding: 1rem;
  }

  .op-grid.cols-2,
  .op-grid.cols-3,
  .op-stat-grid,
  .op-command-grid {
    grid-template-columns: 1fr;
  }

  .op-table {
    min-width: 720px;
  }

  .op-table-wrap {
    overflow-x: auto;
  }
}
```

- [ ] **Step 5: Run the focused tests**

Run:

```bash
../../.venv/bin/pytest tests/test_controlplane.py -k "deep_ocean or composer_sections or dark_operator_shell" -v
```

Expected: the home shell part may pass, but page-specific tests can still fail until later tasks add `Command Deck`, `op-agent-composer`, and consistent `op-panel` usage.

- [ ] **Step 6: Commit**

```bash
git add controlplane/templates/admin/operator_base.html tests/test_controlplane.py
git commit -m "Add Deep Ocean operator shell"
```

## Task 3: Redesign Home Into The Agent Command Deck

**Files:**
- Modify: `controlplane/templates/admin/operator_home.html`
- Test: `tests/test_controlplane.py`

- [ ] **Step 1: Replace the top stats with a Command Deck hero**

In `operator_home.html`, make the first content section:

```django
<section class="op-hero op-panel">
  <div>
    <p class="op-kicker">Aquarium Operator Console</p>
    <h1>Command Deck</h1>
    <p class="op-subtitle">Build, launch, and supervise NullClaw agents from one dark control surface.</p>
  </div>
  <div class="op-hero-actions">
    <a href="#create-agent" class="op-button primary">Create Agent</a>
    <a href="/admin/vault/" class="op-button secondary">Open Vault</a>
  </div>
</section>
```

- [ ] **Step 2: Add the agents-first metric strip**

Use existing context variables and render:

```django
<section class="op-stat-grid op-command-strip">
  <article class="op-metric"><span>Agents</span><strong>{{ agent_count }}</strong></article>
  <article class="op-metric"><span>Runtimes</span><strong>{{ runtime_count }}</strong></article>
  <article class="op-metric"><span>Needs Attention</span><strong>{{ unhealthy_count }}</strong></article>
  <article class="op-metric"><span>Recent Actions</span><strong>{{ recent_actions|length }}</strong></article>
  <article class="op-metric"><span>Monitoring</span><strong>{% if monitoring.healthy %}Live{% else %}Offline{% endif %}</strong></article>
</section>
```

- [ ] **Step 3: Turn the create-agent section into a command card**

Wrap the existing included builder form:

```django
<section class="op-command-card op-create-agent-panel" id="create-agent">
  <div class="op-section-heading">
    <p class="op-kicker">Primary Flow</p>
    <h2>Create Agent</h2>
    <p class="op-note">Create a draft agent first. Runtime launch stays explicit inside Agent Studio.</p>
  </div>
  {% include "admin/_agent_builder_form.html" with agent_form_action="create_agent_inline" agent_submit_label="Create Draft Agent" %}
</section>
```

- [ ] **Step 4: Render Agent Fleet as cards**

Replace the current agent table with cards:

```django
<section class="op-panel">
  <div class="op-section-heading">
    <p class="op-kicker">Agents</p>
    <h2>Agent Fleet</h2>
  </div>
  {% if agent_details %}
  <div class="op-agent-grid">
    {% for agent in agent_details %}
    <article class="op-agent-card">
      <div class="op-card-topline">
        <strong><a href="/admin/agents/{{ agent.slug }}/">{{ agent.name }}</a></strong>
        <span class="op-status-pill {{ agent.status }}">{{ agent.status }}</span>
      </div>
      <p class="op-note">{{ agent.slug }}</p>
      <dl class="op-mini-meta">
        <div><dt>Channel</dt><dd>{{ agent.primary_channel }}</dd></div>
        <div><dt>Model</dt><dd>{{ agent.model|default:"-" }}</dd></div>
        <div><dt>Last Launch</dt><dd>{{ agent.last_launch|default:"-" }}</dd></div>
      </dl>
      <div class="op-inline-actions">
        <a href="/admin/agents/{{ agent.slug }}/" class="op-button secondary">Studio</a>
      </div>
    </article>
    {% endfor %}
  </div>
  {% else %}
  <div class="op-empty">No agents yet. Create a draft agent to start.</div>
  {% endif %}
</section>
```

- [ ] **Step 5: Keep Runtime Infrastructure below agents**

Rename the runtime section heading to `Runtime Infrastructure`, keep existing runtime links, and wrap any table in:

```django
<div class="op-table-wrap">
  <table class="op-table op-data-table">
    ...
  </table>
</div>
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
../../.venv/bin/pytest tests/test_controlplane.py -k "deep_ocean or command_deck" -v
```

Expected: PASS for the home command deck assertions.

- [ ] **Step 7: Commit**

```bash
git add controlplane/templates/admin/operator_home.html controlplane/templates/admin/operator_base.html tests/test_controlplane.py
git commit -m "Redesign operator home as command deck"
```

## Task 4: Redesign Agent Builder, Agent Wizard, Agent Studio, And Vault

**Files:**
- Modify: `controlplane/templates/admin/_agent_builder_form.html`
- Modify: `controlplane/templates/admin/agent_wizard.html`
- Modify: `controlplane/templates/admin/agent_studio.html`
- Modify: `controlplane/templates/admin/workspace_vault.html`
- Modify: `controlplane/templates/admin/operator_base.html`
- Test: `tests/test_controlplane.py`

- [ ] **Step 1: Convert the builder form into named composer sections**

In `_agent_builder_form.html`, keep every existing input name and wrap the sections with:

```django
<div class="op-agent-composer js-agent-builder-root">
  <form method="post" class="op-form js-agent-builder-form">
    {% csrf_token %}
    <input type="hidden" name="action" value="{{ agent_form_action|default:'create_agent_inline' }}">

    <section class="op-composer-section">
      <div class="op-section-heading"><p class="op-kicker">Step 01</p><h2>Identity</h2></div>
      ...
    </section>

    <section class="op-composer-section">
      <div class="op-section-heading"><p class="op-kicker">Step 02</p><h2>Personality</h2></div>
      ...
    </section>

    <section class="op-composer-section">
      <div class="op-section-heading"><p class="op-kicker">Step 03</p><h2>Model</h2></div>
      ...
    </section>

    <section class="op-composer-section">
      <div class="op-section-heading"><p class="op-kicker">Step 04</p><h2>Channels</h2></div>
      ...
    </section>

    <section class="op-composer-section">
      <div class="op-section-heading"><p class="op-kicker">Step 05</p><h2>Skills</h2></div>
      ...
    </section>

    <section class="op-composer-section">
      <div class="op-section-heading"><p class="op-kicker">Step 06</p><h2>Limits</h2></div>
      ...
    </section>

    <section class="op-composer-section">
      <div class="op-section-heading"><p class="op-kicker">Step 07</p><h2>Secrets</h2></div>
      ...
    </section>
  </form>
</div>
```

- [ ] **Step 2: Preserve required builder field names**

After restructuring, confirm these fields still exist exactly:

```html
name="name"
name="slug"
name="model_alias"
name="gateway_port"
name="description"
name="personality_prompt"
name="telegram_enabled"
name="telegram_bot_secret"
name="telegram_allow_secret"
name="litellm_budget_usd"
name="litellm_rpm_limit"
name="litellm_tpm_limit"
name="skill_keys"
```

- [ ] **Step 3: Convert personality cards to `op-choice-card`**

Use this card shape:

```django
<label class="op-choice-card op-personality-card" data-preset-card data-preset-display="{{ preset.display_name }}">
  <input type="radio" value="{{ preset.key }}" data-preset-radio data-preset-key="{{ preset.key }}">
  <span class="op-choice-card-body">
    <span class="op-choice-eyebrow">{{ preset.subtitle }}</span>
    <strong>{{ preset.display_name }}</strong>
    <span>{{ preset.short_description }}</span>
    <span class="op-choice-footer">Best for: {{ preset.best_for }}</span>
  </span>
</label>
```

Keep the existing `personality_preset_prompts|json_script` block and current JavaScript behavior.

- [ ] **Step 4: Convert skill checkboxes to capability cards**

Use:

```django
<label class="op-choice-card op-skill-card">
  <input type="checkbox" name="skill_keys" value="{{ skill.key }}">
  <span class="op-choice-card-body">
    <strong>{{ skill.display_name }}</strong>
    <span class="op-note">{{ skill.description }}</span>
    <span class="op-badge neutral">{{ skill.skill_type }}</span>
    <span class="op-badge neutral">{{ skill.trust_status }}</span>
  </span>
</label>
```

- [ ] **Step 5: Redesign Agent Wizard and Agent Studio wrappers**

In `agent_wizard.html`, render:

```django
<section class="op-hero op-panel">
  <p class="op-kicker">Agent Builder</p>
  <h1>Create Agent</h1>
  <p class="op-subtitle">Compose a draft agent, then launch it explicitly from Agent Studio.</p>
</section>
```

In `agent_studio.html`, render the page as:

```django
<section class="op-hero op-panel">
  <p class="op-kicker">Agent Studio</p>
  <h1>{{ agent.name }}</h1>
  <p class="op-subtitle">{{ agent.slug }} · {{ agent.status }}</p>
</section>
<section class="op-grid cols-3">
  <article class="op-panel">...</article>
  <article class="op-panel">...</article>
  <article class="op-panel">...</article>
</section>
```

Keep all existing action forms and links.

- [ ] **Step 6: Redesign Workspace Vault**

In `workspace_vault.html`, use `op-panel`, `op-data-table`, `op-status-pill`, and preserve existing secret metadata. The page heading must contain `Workspace Vault`.

- [ ] **Step 7: Run focused tests**

Run:

```bash
../../.venv/bin/pytest tests/test_controlplane.py -k "composer_sections or agent" -v
```

Expected: PASS for composer and existing agent page tests.

- [ ] **Step 8: Commit**

```bash
git add controlplane/templates/admin/_agent_builder_form.html controlplane/templates/admin/agent_wizard.html controlplane/templates/admin/agent_studio.html controlplane/templates/admin/workspace_vault.html controlplane/templates/admin/operator_base.html tests/test_controlplane.py
git commit -m "Redesign agent operator surfaces"
```

## Task 5: Redesign Runtime Wizard, Runtime Detail, Diagnostics, And Chat

**Files:**
- Modify: `controlplane/templates/admin/runtime_wizard.html`
- Modify: `controlplane/templates/admin/runtime_detail.html`
- Modify: `controlplane/templates/admin/runtime_diagnostics.html`
- Modify: `controlplane/templates/admin/runtime_chat.html`
- Modify: `controlplane/templates/admin/operator_base.html`
- Test: `tests/test_controlplane.py`

- [ ] **Step 1: Add runtime page assertions**

Add:

```python
def test_runtime_wizard_uses_pressure_rail(client, admin_user):
    client.force_login(admin_user)

    response = client.get("/admin/runtime-wizard/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "Runtime Wizard" in body
    assert "op-pressure-rail" in body
    assert "Create Runtime" in body or "Next" in body


def test_runtime_detail_uses_infrastructure_cockpit(client, admin_user, runtime):
    client.force_login(admin_user)

    response = client.get(f"/admin/runtimes/{runtime.runtime_id}/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "op-runtime-cockpit" in body
    assert "Lifecycle" in body
    assert "LiteLLM" in body
```

If the project uses a different runtime fixture name, use the existing fixture already used by runtime detail tests in `tests/test_controlplane.py`.

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
../../.venv/bin/pytest tests/test_controlplane.py -k "pressure_rail or infrastructure_cockpit" -v
```

Expected: FAIL because runtime templates do not yet contain these classes.

- [ ] **Step 3: Convert Runtime Wizard progress to pressure rail**

In `runtime_wizard.html`, replace the progress section with:

```django
<section class="op-pressure-rail op-panel">
  {% for item in wizard_steps %}
  <span class="op-pressure-step {{ item.status }}">
    <span>{{ item.number }}</span>
    <strong>{{ item.label }}</strong>
  </span>
  {% endfor %}
</section>
```

Wrap each step body in:

```django
<section class="op-panel op-runtime-step">
  <div class="op-section-heading">
    <p class="op-kicker">Runtime Infrastructure</p>
    <h2>Step {{ step }} of {{ wizard_steps|length }}</h2>
  </div>
  ...
</section>
```

- [ ] **Step 4: Redesign Runtime Detail as infrastructure cockpit**

In `runtime_detail.html`, add:

```django
<div class="op-runtime-cockpit">
  <section class="op-hero op-panel">...</section>
  <section class="op-grid cols-3">
    <article class="op-panel"><h2>Lifecycle</h2>...</article>
    <article class="op-panel"><h2>LiteLLM</h2>...</article>
    <article class="op-panel"><h2>Secrets</h2>...</article>
  </section>
</div>
```

Keep existing start/stop/restart/recreate/key/limit forms and their current action names.

- [ ] **Step 5: Redesign Diagnostics and Chat**

In `runtime_diagnostics.html`, use:

```django
<section class="op-panel op-diagnostics-panel">
  <h2>Cached Diagnostics</h2>
  ...
</section>
<section class="op-panel op-danger-zone">
  <h2>Live Checks</h2>
  ...
</section>
```

In `runtime_chat.html`, use:

```django
<section class="op-panel op-chat-console">
  <h2>Operator Chat</h2>
  ...
</section>
```

Preserve existing chat form field names and route actions.

- [ ] **Step 6: Run runtime tests**

Run:

```bash
../../.venv/bin/pytest tests/test_controlplane.py -k "runtime" -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add controlplane/templates/admin/runtime_wizard.html controlplane/templates/admin/runtime_detail.html controlplane/templates/admin/runtime_diagnostics.html controlplane/templates/admin/runtime_chat.html controlplane/templates/admin/operator_base.html tests/test_controlplane.py
git commit -m "Redesign runtime operator surfaces"
```

## Task 6: Redesign Configuration Pages

**Files:**
- Modify: `controlplane/templates/admin/providers.html`
- Modify: `controlplane/templates/admin/models.html`
- Modify: `controlplane/templates/admin/integrations.html`
- Modify: `controlplane/templates/admin/secrets.html`
- Modify: `controlplane/templates/admin/operator_base.html`
- Test: `tests/test_controlplane.py`

- [ ] **Step 1: Add config page regression assertions**

Add:

```python
def test_configuration_pages_use_config_deck(client, admin_user):
    client.force_login(admin_user)

    urls = [
        "/admin/providers/",
        "/admin/models/",
        "/admin/integrations/",
        "/admin/secrets/",
    ]

    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        body = response.content.decode()
        assert "op-config-deck" in body, url
        assert "op-panel" in body, url
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```bash
../../.venv/bin/pytest tests/test_controlplane.py -k "configuration_pages_use_config_deck" -v
```

Expected: FAIL because the config pages do not yet use `op-config-deck`.

- [ ] **Step 3: Apply the shared config deck layout**

Each config page should follow this structure:

```django
<div class="op-config-deck">
  <section class="op-hero op-panel">
    <p class="op-kicker">Configuration</p>
    <h1>PAGE TITLE</h1>
    <p class="op-subtitle">SHORT OPERATOR PURPOSE.</p>
  </section>

  <section class="op-panel">
    <div class="op-section-heading">
      <h2>Existing Records</h2>
    </div>
    <div class="op-table-wrap">
      <table class="op-table op-data-table">
        ...
      </table>
    </div>
  </section>
</div>
```

Use these titles:

- Providers: `Provider Connections`
- Models: `Model Catalog`
- Integrations: `Integrations`
- Secrets: `Runtime Secrets`

Do not remove existing forms, hidden inputs, CSRF tokens, submit buttons, or test action buttons.

- [ ] **Step 4: Run config tests**

Run:

```bash
../../.venv/bin/pytest tests/test_controlplane.py -k "configuration_pages_use_config_deck or provider or model or integration or secret" -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add controlplane/templates/admin/providers.html controlplane/templates/admin/models.html controlplane/templates/admin/integrations.html controlplane/templates/admin/secrets.html controlplane/templates/admin/operator_base.html tests/test_controlplane.py
git commit -m "Redesign configuration operator pages"
```

## Task 7: Knowledge, Full Tests, And Browser Smoke

**Files:**
- Modify: `knowledge/controlplane.md`
- Modify: `docs/superpowers/plans/2026-05-08-dark-admin-ui.md`

- [ ] **Step 1: Document the new UI conventions**

Add this section to `knowledge/controlplane.md`:

```markdown
## Deep Ocean Operator Console

The Django operator UI uses a dark agents-first visual system called Deep Ocean Console.

Rules:

- agents are the primary product object
- runtimes are shown as infrastructure under agent lifecycle
- `operator_base.html` owns the shared shell, tokens, panels, buttons, forms, status pills, and responsive rules
- normal GET pages must remain read-only and render cached/persisted state
- live diagnostics, secret verification, smoke checks, and runtime probes must stay explicit operator actions
- UI templates must preserve existing POST field names and API contracts
- secrets must render only as masked labels or references

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
```

- [ ] **Step 2: Run full Django tests**

Run:

```bash
../../.venv/bin/pytest
```

Expected: all tests PASS.

- [ ] **Step 3: Run lint**

Run:

```bash
make lint
```

Expected: lint PASS. If `make lint` depends on root-local paths, run it from the worktree and keep generated artifacts ignored.

- [ ] **Step 4: Run the control-plane dev server**

Run:

```bash
../../.venv/bin/python manage.py runserver 127.0.0.1:15000
```

Expected: server starts and `/admin/` is reachable.

- [ ] **Step 5: Browser smoke with Playwright**

Use the existing Playwright skill wrapper from the project root if needed. Visit:

```text
http://127.0.0.1:15000/admin/
http://127.0.0.1:15000/admin/agents/new/
http://127.0.0.1:15000/admin/vault/
http://127.0.0.1:15000/admin/runtime-wizard/
http://127.0.0.1:15000/admin/providers/
http://127.0.0.1:15000/admin/models/
http://127.0.0.1:15000/admin/integrations/
http://127.0.0.1:15000/admin/secrets/
```

Expected:

- dark background visible on every page
- no white Django-admin panels in operator pages
- top navigation visible
- Agent Builder personality cards still update the prompt preview
- no browser console errors

- [ ] **Step 6: Commit docs and final verification adjustments**

```bash
git add knowledge/controlplane.md docs/superpowers/plans/2026-05-08-dark-admin-ui.md
git commit -m "Document dark operator console workflow"
```

## Final Acceptance

Before merging back to `main`, verify:

```bash
git status --short --branch
../../.venv/bin/pytest
make lint
```

Expected:

- branch is `codex/dark-admin-ui`
- working tree is clean
- tests pass
- lint passes

Then review the visual result in browser and decide whether to squash before merging.
