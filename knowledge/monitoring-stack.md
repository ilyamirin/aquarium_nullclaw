# Monitoring Stack

Aquarium now includes a local self-hosted observability stack under [monitoring-stack](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack).

Compose project name:

- `aquarium-monitoring`

Current stack:

- `Grafana` for dashboards, Explore, and operator UI
- `Alloy` as the single collector/router
- `Loki` for container logs
- `Tempo` for NullClaw OTEL traces
- `Mimir` for blackbox and Alloy self-metrics

## Why This Stack Exists

The project already had:

- runtime logs in Docker
- detailed NullClaw observability support through OTEL
- per-service health endpoints

What was missing was one operator surface that could answer:

- are all runtimes healthy right now
- what are the recent logs across all Aquarium services
- did a specific NullClaw request produce trace data
- is the monitoring plane itself healthy

The stack is local-first and intentionally simple:

- loopback-only host exposure
- no reverse proxy in front of Loki, Tempo, Mimir, or Alloy
- Grafana is the operator-facing monitoring UI and should be entered through `https://grafana.aquarium.local`
- local browser automation can also use `https://grafana.lvh.me`

## Signal Flow

Current signal split:

- `Loki`
  receives Docker logs from all Aquarium containers through Alloy
- `Tempo`
  receives NullClaw OTEL traces through Alloy on `http://alloy.local:4318`
- `Mimir`
  receives:
  - blackbox probe metrics for the Aquarium service endpoints
  - Alloy self-metrics

The effective flow is:

```text
NullClaw runtimes --OTLP traces--> Alloy --OTLP--> Tempo
Aquarium Docker containers -------> Alloy --------> Loki
Health probes + Alloy metrics ----> Alloy --------> Mimir
Grafana --------------------------> Loki/Tempo/Mimir
```

## Secret Model

Source of truth for monitoring secrets:

- Infisical project: `monitoring-core`
- environment: `prod`
- path: `/runtime`

Current secrets stored there:

- `GF_SECURITY_ADMIN_PASSWORD`
- `GF_SECURITY_SECRET_KEY`

Bootstrap material is written locally to the ignored file:

- [monitoring-stack/.env](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack/.env)

That file contains:

- port values
- `INFISICAL_API_URL`
- `INFISICAL_PROJECT_ID`
- `INFISICAL_ENV`
- `INFISICAL_PATH`
- `INFISICAL_TOKEN`

This mirrors the rest of Aquarium:

- Infisical is the secret source-of-truth
- local `.env` holds only bootstrap material required to start the container and fetch real secrets
- local `.env` also carries `GRAFANA_PUBLIC_URL` so Grafana can render perimeter-native absolute URLs

## Runtime OTEL Integration

The orchestrator now checks whether [monitoring-stack/.env](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack/.env) exists and contains a usable monitoring bootstrap token.

If monitoring bootstrap exists, generated runtime env files now include:

- `NULLCLAW_OTEL_ENABLED=true`
- `NULLCLAW_OTEL_ENDPOINT=http://alloy.local:4318`
- `NULLCLAW_OTEL_SERVICE_NAME=nullclaw-<runtime-id>`

To make that endpoint resolvable and still acceptable to NullClaw's local-http validation, runtime services join the shared Docker network:

- `aquarium-monitoring`

Important consequence:

- once monitoring is bootstrapped, NullClaw diagnostics switch from `backend=log` to `backend=otel`
- the deepest runtime/tool/LLM events therefore move into `Tempo`
- container stdout/stderr remains available in `Loki`

## Files

Tracked stack files:

- [monitoring-stack/docker-compose.yml](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack/docker-compose.yml)
- [monitoring-stack/.env.example](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack/.env.example)
- [monitoring-stack/alloy/config.alloy](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack/alloy/config.alloy)
- [monitoring-stack/loki/loki.yaml](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack/loki/loki.yaml)
- [monitoring-stack/tempo/tempo.yaml](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack/tempo/tempo.yaml)
- [monitoring-stack/mimir/mimir.yaml](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack/mimir/mimir.yaml)
- [monitoring-stack/grafana/provisioning](/Users/ilyagmirin/PycharmProjects/aquarium/monitoring-stack/grafana/provisioning)

Tracked bootstrap/runtime helpers:

- [scripts/bootstrap-monitoring-stack.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/bootstrap-monitoring-stack.sh)
- [scripts/grafana-infisical-entrypoint.sh](/Users/ilyagmirin/PycharmProjects/aquarium/scripts/grafana-infisical-entrypoint.sh)
- [docker/grafana-infisical.Dockerfile](/Users/ilyagmirin/PycharmProjects/aquarium/docker/grafana-infisical.Dockerfile)

## Perimeter Behavior

