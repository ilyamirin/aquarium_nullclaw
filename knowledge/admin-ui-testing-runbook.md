# Admin UI Testing Runbook

This document is the operator and AI-agent runbook for testing the Aquarium Django admin UI end to end.

It is written for the current local control-plane stack in this repository, not for a generic Django project.

## Purpose

Use this runbook when an agent must verify that the operator UI does not just render pages, but actually drives the real platform:

- runtime lifecycle
- runtime wizard create flow
- runtime diagnostics
- runtime chat
- provider/model/integration/secrets screens
- post-save application of runtime-affecting settings

The goal is to distinguish:

- UI rendering issues
- operator flow regressions
- control-plane apply failures
- runtime/environment anomalies

## Current Operator Surface

Primary operator endpoint:

- `http://app.aquarium.local/admin/`

Direct loopback `runserver` URLs are now a dev/debug path, not the supported operator entrypoint.

Main pages:

- `/admin/`
- `/admin/runtime-wizard/`
- `/admin/runtimes/<runtime-id>/`
- `/admin/runtimes/<runtime-id>/diagnostics/`
- `/admin/runtimes/<runtime-id>/chat/`
- `/admin/providers/`
- `/admin/models/`
- `/admin/integrations/`
- `/admin/secrets/`

Current local operator credentials:

- username: `admin`
- password: `admin`

## Current Runtime Inventory Assumption

The standard local state usually includes:

- `test-nullclaw`
- `probe`
- `limit-probe`

Normal roles:

- `test-nullclaw` is the live Telegram-enabled runtime
- `probe` is a non-Telegram runtime for generic checks
- `limit-probe` is a non-Telegram runtime used for LiteLLM limit testing

Do not delete or mutate `probe` or `limit-probe` unless the test explicitly requires it.

## Safety Rules

Before running any mutating UI test:

- record the initial state of all runtimes
- record the initial lifecycle and health of `test-nullclaw`
- prefer creating a dedicated throwaway runtime for UI mutation checks
- restore `test-nullclaw` to its prior lifecycle state at the end
- delete the throwaway runtime before finishing

Do not:

- rotate or revoke production LiteLLM keys unless that is the explicit test target
- overwrite provider master credentials during a generic admin UI pass
- leave temporary runtimes behind in inventory
- leave the live runtime stopped if it started the test in `running`

## Required Preflight

### 1. Confirm control plane is reachable

Use one of:

```bash
curl -I -H 'Host: app.aquarium.local' http://127.0.0.1/auth/login/
```

or:

```bash
make controlplane-check
```

If a temporary local dev server is needed for isolated testing, use:

```bash
.venv/bin/python manage.py runserver 127.0.0.1:15001 --noreload
```

If you start a temporary `runserver`, stop it before finishing the test.

### 2. Record current runtime state

Run:

```bash
.venv/bin/python manage.py shell -c "from controlplane.domain.models import Runtime; print(list(Runtime.objects.values_list('runtime_id','lifecycle_status','health_status','gateway_port','telegram_enabled')))"
```

This gives the baseline inventory for the final report.

### 3. Record current Docker-side runtime state

Run:

```bash
docker ps --format '{{.Names}}\t{{.Status}}'
```

If the shared runtime compose file exists, also run:

```bash
docker compose -f .aquarium/generated/aquarium-nullclaw-runtimes.compose.yml ps
```

### 4. Record current gateway health

Typical checks:

```bash
curl -sS http://127.0.0.1:3000/health
curl -sS http://127.0.0.1:3002/health
curl -sS http://127.0.0.1:3003/health
```

Treat these as supporting evidence, not the only source of truth.

## Playwright Execution Method

For Codex-style automation, prefer the bundled wrapper:

```bash
/Users/ilyagmirin/.codex/skills/playwright/scripts/playwright_cli.sh open http://app.aquarium.local/auth/login/
```

Then use:

- `snapshot`
- `fill`
- `click`

Important session rule:

