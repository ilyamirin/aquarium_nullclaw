# Admin UI Bug List

This file records the currently reproduced defects from end-to-end operator UI testing.

Test basis:

- runbook: `knowledge/admin-ui-testing-runbook.md`
- test date: `2026-04-18`
- test mode: Playwright-driven safe pass plus mutating pass
- control plane entrypoint: `http://127.0.0.1:15001/admin/`

## P1. Runtime Chat mixes bootstrap/build logs into assistant reply

Severity:

- `P1`

Affected page:

- `/admin/runtimes/<runtime-id>/chat/`

Reproduced on:

- `ui-smoke-1541`
- previously also reproduced on `ui-smoke-temp`

Steps to reproduce:

1. Open `/admin/runtime-wizard/`
2. Create a no-Telegram runtime with the default model
3. Open `/admin/runtimes/<runtime-id>/chat/`
4. Create a session
5. Send `Reply with exactly: UI chat ok.`

Expected:

- the assistant message contains only the model reply
- bootstrap and execution logs remain outside the user-visible chat transcript

Actual:

- the assistant message starts with Docker build/bootstrap output
- the actual model answer appears only at the end of the same message

Observed shape:

- the chat bubble includes lines like `#1 [internal] load local bake definitions`
- the message ends with `UI chat ok.`

Impact:

- operator chat is noisy and misleading
- runtime transport details leak into the conversation layer
- the UI cannot be treated as a clean debug chat surface

Likely boundary problem:

- buffered command execution output is being stored as assistant content instead of being separated into logs versus final model text

## P1. Newly created runtime detail page shows inconsistent model/config state immediately after create

Severity:

- `P1`

Affected pages:

- `/admin/runtimes/<runtime-id>/`
- `/admin/runtimes/<runtime-id>/diagnostics/`

Reproduced on:

- `ui-smoke-1541`

Steps to reproduce:

1. Stop `test-nullclaw`
2. Create a new no-Telegram runtime through `/admin/runtime-wizard/`
3. Land on the new runtime detail page
4. Compare top cards, overview fields, and diagnostics summary

Expected:

- the new runtime shows one consistent model/provider/config state across detail and diagnostics

Actual:

- detail top card showed `Model = openai/qwen/qwen3.6-plus`
- overview fields showed `Provider = -` and `Model Alias = -`
- diagnostics summary on the detail page initially showed `Config Valid = False`
- diagnostics page later showed `Config Valid = yes`

Impact:

- operators cannot trust the page state immediately after create
- it is unclear whether the runtime was provisioned correctly or the UI is stale

Likely cause:

- mixed refresh timing between DB-backed fields, diagnostics payload, and rendered page sections after runtime create

## P2. Host-side gateway probe can disagree with container and control-plane health after runtime start

Severity:

- `P2`

Affected surface:

- lifecycle verification and environment diagnostics around `test-nullclaw`

Reproduced on:

- `test-nullclaw` after stop/start restore

Steps to reproduce:

1. Stop `test-nullclaw` from the runtime detail page
2. Start `test-nullclaw` again from the same page
3. Confirm UI and DB show `running / healthy`
4. Check Docker and host-side health separately

Expected:

- host-side `curl http://127.0.0.1:3000/health` agrees with Docker/container health

Actual:

- Docker shows `aquarium-nullclaw-runtimes-gateway-test-nullclaw-1` as healthy after startup
- Django DB and UI returned to `running / healthy`
- host-side `curl http://127.0.0.1:3000/health` still returned `connection refused`

Impact:

- not clearly a pure admin UI defect
- still important because the operator surface may claim recovery while loopback probing disagrees

Interpretation:

- this looks like an environment, port-binding, or probe-path anomaly rather than a rendering bug
- keep it separate from UI defects, but do not ignore it

## Non-findings

The following signals were observed but are not currently treated as product bugs on their own:

- `404 /favicon.ico`
- browser autocomplete hints in console

## Recommended Fix Order

1. Separate runtime chat transport/build logs from assistant content
2. Make post-create runtime detail and diagnostics state refresh from one consistent source
3. Investigate why host loopback health can fail while Docker and control plane report recovery
