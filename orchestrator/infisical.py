from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

from orchestrator.paths import INFISICAL_STACK_ENV_FILE
from orchestrator.shell import CommandError, run


class InfisicalError(RuntimeError):
    pass


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def default_api_url() -> str:
    if os.environ.get("INFISICAL_API_URL"):
        return os.environ["INFISICAL_API_URL"]
    env_file = read_env_file(INFISICAL_STACK_ENV_FILE)
    if env_file.get("INFISICAL_API_URL"):
        return env_file["INFISICAL_API_URL"]
    return "http://127.0.0.1:18080"


def operator_token(api_url: str) -> str:
    if os.environ.get("INFISICAL_OPERATOR_TOKEN"):
        return os.environ["INFISICAL_OPERATOR_TOKEN"]
    try:
        return run(
            ["infisical", "user", "get", "token", "--plain"],
            env={"INFISICAL_API_URL": api_url},
        )
    except CommandError as exc:
        raise InfisicalError(
            "No usable Infisical operator token found. Run `INFISICAL_API_URL=... infisical login` first or export INFISICAL_OPERATOR_TOKEN."
        ) from exc


def api_request(
    api_url: str,
    token: str,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    expected: tuple[int, ...] = (200,),
) -> requests.Response:
    url = f"{api_url.rstrip('/')}{path}"
    response = requests.request(
        method=method,
        url=url,
        headers={"Authorization": f"Bearer {token}"},
        json=json_body,
        params=params,
        timeout=20,
    )
    if response.status_code not in expected:
        raise InfisicalError(
            f"Infisical {method} {path} failed with {response.status_code}: {response.text.strip()}"
        )
    return response


def ensure_project(api_url: str, token: str, slug: str) -> dict[str, str]:
    projects = api_request(api_url, token, "GET", "/api/v1/projects").json()["projects"]
    for project in projects:
        if project["slug"] == slug:
            return {"id": project["id"], "slug": project["slug"]}
    payload = {
        "projectName": slug,
        "slug": slug,
        "type": "secret-manager",
        "shouldCreateDefaultEnvs": True,
        "hasDeleteProtection": False,
    }
    created = api_request(
        api_url,
        token,
        "POST",
        "/api/v1/projects",
        json_body=payload,
        expected=(200, 201),
    ).json()["project"]
    return {"id": created["id"], "slug": created["slug"]}


def ensure_secret_path(api_url: str, token: str, project_id: str, env_slug: str, secret_path: str) -> None:
    normalized = secret_path.strip()
    if normalized in ("", "/"):
        return

    current_path = "/"
    parts = [part for part in normalized.split("/") if part]
    for part in parts:
        payload = {
            "projectId": project_id,
            "environment": env_slug,
            "name": part,
            "path": current_path,
        }
        response = requests.post(
            f"{api_url.rstrip('/')}/api/v2/folders",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=20,
        )
        if response.status_code not in (200, 201, 400, 409):
            raise InfisicalError(
                f"Infisical failed to ensure folder {normalized} with {response.status_code}: {response.text.strip()}"
            )
        current_path = "/" if current_path == "/" else current_path.rstrip("/")
        current_path = f"{current_path}/{part}".replace("//", "/")


def upsert_secret(api_url: str, token: str, project_id: str, env_slug: str, secret_path: str, name: str, value: str) -> None:
    ensure_secret_path(api_url, token, project_id, env_slug, secret_path)
    payload = {
        "projectId": project_id,
        "environment": env_slug,
        "secretValue": value,
        "secretPath": secret_path,
        "type": "shared",
        "skipMultilineEncoding": True,
    }
    try:
        api_request(
            api_url,
            token,
            "POST",
            f"/api/v4/secrets/{name}",
            json_body=payload,
            expected=(200, 201),
        )
    except InfisicalError:
        api_request(
            api_url,
            token,
            "PATCH",
            f"/api/v4/secrets/{name}",
            json_body=payload,
            expected=(200, 201),
        )


def create_service_token(api_url: str, project_id: str, runtime_id: str, env_slug: str, secret_path: str) -> str:
    return run(
        [
            "infisical",
            "service-token",
            "create",
            "--projectId",
            project_id,
            "--name",
            f"{runtime_id}-runtime-token",
            "--access-level",
            "read",
            "--scope",
            f"{env_slug}:{secret_path}",
            "--expiry-seconds",
            "0",
            "--token-only",
        ],
        env={"INFISICAL_API_URL": api_url},
    )


def read_secret_with_token(api_url: str, token: str, project_id: str, env_slug: str, secret_path: str, name: str) -> str:
    response = api_request(
        api_url,
        token,
        "GET",
        f"/api/v4/secrets/{name}",
        params={
            "projectId": project_id,
            "environment": env_slug,
            "secretPath": secret_path,
            "type": "shared",
        },
        expected=(200,),
    )
    data = response.json()
    if isinstance(data, dict):
        if "secret" in data and isinstance(data["secret"], dict):
            secret = data["secret"]
            if "secretValue" in secret:
                return str(secret["secretValue"])
        if "secretValue" in data:
            return str(data["secretValue"])
    raise InfisicalError(f"Unexpected secret payload for {name}: {json.dumps(data)}")