- Grafana is perimeter-gated by `Authelia` and configured for proxy-auth using the forwarded `Remote-User` header.
- The monitoring stack keeps the loopback host port `13000` for local health/debug access, but the supported operator browser path is the perimeter route.
- The perimeter Caddy upstream reaches Grafana by Docker service/container name on the shared `aquarium-perimeter` network. If the browser route shows an upstream failure, first verify Grafana itself is running and that `aquarium-perimeter-caddy-1` can fetch `http://aquarium-grafana:3000/api/health`.

Ignored local state:

- `monitoring-stack/.env`
- `monitoring-stack/data/`

## Setup And Start Order

Bootstrap monitoring secrets:

```bash
./scripts/bootstrap-monitoring-stack.sh
```

Or:

```bash
make monitoring-bootstrap
```

Start the stack:

```bash
make monitoring-up
```

Health check:

```bash
make monitoring-health
```

Important ordering rule:

- if you want NullClaw runtimes to emit OTEL traces from the moment they are created, bootstrap monitoring before running `orchestrator runtime create`

If monitoring is added later, rerun `runtime create` for each runtime you want to move onto OTEL.

## Local Endpoints

Operator-facing UI endpoint:

- Grafana: `https://grafana.aquarium.local`
- local browser alias: `https://grafana.lvh.me`

Internal and health-check endpoints:

- Grafana direct health/debug: `http://127.0.0.1:13000`
- Alloy UI: `http://127.0.0.1:12345`
- Loki: `http://127.0.0.1:13100`
- Tempo: `http://127.0.0.1:13200`
- Mimir: `http://127.0.0.1:13300`
- OTLP HTTP ingest: `http://127.0.0.1:4318`

Provisioned Grafana datasources:

- `Mimir`
- `Loki`
- `Tempo`

Provisioned dashboard:

- `Aquarium Overview`

## What Alloy Probes

Blackbox metrics currently cover:

- `test-nullclaw` health
- `probe` health
- `limit-probe` health
- `LiteLLM` liveliness
- `Infisical` status
- `Grafana` health
- `Loki` ready
- `Tempo` ready
- `Mimir` ready
- `Alloy` UI root

This is v1 scope only.

Current deliberate omissions:

- no Postgres exporter
- no Redis exporter
- no cAdvisor on macOS by default

## Grafana Upstream Recovery

If `Open Grafana` or the perimeter route is red while the Caddy route exists, separate the checks:

1. Direct Grafana health:

   ```bash
   curl -fsS http://127.0.0.1:13000/api/health
   ```

2. Caddy-to-Grafana upstream from inside the perimeter network:

   ```bash
   docker exec aquarium-perimeter-caddy-1 wget -qO- http://aquarium-grafana:3000/api/health
   ```

3. Control-plane monitoring payload:

   ```bash
   docker exec aquarium-perimeter-controlplane-1 python -c "from orchestrator.service_layer import monitoring_surface_payload; print(monitoring_surface_payload())"
   ```

The common local failure mode after Infisical data is reset is a stale `INFISICAL_TOKEN` in `monitoring-stack/.env`. Grafana then restart-loops because its entrypoint cannot fetch `GF_SECURITY_ADMIN_PASSWORD` and `GF_SECURITY_SECRET_KEY` from the `monitoring-core` project.

Recovery path:

1. Ensure Infisical has an admin user and organization. If the local DB is empty, bootstrap Infisical before continuing.
2. Export a valid `INFISICAL_ADMIN_TOKEN` for that organization.
3. Run `make monitoring-bootstrap` to recreate the `monitoring-core` project material and rewrite `monitoring-stack/.env`.
4. Run `make monitoring-up`.
5. Verify direct health, Caddy upstream health, and the control-plane monitoring payload before debugging Caddy routing.

## Operator Workflow

Common commands:

```bash
make monitoring-bootstrap
make monitoring-up
make monitoring-health
make monitoring-logs
make monitoring-down
```

Typical end-to-end local check:

1. `make monitoring-bootstrap`
2. `make monitoring-up`
3. `make monitoring-health`
4. rerun `runtime create` for the runtimes you want on OTEL
5. run a one-shot NullClaw request
6. inspect:
   - Grafana Explore / Tempo for traces
   - Grafana Explore / Loki for logs
   - Grafana Explore / Mimir for `probe_success`

## Current Constraints

- this is local OSS only, not a production-hardened deployment
- Mimir is monolithic and filesystem-backed for simplicity
- Loki is filesystem-backed for simplicity
- Tempo uses local storage for simplicity
- no auth layer protects Loki, Tempo, Mimir, or Alloy beyond loopback binding
- NullClaw can currently emit its deep diagnostics either as OTEL traces or as log backend output, not both at once
