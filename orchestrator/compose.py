from __future__ import annotations

from pathlib import Path

import yaml

from orchestrator.infisical import read_env_file
from orchestrator.models import RuntimeRecord, StateFile
from orchestrator.paths import COMPOSE_FILE, COMPOSE_PROJECT_NAME, MONITORING_STACK_ENV_FILE, ROOT_DIR


NULLCLAW_IMAGE_CONTEXT = str(ROOT_DIR)
NULLCLAW_DOCKERFILE = str(ROOT_DIR / "docker" / "nullclaw-infisical.Dockerfile")
SCRIPTS_DIR = str(ROOT_DIR / "scripts")
MONITORING_NETWORK_NAME = "aquarium-monitoring"


def _monitoring_network_enabled() -> bool:
    values = read_env_file(MONITORING_STACK_ENV_FILE)
    return bool(values.get("INFISICAL_PROJECT_ID") and values.get("INFISICAL_TOKEN"))


def _base_service(runtime: RuntimeRecord) -> dict:
    service = {
        "build": {
            "context": NULLCLAW_IMAGE_CONTEXT,
            "dockerfile": NULLCLAW_DOCKERFILE,
        },
        "entrypoint": ["/opt/aquarium-scripts/nullclaw-infisical-entrypoint.sh"],
        "env_file": [runtime.runtime_env_file],
        "environment": {
            "INFISICAL_DISABLE_UPDATE_CHECK": "true",
            "NULLCLAW_HOME": "/nullclaw-data",
            "NULLCLAW_RENDER_CONFIG_SCRIPT": "/opt/aquarium-scripts/render-nullclaw-config.sh",
        },
        "volumes": [
            f"{SCRIPTS_DIR}:/opt/aquarium-scripts:ro",
            f"{runtime.runtime_home}:/nullclaw-data",
        ],
    }
    if _monitoring_network_enabled():
        service["networks"] = ["default", "observability"]
    return service


def gateway_service(runtime: RuntimeRecord) -> dict:
    service = _base_service(runtime)
    service.update(
        {
            "command": ["gateway", "--host", "::"],
            "ports": [f"127.0.0.1:{runtime.gateway_port}:{runtime.gateway_port}"],
            "restart": "unless-stopped",
            "healthcheck": {
                "test": ["CMD", "wget", "-qO-", f"http://127.0.0.1:{runtime.gateway_port}/health"],
                "interval": "30s",
                "timeout": "5s",
                "retries": 10,
            },
        }
    )
    return service


def agent_service(runtime: RuntimeRecord) -> dict:
    service = _base_service(runtime)
    service.update({"command": ["agent"]})
    return service


def render_compose(state: StateFile) -> dict:
    services: dict[str, dict] = {}
    for runtime_id in sorted(state.runtimes):
        runtime = state.runtimes[runtime_id]
        services[f"gateway-{runtime.id}"] = gateway_service(runtime)
        services[f"agent-{runtime.id}"] = agent_service(runtime)
    payload = {"name": COMPOSE_PROJECT_NAME, "services": services}
    if _monitoring_network_enabled():
        payload["networks"] = {
            "observability": {
                "external": True,
                "name": MONITORING_NETWORK_NAME,
            }
        }
    return payload


def write_compose(state: StateFile) -> Path:
    COMPOSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = render_compose(state)
    COMPOSE_FILE.write_text(yaml.safe_dump(payload, sort_keys=False))
    return COMPOSE_FILE
