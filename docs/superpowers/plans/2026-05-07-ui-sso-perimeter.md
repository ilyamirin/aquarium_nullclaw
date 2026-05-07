# UI SSO Perimeter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put Aquarium's user-facing UIs behind one local `Caddy + Authelia` perimeter at `*.aquarium.local`, with Django, Grafana, and Infisical no longer exposed as the normal direct localhost browser entrypoints.

**Architecture:** Add a dedicated perimeter stack that owns ingress and SSO, containerize the Django control plane so it can live on the same internal network as Grafana and Infisical, and rewire all user-facing links and docs around the subdomain entrypoints. Keep non-UI services on their existing internal or loopback-only ports unless they are explicitly promoted to the perimeter later.

**Tech Stack:** Docker Compose, Caddy, Authelia, Django 5, existing Infisical backend, existing Grafana stack, pytest, Django test client, curl-based smoke checks.

---

### Task 1: Add the perimeter foundation stack and containerized control plane

**Files:**
- Create: `docker/controlplane.Dockerfile`
- Create: `perimeter-stack/docker-compose.yml`
- Create: `perimeter-stack/Caddyfile`
- Create: `perimeter-stack/authelia/configuration.yml`
- Create: `perimeter-stack/authelia/users_database.yml.example`
- Create: `scripts/bootstrap-perimeter-stack.sh`
- Modify: `Makefile`
- Modify: `.gitignore`
- Test: `tests/test_controlplane.py`

- [ ] **Step 1: Write the failing tests for perimeter-aware settings and links**

```python
def test_controlplane_public_base_url_defaults_to_aquarium_subdomain(settings):
    from controlplane.core import settings as controlplane_settings

    assert controlplane_settings.CONTROLPLANE_PUBLIC_URL == "http://app.aquarium.local"


def test_operator_home_prefers_perimeter_links(client, admin_user, settings):
    client.force_login(admin_user)
    response = client.get("/admin/")

    assert response.status_code == 200
    body = response.content.decode()
    assert "http://grafana.aquarium.local" in body
    assert "http://secrets.aquarium.local" in body
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `../../.venv/bin/pytest tests/test_controlplane.py -k "perimeter or public_base_url" -v`
Expected: FAIL because the new perimeter URL settings and rendered links do not exist yet.

- [ ] **Step 3: Add the perimeter stack and control-plane containerization**

Create the new stack and Dockerfile with the following structure:

```dockerfile
# docker/controlplane.Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY orchestrator /app/orchestrator
COPY controlplane /app/controlplane
COPY manage.py /app/manage.py
COPY knowledge /app/knowledge
COPY scripts /app/scripts

RUN pip install --no-cache-dir -e .[dev]

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000", "--noreload"]
```

```yaml
# perimeter-stack/docker-compose.yml
name: aquarium-perimeter

services:
  caddy:
    image: caddy:2
    ports:
      - "127.0.0.1:${PERIMETER_HTTP_PORT:-8080}:80"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
    depends_on:
      - authelia
      - controlplane
    networks:
      - perimeter
      - infisical
      - monitoring

  authelia:
    image: authelia/authelia:latest
    env_file:
      - path: .env
        required: false
    volumes:
      - ./authelia/configuration.yml:/config/configuration.yml:ro
      - ./authelia/users_database.yml:/config/users_database.yml:ro
    networks:
      - perimeter

  controlplane:
    build:
      context: ..
      dockerfile: docker/controlplane.Dockerfile
    env_file:
      - path: .env
        required: false
    environment:
      CONTROLPLANE_PUBLIC_URL: http://app.aquarium.local
      AUTHELIA_LOGIN_URL: http://auth.aquarium.local
      AUTHELIA_LOGOUT_URL: http://auth.aquarium.local/logout
      AUTHELIA_HEADER_USER: HTTP_REMOTE_USER
    volumes:
      - ../.aquarium:/app/.aquarium
      - ../knowledge:/app/knowledge
    networks:
      - perimeter

