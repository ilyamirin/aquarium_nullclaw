# Administration

This is the operator-facing runbook for the current Aquarium stack.

Use it after initial install is complete.

## Main Services

Primary services:

- web control plane: Django + Unfold
- runtime plane: `aquarium-nullclaw-runtimes`
- secrets backend: `aquarium-infisical`
- LLM gateway: `aquarium-litellm`
- monitoring plane: `aquarium-monitoring`

Primary runtime ids:

- `test-nullclaw`
- `probe`
- `limit-probe`

## Core Admin Commands

List runtimes:

```bash
.venv/bin/orchestrator runtime list
```

Inspect one runtime:

```bash
.venv/bin/orchestrator runtime status --id test-nullclaw
.venv/bin/orchestrator runtime status --id probe
.venv/bin/orchestrator runtime status --id limit-probe
```

Inspect LiteLLM:

```bash
.venv/bin/orchestrator litellm status
```

Inspect one runtime key:

```bash
.venv/bin/orchestrator runtime inspect-key --id test-nullclaw
```

Inspect configured limits:

```bash
.venv/bin/orchestrator runtime limits --id limit-probe
```

Inspect monitoring stack:

```bash
make monitoring-health
```

Inspect Django control plane:

```bash
make controlplane-check
```

Rotate a runtime key:

```bash
.venv/bin/orchestrator runtime rotate-key --id test-nullclaw
```

Revoke a runtime key:

```bash
.venv/bin/orchestrator runtime revoke-key --id probe
```

## Logs

Runtime logs:

```bash
docker logs aquarium-nullclaw-runtimes-gateway-test-nullclaw-1
docker logs aquarium-nullclaw-runtimes-gateway-probe-1
docker logs aquarium-nullclaw-runtimes-gateway-limit-probe-1
```

Follow runtime logs:

```bash
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml logs -f gateway-test-nullclaw
docker compose -f /Users/ilyagmirin/PycharmProjects/aquarium/.aquarium/generated/aquarium-nullclaw-runtimes.compose.yml logs -f gateway-limit-probe
```

LiteLLM logs:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/litellm-stack
docker compose logs -f litellm
```

Infisical logs:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/infisical-stack
docker compose logs -f backend
```

Monitoring logs:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack
docker compose logs -f
```

## Internal UI/API

Current internal operator endpoints:

- Control plane UI: `http://127.0.0.1:15000/admin/`
- Runtime detail pattern: `http://127.0.0.1:15000/admin/runtimes/<runtime-id>/`
- Providers page: `http://127.0.0.1:15000/admin/providers/`
- Models page: `http://127.0.0.1:15000/admin/models/`
- Integrations page: `http://127.0.0.1:15000/admin/integrations/`
- Secrets page: `http://127.0.0.1:15000/admin/secrets/`
- Control plane API root pattern: `http://127.0.0.1:15000/api/...`
- LiteLLM UI: `http://127.0.0.1:14000/ui/`
- LiteLLM fallback login: `http://127.0.0.1:14000/fallback/login`
- LiteLLM root: `http://127.0.0.1:14000/`
- LiteLLM OpenAPI JSON: `http://127.0.0.1:14000/openapi.json`
- Infisical UI: `http://127.0.0.1:18080`
- Grafana: `http://127.0.0.1:13000`
- Alloy: `http://127.0.0.1:12345`
- Loki: `http://127.0.0.1:13100`
- Tempo: `http://127.0.0.1:13200`
- Mimir: `http://127.0.0.1:13300`

Policy:

- these are internal-only loopback endpoints
- runtime containers do not receive LiteLLM admin credentials
- only operators and the orchestrator use LiteLLM admin functions
- the Django control plane is operator-only in `v1`

Current local Django operator bootstrap:

- username: `admin`
- password: `admin`

Current operator workflow preference:

- start from `/admin/`
- use the runtime detail page as the first stop for a specific runtime
- use `Providers`, `Models`, `Integrations`, and `Secrets` pages for cross-runtime administration
- use Grafana/Loki/Tempo/Mimir only when the control plane summary is not enough
- treat raw `/admin/domain/...` URLs as unsupported operator entrypoints; they now redirect into the operator console

Compatibility note:

- `/admin/dashboard/` and `/admin/runtimes/` now redirect back to `/admin/`
- operator pages now share a single Unfold-native layout and standardized browser titles

Current local fallback UI login:

- username: `admin`
- password: the current `LITELLM_MASTER_KEY` value from the `litellm-core` Infisical project

Important note:

- this is a UI-level fallback login convention in the current LiteLLM build
- the underlying secret of record is still `LITELLM_MASTER_KEY` from the `litellm-core` Infisical project

Current Grafana admin user:

## Operator UI Locking

If the control plane previously showed `database is locked` on `/admin/`, the important behavior change is now:

