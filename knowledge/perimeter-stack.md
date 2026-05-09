# Perimeter Stack

Aquarium now has a shared web perimeter under [`perimeter-stack/`](/Users/ilyagmirin/PycharmProjects/aquarium/perimeter-stack).

Compose project name:

- `aquarium-perimeter`

## Purpose

The perimeter makes the operator-facing web surfaces behave like one local platform instead of a pile of unrelated localhost panels.

Current perimeter components:

- `Caddy`
  ingress and host-based routing
- `Authelia`
  visible login boundary and session owner
- Django control plane
  routed as `https://app.aquarium.local`
- Grafana
  routed as `https://grafana.aquarium.local`
- Infisical UI
  routed as `https://secrets.aquarium.local`

## Entry Contract

Supported operator-facing web entrypoints:

- `https://app.aquarium.local`
- `https://auth.aquarium.local`
- `https://grafana.aquarium.local`
- `https://secrets.aquarium.local`

Local browser-testing aliases are also wired through the same perimeter:

- `https://app.lvh.me`
- `https://auth.lvh.me`
- `https://grafana.lvh.me`
- `https://secrets.lvh.me`

Direct loopback URLs remain relevant for internal API traffic and health checks, but they are no longer the supported normal browser path for operators.

Important implementation note:

- Authelia `v4.39.x` rejects insecure session URLs, so the local perimeter had to move from plain HTTP to `Caddy`-terminated HTTPS with `tls internal`.
- The repo still keeps plain loopback ports for internal health and bootstrap flows, but the supported browser path is now HTTPS through the perimeter.

## Bootstrap

Bootstrap once before starting the perimeter:

```bash
make perimeter-bootstrap
```

That writes the ignored file:

- `perimeter-stack/.env`

It preserves existing Authelia secrets on rerun and writes missing values only once.

If `perimeter-stack/authelia/users_database.yml` is missing, bootstrap creates it once from:

- `AUTHELIA_ADMIN_PASSWORD_HASH`
- or `AUTHELIA_ADMIN_PASSWORD`
- or a one-time generated local password printed during bootstrap

The bootstrap script writes a bcrypt hash through `htpasswd` when a cleartext local password is supplied. This is intentional because macOS system `openssl passwd` does not support the Linux-style `-6` option consistently. If Docker was started before bootstrap and created `perimeter-stack/authelia/users_database.yml` as an empty directory, rerunning bootstrap removes that empty directory and writes the expected file.

If the local Infisical CLI session is available, bootstrap also copies `INFISICAL_OPERATOR_TOKEN` into the perimeter env file so the containerized control plane can resolve workspace-backed secrets without its own CLI login.

## Start And Health Check

```bash
make perimeter-up
make perimeter-health
```

The perimeter health check now verifies:

- `app.aquarium.local`
- `auth.aquarium.local`
- `grafana.aquarium.local`
- `secrets.aquarium.local`

It uses `curl -k --resolve ... https://...` so health validation still works even though the perimeter certificate is locally issued by Caddy.

## Operational Notes

- Django's old `/admin/login/` path is redirected into the Authelia flow.
- `Authelia` is configured with `ntp.disable_startup_check: true` for this local stack. This is a development concession to avoid startup failure on machines where container time and remote NTP differ too much.
- The containerized Django control plane now runs `python manage.py migrate --noinput` on startup before `runserver` so SSO traffic does not land on an unmigrated SQLite database.
- Grafana is configured for proxy-auth and should be entered through the perimeter route.
- `Infisical` still keeps its loopback API port for host-side control-plane and CLI usage, but the supported browser entry is the perimeter route.
- `Infisical` is deliberately perimeter-gated only in v1. Aquarium does not require an app-level Infisical SSO bridge for the current single-operator local platform. After the outer Authelia gate, Infisical may still show its own login, signup, and organization administration flows; that is accepted because Infisical remains the secret source-of-truth with its own internal authorization model.
- Current verified browser behavior:
  - `Authelia -> Django control plane` SSO works end-to-end.
  - `Infisical` is perimeter-gated, with app-native Infisical auth/admin behavior behind the gate by design.
  - `Grafana` is perimeter-gated and the Caddy upstream path should be validated after monitoring bootstrap or Docker-network changes.
