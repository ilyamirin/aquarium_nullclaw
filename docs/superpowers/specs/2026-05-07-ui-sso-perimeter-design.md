# Aquarium UI SSO Perimeter Design

Date: 2026-05-07
Status: Approved for planning

## Goal

Turn Aquarium's user-facing web surfaces into one perimeter-protected local platform.

The supported operator access path becomes:

- `app.aquarium.local`
- `grafana.aquarium.local`
- `secrets.aquarium.local`

All of them sit behind:

- `Caddy` as ingress
- `Authelia` as the single SSO boundary

Direct localhost UI access stops being the supported normal path.

## Product Rule

Every user-facing UI in Aquarium must:

- live behind the common perimeter
- get its own subdomain under `*.aquarium.local`
- rely on the Authelia session as the visible login story
- avoid exposing a separate public login UX when accessed normally

This applies to:

- Django control plane
- Grafana
- Infisical
- future web UIs added later

## Domain Model For Access

External URLs:

- `app.aquarium.local` -> Django control plane
- `grafana.aquarium.local` -> Grafana
- `secrets.aquarium.local` -> Infisical

Internal model:

- `Authelia` decides who may enter
- `Caddy` decides where authenticated traffic goes
- downstream services are internal upstreams, not independent public login surfaces

## Strict Perimeter Rule

The perimeter is strict, not advisory.

That means:

- direct user-facing host port exposure for Django UI must be removed
- direct user-facing host port exposure for Grafana UI must be removed
- direct user-facing host port exposure for Infisical UI must be removed
- direct localhost UI bookmarks are no longer the documented operator path

The only normal user-facing entry is through Caddy.

## Local Environment Assumptions

V1 perimeter assumptions:

- local HTTP only
- root domain family: `aquarium.local`
- no TLS in this first pass

Constraint:

- the network/auth design should still be shaped so HTTPS can be added later without rethinking subdomain routing or the auth boundary

## Network And Compose Topology

### Shared Perimeter Network

Add one shared Docker network for all web-facing services that must be reachable by ingress:

- `caddy`
- `authelia`
- Django web service
- Grafana
- Infisical backend/UI

Future web UI services join the same pattern.

### Port Exposure Policy

Publish host-facing HTTP ports only for the ingress layer.

For the protected UI services:

- Django keeps its internal app port only
- Grafana keeps its internal app port only
- Infisical keeps its internal app port only

They should remain reachable from Caddy over the shared internal network, not as direct operator browser targets.

### Out Of Scope Ports

This perimeter change does not automatically convert every service port into a routed UI.

Not first-priority perimeter surfaces:

- Loki
- Tempo
- Mimir
- Alloy
- runtime gateway ports
- OTEL ports
- internal API-only services

These may remain internal or separately handled until they are intentionally promoted to user-facing surfaces.

## Authentication Flow

### Normal Flow

1. user opens one of the platform subdomains
2. request reaches Caddy
3. Caddy checks access through Authelia
4. if there is no valid session, user is redirected into Authelia login
5. after successful auth, user returns to the requested subdomain
6. downstream app receives only already-authenticated traffic

This is the only normal login path.

### Downstream App Contract

Downstream apps should stop behaving as identity owners.

Instead:

- perimeter decides whether the user may enter
- authenticated identity is forwarded from the proxy layer
- local login pages stop being the normal UX

## Service-Specific Strategy

### Django

Target behavior:

- routed through `app.aquarium.local`
- proxy-provided identity is trusted
- old `/admin/login/` redirects into SSO
- direct localhost UI access is no longer the documented path

Internal Django users may still exist, but they represent SSO identity rather than a standalone username/password flow.

### Grafana

Target behavior:

- routed through `grafana.aquarium.local`
- protected by Caddy + Authelia
- no separate visible Grafana login wall in normal use

Preferred integration shape:

- perimeter auth at Caddy
- Grafana proxy-auth mode internally
- forwarded user identity mapped into Grafana session behavior

### Infisical

Target behavior:

- routed through `secrets.aquarium.local`
- protected by Caddy + Authelia
- no direct operator path through raw localhost UI

Important distinction:

- perimeter SSO controls access to the UI
- this does not require a risky full rewrite of Infisical's internal auth semantics on day one

V1 goal for Infisical:

- unified external access boundary first
- internal simplification only if actually required and safe

## Legacy Behavior

Legacy direct login paths must become redirect or deny paths, not alternative UX.

Required outcomes:

- old Django login page no longer acts as a normal login screen
- direct localhost UI instructions are removed from docs and operator expectations
- internal services stop being presented as public browser entrypoints

## Migration Plan

### Phase 1: Perimeter Foundation

Add:

- `Caddy`
- `Authelia`
- shared perimeter network
- local host mapping expectations for `app.aquarium.local`, `grafana.aquarium.local`, `secrets.aquarium.local`

Success condition:

- subdomain routing works
- Authelia can gate entry
- upstream services are reachable through the perimeter

### Phase 2: Django Conversion

- route Django through Caddy
- trust perimeter identity
- redirect legacy login into SSO
- remove direct user-facing Django host port exposure

### Phase 3: Grafana Conversion

- route Grafana through Caddy
- enable perimeter-compatible auth behavior
- remove direct user-facing Grafana host port exposure

### Phase 4: Infisical Conversion

- route Infisical through Caddy
- protect it through Authelia
- remove direct user-facing Infisical host port exposure

### Phase 5: Cleanup

- update docs and runbooks
- update UI links still pointing to localhost service ports
- remove stale direct-access assumptions from operator UX
- make the perimeter rule the default for future UIs

## Success Criteria

The design is successful when:

- all main UIs are reached through `*.aquarium.local`
- Authelia is the only visible login boundary
- Django no longer exposes a real alternative login path
- Grafana no longer behaves like a separate login island
- Infisical is no longer treated as a raw localhost admin UI
- direct localhost UI entry is no longer the supported normal operator path

## Explicit Non-Goals For V1

This design does not require in the first pass:

- HTTPS
- full RBAC or team/org model changes
- immediate replacement of every app's internal auth semantic
- perimeter routing for every non-UI service in the repository

The important thing is one ingress, one login story, and no normal bypass around the perimeter.