- ordinary `GET` requests use cached diagnostics and cached secret verification state
- live diagnostics probing is explicit, not implicit during page render
- runtime repair/backfill is explicit, not part of generic reads

Operational implication:

- opening multiple admin tabs should no longer compete for SQLite write locks during normal browsing
- if fresh health/log/trace state is needed, use the explicit probe/test actions instead of expecting passive page loads to refresh it

- username: `admin`
- password source-of-truth: `GF_SECURITY_ADMIN_PASSWORD` in Infisical project `monitoring-core`

## Secret Rotation

Current practical rules:

- Infisical is the source of truth for application secrets
- LiteLLM owns provider access
- `.aquarium/runtimes/<id>/runtime.env` stores only bootstrap material and non-secret settings

### Rotate Telegram or runtime-facing secret material

Preferred path now:

- open the runtime detail page
- update the typed runtime secret in the `Secrets` section
- run the secret verify action

CLI fallback remains valid when needed:

Example:

```bash
TELEGRAM_BOT_TOKEN=... \
TELEGRAM_ALLOW_FROM=373793732 \
.venv/bin/orchestrator runtime create --id test-nullclaw --telegram --gateway-port 3000
```

### Rotate provider master key

```bash
OPENROUTER_API_KEY=... \
.venv/bin/orchestrator litellm bootstrap
cd /Users/ilyagmirin/PycharmProjects/aquarium/litellm-stack
docker compose up -d
```

### Rotate monitoring Grafana credentials

Update `GF_SECURITY_ADMIN_PASSWORD` or `GF_SECURITY_SECRET_KEY` in Infisical project `monitoring-core`, then restart only Grafana:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack
docker compose up -d grafana
```

### Rotate Django operator credentials

Use Django management commands:

```bash
.venv/bin/python manage.py changepassword admin
```

Or recreate the operator explicitly:

```bash
.venv/bin/python manage.py bootstrap_operator --username admin --password admin --email admin@aquarium.local
```

## Backfill And Empty Admin Sections

If imported runtimes exist in the DB but operator pages look suspiciously empty, run the related-record backfill:

```bash
cd /Users/ilyagmirin/PycharmProjects/aquarium
.venv/bin/python manage.py backfill_runtime_related
```

This reconstructs operator-side records such as:

- integration connections
- runtime secret refs
- diagnostic snapshots
- baseline action logs

## Isolation Management

Run the cross-runtime proof:

```bash
.venv/bin/orchestrator runtime probe-check --id probe --target test-nullclaw
```

Expected:

- each runtime can read only its own LiteLLM key
- cross-project reads do not expose the other runtime's secret value

## Telegram Administration

Only `test-nullclaw` currently has Telegram enabled.

If Telegram stops responding:

1. check `runtime status --id test-nullclaw`
2. inspect runtime logs
3. verify the live runtime still has the correct `TELEGRAM_BOT_TOKEN` in Infisical
4. verify LiteLLM is alive
5. rerun `runtime create` for `test-nullclaw`

## Limit Administration

### RPM enforcement

Current verified behavior:

- LiteLLM returns `429`
- NullClaw surfaces a recognizable `RateLimited` failure

This path is currently acceptable for platform behavior.

### Budget enforcement

Current verified behavior:

- LiteLLM enforces the budget
- LiteLLM logs a budget-exceeded rejection
- NullClaw currently surfaces this as a generic `ApiError`

This is a known platform gap.

Operators should know:

- the limit is still enforced
- the user-facing explanation on the NullClaw side is not yet good enough

## Recovery Notes

If the runtime plane is lost but Infisical and LiteLLM still exist:

1. recreate `.venv`
2. run `.venv/bin/orchestrator init`
3. recreate runtimes with `runtime create`
4. verify health, isolation, and one-shot execution

If LiteLLM is lost:

1. rerun `.venv/bin/orchestrator litellm bootstrap`
2. restart `litellm-stack`
3. rerun `runtime create` for affected runtimes if necessary

If monitoring is lost:

1. rerun `make monitoring-bootstrap`
2. rerun `make monitoring-up`
3. rerun `runtime create` for runtimes that should emit OTEL traces
4. verify Grafana, Loki, Tempo, and Mimir health

If the control plane DB is lost but `.aquarium/state/runtimes.json` survives:

1. rerun `make controlplane-migrate`
2. rerun `make controlplane-import-state`
3. rerun `make controlplane-bootstrap-operator`
4. start the UI with `make controlplane-run`

If Infisical is lost:

- recover `infisical-stack/data/` if possible
- otherwise bootstrap Infisical again, recreate `litellm-core`, then recreate runtime projects and runtimes

## Current Known Constraints

- the runtime plane is CLI-driven only
- service tokens remain bootstrap material in ignored files
- budget-exceeded UX in NullClaw is not as good as rate-limit UX
- older manual stacks still exist but should be treated as legacy references
- monitoring is loopback-only and intentionally unauthenticated except for Grafana