- `open` launches a fresh browser page/context
- after login, prefer navigating with in-page links and buttons
- do not keep calling `open` for authenticated routes unless you are prepared to log in again

Console log file:

- `.playwright-cli/console-<timestamp>.log`

Snapshot files:

- `.playwright-cli/page-<timestamp>.yml`

## Test Layers

Run the admin UI in two passes:

1. safe pass
2. mutating pass

The safe pass confirms navigation and non-destructive UI behavior.
The mutating pass proves the UI actually drives the real platform.

## Safe Pass

Minimum route coverage:

1. log in through `/auth/login/`
2. open `/admin/`
3. open runtime detail for `test-nullclaw`
4. open diagnostics for `test-nullclaw`
5. open chat for `test-nullclaw`
6. open `/admin/runtime-wizard/`
7. open `/admin/providers/`
8. open `/admin/models/`
9. open `/admin/integrations/`
10. open `/admin/secrets/`

Optional safe POST checks:

- `Provider test`
- `Integration test`
- `Test Selected Integration`

Do not treat these safe POSTs as a substitute for the mutating pass.

## Mutating Pass

The mutating pass must use a temporary no-Telegram runtime created from the wizard.

### Target scenario

1. stop `test-nullclaw`
2. create a new temporary runtime from `/admin/runtime-wizard/`
3. open its detail, diagnostics, and chat pages
4. create a chat session
5. send one short message and confirm an assistant response is rendered
6. stop the temporary runtime
7. delete the temporary runtime with typed confirmation
8. start `test-nullclaw` again
9. confirm the system returns to its prior inventory

### Temporary runtime requirements

Use a unique runtime id such as:

- `ui-smoke-temp`
- `ui-smoke-<timestamp>`

Use:

- `telegram_enabled = false`
- a non-conflicting gateway port
- the default supported model alias already present in the system

Do not enable Telegram or optional channels for the temporary runtime.

### Wizard expectations

Current wizard behavior:

- identity step requires runtime id and gateway port
- Telegram secret validation is only required when Telegram is enabled
- a no-Telegram runtime can be created without Telegram secrets
- the final validation screen can create directly and optionally run a smoke test

### Runtime chat expectations

Current chat behavior:

- session history is stored in Django DB
- chat execution is buffered, not streaming
- the control plane runs a one-shot runtime command and stores the response afterward

Minimum successful proof:

- a new session appears in the sidebar
- the user message is shown in the conversation
- an assistant message is rendered afterward

Recommended message:

```text
Reply with exactly: UI chat ok.
```

## Required Verification After Each Mutation

After `Stop`, `Start`, `Create Runtime`, or `Delete Runtime`, verify with both:

- the UI flash message and page state
- a DB or Docker-side check

Useful DB checks:

```bash
.venv/bin/python manage.py shell -c "from controlplane.domain.models import Runtime; print(list(Runtime.objects.values_list('runtime_id','lifecycle_status','health_status')))"
```

Per-runtime check:

```bash
.venv/bin/python manage.py shell -c "from controlplane.domain.models import Runtime; r=Runtime.objects.get(runtime_id='test-nullclaw'); print(r.lifecycle_status, r.health_status, r.last_healthcheck_at, r.last_error)"
```

Docker-side check:

```bash
docker ps --format '{{.Names}}\t{{.Status}}'
```

## What Counts As Pass

The admin UI pass is successful only if all of the following are true:

- login works
- main operator routes load
- the runtime wizard creates a new no-Telegram runtime
- the temporary runtime detail page renders correctly
- diagnostics route loads for the temporary runtime
- chat route loads for the temporary runtime
- chat session creation works
- a runtime reply is rendered in chat
- stop works on the temporary runtime
- delete works on the temporary runtime
- the temporary runtime disappears from runtime inventory
- `test-nullclaw` is restored to its original lifecycle state

## What Counts As Failure

Treat the following as real failures:

- operator login breaks
- wizard submit fails or loops incorrectly
- runtime is created in DB but not reflected in inventory
- runtime page renders but lifecycle actions do not actually change state
- chat session creation fails
- user message is stored but no assistant reply is ever rendered
- delete action returns success but the runtime remains in DB or inventory
- restoration of `test-nullclaw` fails