networks:
  perimeter:
    name: aquarium-perimeter
  infisical:
    external: true
    name: aquarium-infisical
  monitoring:
    external: true
    name: aquarium-monitoring
```

- [ ] **Step 4: Add Makefile entrypoints and ignore rules**

Add the new perimeter commands:

```make
.PHONY: perimeter-bootstrap perimeter-up perimeter-down perimeter-health

perimeter-bootstrap:
	./scripts/bootstrap-perimeter-stack.sh

perimeter-up:
	cd perimeter-stack && docker compose up -d

perimeter-down:
	cd perimeter-stack && docker compose down

perimeter-health:
	curl -fsS -H 'Host: app.aquarium.local' http://127.0.0.1:8080/auth/login/ >/dev/null
	curl -fsS -H 'Host: grafana.aquarium.local' http://127.0.0.1:8080/ >/dev/null || true
```

Ensure `.gitignore` keeps local perimeter secrets out of git:

```gitignore
/perimeter-stack/.env
/perimeter-stack/authelia/users_database.yml
```

- [ ] **Step 5: Run targeted tests and compose validation**

Run:
- `../../.venv/bin/pytest tests/test_controlplane.py -k "perimeter or public_base_url" -v`
- `cd perimeter-stack && docker compose config`

Expected:
- new tests PASS
- compose config renders without schema errors

- [ ] **Step 6: Commit**

```bash
git add docker/controlplane.Dockerfile perimeter-stack scripts/bootstrap-perimeter-stack.sh Makefile .gitignore tests/test_controlplane.py
git commit -m "Add SSO perimeter foundation stack"
```

### Task 2: Make Django perimeter-native and remove the old login UX

**Files:**
- Modify: `controlplane/core/settings.py`
- Modify: `controlplane/core/urls.py`
- Modify: `controlplane/domain/auth.py`
- Modify: `controlplane/domain/views.py`
- Modify: `controlplane/templates/admin/operator_base.html`
- Modify: `controlplane/templates/admin/operator_home.html`
- Modify: `scripts/controlplane-dev-server.sh`
- Test: `tests/test_controlplane.py`

- [ ] **Step 1: Write the failing tests for login redirects and perimeter URLs**

```python
def test_admin_login_redirects_into_sso(client):
    response = client.get("/admin/login/?next=/admin/", follow=False)

    assert response.status_code == 302
    assert response["Location"].startswith("/auth/login/")


def test_login_view_uses_authelia_redirect_target(client, settings):
    settings.AUTHELIA_LOGIN_URL = "http://auth.aquarium.local/?rd="
    response = client.get("/auth/login/?next=/admin/", follow=False)

    assert response.status_code == 302
    assert "auth.aquarium.local" in response["Location"]


def test_runtime_detail_grafana_link_uses_public_subdomain(client, admin_user):
    client.force_login(admin_user)
    response = client.get("/admin/runtimes/test-nullclaw/")

    assert response.status_code == 200
    assert "http://grafana.aquarium.local" in response.content.decode()
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `../../.venv/bin/pytest tests/test_controlplane.py -k "admin_login_redirects_into_sso or auth.aquarium.local or grafana_link_uses_public_subdomain" -v`
Expected: FAIL because `/admin/login/` still behaves like a local login surface and links still point at raw localhost URLs.

- [ ] **Step 3: Add perimeter-aware Django settings and redirects**

Implement the public URL settings and legacy login redirect:

```python
# controlplane/core/settings.py
CONTROLPLANE_PUBLIC_URL = os.environ.get("CONTROLPLANE_PUBLIC_URL", "http://app.aquarium.local")
GRAFANA_PUBLIC_URL = os.environ.get("GRAFANA_PUBLIC_URL", "http://grafana.aquarium.local")
INFISICAL_PUBLIC_URL = os.environ.get("INFISICAL_PUBLIC_URL", "http://secrets.aquarium.local")
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "app.aquarium.local"]
CSRF_TRUSTED_ORIGINS = ["http://app.aquarium.local"]
```