## Known Noise To Ignore

Current browser noise that should not be promoted to a product finding by itself:

- `404 /favicon.ico`
- browser autocomplete hints such as missing `autocomplete` suggestions

Report them only as incidental console noise.

## Current Known Findings And Interpretation Rules

These behaviors have already been observed and should be treated carefully:

### 1. Health-state inconsistency between UI sections

Possible observed pattern:

- runtime detail says `Health = healthy`
- lifecycle says `stopped`
- DB says `health_status = unhealthy`

or:

- diagnostics shows `Gateway Health = HTTP 200`
- diagnostics summary still shows overall `Health = unhealthy`

Treat this as a real finding when reproduced.

Interpretation:

- the operator UI is mixing different health sources or stale state
- this is more serious than cosmetic text mismatch because it affects operator decisions

### 2. Chat response polluted by bootstrap/build logs

Possible observed pattern:

- assistant chat bubble includes Docker build output or bootstrap logs
- the actual model answer appears only at the end of the message

Treat this as a real finding.

Interpretation:

- the control plane is surfacing transport/bootstrap output as assistant content
- the operator chat is functionally working, but the UX and message boundary are incorrect

### 3. Running lifecycle with unhealthy status after restore

Possible observed pattern for `test-nullclaw`:

- UI shows `Lifecycle = running`
- Docker shows the gateway container `Up (healthy)`
- diagnostics shows `Gateway Health = HTTP 200`
- overall control-plane health remains `unhealthy`
- recent logs include Telegram timeout warnings

Treat this as an environment-or-health-aggregation issue unless the failure is clearly inside the admin UI itself.

This still belongs in the report because it affects trust in the operator surface.

## Evidence Collection

For each meaningful step, keep:

- Playwright snapshot
- final page URL
- flash message text
- relevant console lines
- DB check output when lifecycle changed
- Docker or health-check output when relevant

Do not rely on memory-only reporting.

## Layout Smoke Checks

Before reporting the admin UI as visually healthy, verify the main operator surfaces at desktop width:

- `/admin/`
- `/admin/agents/new/`
- `/admin/runtime-wizard/`
- `/admin/providers/`
- `/admin/models/`
- `/admin/integrations/`
- `/admin/secrets/`
- `/admin/vault/`

Minimum browser checks:

- `document.scrollingElement.scrollWidth <= window.innerWidth + 2`
- adjacent `.op-composer-section` blocks do not overlap
- direct children of `.op-composer-section` do not extend past the section bottom
- `#main` does not render a light `bg-white` background around the Aquarium operator shell

Treat favicon `404` as cosmetic only. Treat layout overlap, horizontal page scroll, or light wrapper backgrounds as admin UI bugs.

## Final Report Format

The final report should always contain four sections:

### Passed Flows

List the flows that completed successfully.

### Failed Flows

List reproducible failures.

### Risky Or Unverified

List important flows you intentionally did not run.

### Environment Anomalies

List issues that may not be pure UI regressions but still affect operator confidence.

## Cleanup Checklist

Before finishing, confirm all of the following:

- temporary runtime is deleted
- runtime inventory is back to the expected set
- `test-nullclaw` is back in its prior lifecycle state
- any temporary `runserver` process has been stopped
- the final report clearly separates UI defects from runtime/environment anomalies

## Minimal End-To-End Example

This is the shortest acceptable real mutating admin UI test:

1. log in to `/admin/`
2. stop `test-nullclaw`
3. create `ui-smoke-temp` from the wizard with `telegram=False`
4. open `ui-smoke-temp` chat
5. create session `QA session`
6. send `Reply with exactly: UI chat ok.`
7. confirm an assistant message appears
8. stop `ui-smoke-temp`
9. delete `ui-smoke-temp`
10. start `test-nullclaw`
11. verify final runtime inventory and state through DB and Docker

If any of those steps fail, the mutating pass is not complete.