```python
# controlplane/core/urls.py
path("admin/login/", lambda request: redirect("/auth/login/?next=/admin/")),
```

Update `authelia_login_view()` so it always forwards the requested `next` value as the Authelia redirect target instead of rendering or redirecting to a local login form.

- [ ] **Step 4: Repoint UI links and local helper messaging**

Update views/templates so all user-facing links use the perimeter URLs:

```python
return {
    "controlplane_url": settings.CONTROLPLANE_PUBLIC_URL,
    "grafana_url": settings.GRAFANA_PUBLIC_URL,
    "secrets_url": settings.INFISICAL_PUBLIC_URL,
}
```

Update the local dev helper text:

```sh
echo "controlplane started behind perimeter at http://app.aquarium.local"
```

- [ ] **Step 5: Run tests**

Run:
- `../../.venv/bin/pytest tests/test_controlplane.py -k "login or public_subdomain or perimeter" -v`
- `../../.venv/bin/python -m django check --settings=controlplane.core.settings`

Expected:
- targeted Django tests PASS
- Django check reports no issues

- [ ] **Step 6: Commit**

```bash
git add controlplane/core/settings.py controlplane/core/urls.py controlplane/domain/auth.py controlplane/domain/views.py controlplane/templates/admin/operator_base.html controlplane/templates/admin/operator_home.html scripts/controlplane-dev-server.sh tests/test_controlplane.py
git commit -m "Make controlplane SSO perimeter native"
```

### Task 3: Move Grafana and Infisical behind the perimeter and remove direct UI ports

**Files:**
- Modify: `monitoring-stack/docker-compose.yml`
- Modify: `infisical-stack/docker-compose.yml`
- Modify: `perimeter-stack/Caddyfile`
- Modify: `perimeter-stack/docker-compose.yml`
- Modify: `scripts/bootstrap-monitoring-stack.sh`
- Test: `tests/test_controlplane.py`

- [ ] **Step 1: Write the failing tests for public URL rendering**

```python
def test_operator_home_does_not_render_loopback_grafana_url(client, admin_user):
    client.force_login(admin_user)
    response = client.get("/admin/")

    body = response.content.decode()
    assert "127.0.0.1:13000" not in body
    assert "grafana.aquarium.local" in body
```

- [ ] **Step 2: Run the focused test to verify it fails on current localhost assumptions**

Run: `../../.venv/bin/pytest tests/test_controlplane.py -k "does_not_render_loopback_grafana_url" -v`
Expected: FAIL if any template or view still emits direct Grafana loopback URLs.

- [ ] **Step 3: Attach Grafana and Infisical services to the perimeter network and drop their user-facing ports**

Modify the compose files so the UI services are internal upstreams:

```yaml
# monitoring-stack/docker-compose.yml
services:
  grafana:
    ports: []
    networks:
      - observability
      - perimeter

networks:
  observability:
    name: aquarium-monitoring
  perimeter:
    external: true
    name: aquarium-perimeter
```

```yaml
# infisical-stack/docker-compose.yml
services:
  backend:
    ports: []
    networks:
      - default
      - perimeter

networks:
  perimeter:
    external: true
    name: aquarium-perimeter
```

Update the Caddy routes:

```caddyfile
app.aquarium.local {
	forward_auth authelia:9091 {
		uri /api/authz/forward-auth
		copy_headers Remote-User Remote-Groups Remote-Name Remote-Email
	}
	reverse_proxy controlplane:8000 {
		header_up Remote-User {http.reverse_proxy.header.Remote-User}
	}
}

grafana.aquarium.local {
	forward_auth authelia:9091
	reverse_proxy grafana:3000 {
		header_up X-WEBAUTH-USER {http.reverse_proxy.header.Remote-User}
	}
}

secrets.aquarium.local {
	forward_auth authelia:9091
	reverse_proxy backend:8080
}
```

- [ ] **Step 4: Update bootstrap assumptions**

Adjust any bootstrap script that still assumes direct UI loopback access:

```sh
printf 'GRAFANA_PUBLIC_URL=%s\n' "http://grafana.aquarium.local"
printf 'INFISICAL_PUBLIC_URL=%s\n' "http://secrets.aquarium.local"
```

- [ ] **Step 5: Validate compose and routing assumptions**

Run:
- `cd monitoring-stack && docker compose config`
- `cd infisical-stack && docker compose config`
- `cd perimeter-stack && docker compose config`

Expected:
- all three compose files validate
- `grafana` and `backend` have no host-published UI ports

- [ ] **Step 6: Commit**

```bash
git add monitoring-stack/docker-compose.yml infisical-stack/docker-compose.yml perimeter-stack/Caddyfile perimeter-stack/docker-compose.yml scripts/bootstrap-monitoring-stack.sh tests/test_controlplane.py
git commit -m "Route Grafana and Infisical through SSO perimeter"
```

### Task 4: Update knowledge, operator workflows, and end-to-end verification

**Files:**
- Modify: `knowledge/README.md`
- Modify: `knowledge/controlplane.md`
- Modify: `knowledge/monitoring-stack.md`
- Modify: `knowledge/infisical-env-injection.md`
- Modify: `knowledge/nullclaw-operations.md`
- Modify: `knowledge/install-and-setup.md`
- Modify: `knowledge/admin-ui-testing-runbook.md`
- Modify: `Makefile`

- [ ] **Step 1: Write the failing documentation-oriented test as an assertion in existing control-plane tests**

```python
def test_public_surface_payload_uses_perimeter_urls():
    from orchestrator.service_layer import public_surface_payload

    payload = public_surface_payload()

    assert payload["app_url"] == "http://app.aquarium.local"
    assert payload["grafana_url"] == "http://grafana.aquarium.local"
    assert payload["secrets_url"] == "http://secrets.aquarium.local"
```

- [ ] **Step 2: Run the test to verify the service layer still lacks a unified public-surface contract**

Run: `../../.venv/bin/pytest tests/test_controlplane.py -k "public_surface_payload_uses_perimeter_urls" -v`
Expected: FAIL until the service layer exposes a perimeter-native public URL payload.

- [ ] **Step 3: Implement the service-layer payload and update docs**

Add a small service-layer helper with the explicit public URLs:

```python
def public_surface_payload() -> dict[str, str]:
    return {
        "app_url": os.environ.get("CONTROLPLANE_PUBLIC_URL", "http://app.aquarium.local"),
        "grafana_url": os.environ.get("GRAFANA_PUBLIC_URL", "http://grafana.aquarium.local"),
        "secrets_url": os.environ.get("INFISICAL_PUBLIC_URL", "http://secrets.aquarium.local"),
    }
```

Update the knowledge base so it no longer teaches direct UI entry:

```markdown
- Control plane: `http://app.aquarium.local`
- Grafana: `http://grafana.aquarium.local`
- Infisical: `http://secrets.aquarium.local`
- Direct localhost UI ports are no longer the supported operator path.
```

- [ ] **Step 4: Run the full verification set**

Run:
- `../../.venv/bin/pytest tests/test_controlplane.py -q`
- `../../.venv/bin/python -m django check --settings=controlplane.core.settings`
- `make lint`
- `cd perimeter-stack && docker compose config`
- `cd monitoring-stack && docker compose config`
- `cd infisical-stack && docker compose config`

Expected:
- tests PASS
- Django check clean
- lint PASS
- all compose configs render

- [ ] **Step 5: Commit**

```bash
git add knowledge/README.md knowledge/controlplane.md knowledge/monitoring-stack.md knowledge/infisical-env-injection.md knowledge/nullclaw-operations.md knowledge/install-and-setup.md knowledge/admin-ui-testing-runbook.md Makefile orchestrator/service_layer.py tests/test_controlplane.py
git commit -m "Document SSO perimeter operator workflow"
```
