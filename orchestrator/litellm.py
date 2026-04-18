from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from urllib.parse import urlparse, urlunparse

from orchestrator.infisical import default_api_url, ensure_project, operator_token, read_env_file, read_secret_with_token
from orchestrator.paths import (
    INFISICAL_STACK_ENV_FILE,
    LITELLM_PRICING_CACHE_FILE,
    LITELLM_STACK_CONFIG_FILE,
    LITELLM_STACK_ENV_FILE,
)


OPENROUTER_PRICING_URL = "https://openrouter.ai/qwen/qwen3.6-plus/pricing"
DEFAULT_LITELLM_BASE_URL = "http://127.0.0.1:14000"
DEFAULT_RUNTIME_LITELLM_BASE_URL = "http://host.docker.internal:14000/v1"
DEFAULT_MODEL_ALIAS = "openai/qwen/qwen3.6-plus"
DEFAULT_PROVIDER_MODEL = "openrouter/qwen/qwen3.6-plus"


class LiteLLMError(RuntimeError):
    pass


@dataclass
class PriceInfo:
    model: str
    input_per_million_usd: float
    output_per_million_usd: float
    source_url: str = OPENROUTER_PRICING_URL


def default_base_url() -> str:
    if os.environ.get("LITELLM_API_URL"):
        return os.environ["LITELLM_API_URL"]
    env_file = read_env_file(LITELLM_STACK_ENV_FILE)
    if env_file.get("LITELLM_API_URL"):
        return env_file["LITELLM_API_URL"]
    return DEFAULT_LITELLM_BASE_URL


def runtime_base_url() -> str:
    if os.environ.get("LITELLM_RUNTIME_BASE_URL"):
        return os.environ["LITELLM_RUNTIME_BASE_URL"]
    env_file = read_env_file(LITELLM_STACK_ENV_FILE)
    if env_file.get("LITELLM_RUNTIME_BASE_URL"):
        return env_file["LITELLM_RUNTIME_BASE_URL"]
    return DEFAULT_RUNTIME_LITELLM_BASE_URL


def containerized_api_url(api_url: str) -> str:
    parsed = urlparse(api_url)
    if parsed.hostname in {"127.0.0.1", "localhost"}:
        netloc = parsed.netloc.replace(parsed.hostname or "", "host.docker.internal", 1)
        return urlunparse(parsed._replace(netloc=netloc))
    return api_url


def _request(
    base_url: str,
    method: str,
    path: str,
    *,
    api_key: str | None = None,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    expected: tuple[int, ...] = (200,),
    timeout: int = 20,
) -> requests.Response:
    url = f"{base_url.rstrip('/')}{path}"
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["x-litellm-api-key"] = api_key
    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        json=json_body,
        params=params,
        timeout=timeout,
    )
    if response.status_code not in expected:
        raise LiteLLMError(f"LiteLLM {method} {path} failed with {response.status_code}: {response.text.strip()}")
    return response


def status(base_url: str) -> dict[str, Any]:
    response = requests.get(f"{base_url.rstrip('/')}/health/liveliness", timeout=10)
    response.raise_for_status()
    return response.json()


def master_key_from_infisical(infisical_api_url: str) -> str:
    token = operator_token(infisical_api_url)
    project = ensure_project(infisical_api_url, token, "litellm-core")
    return read_secret_with_token(infisical_api_url, token, project["id"], "prod", "/runtime", "LITELLM_MASTER_KEY")


def ensure_core_secrets(infisical_api_url: str) -> dict[str, str]:
    token = operator_token(infisical_api_url)
    project = ensure_project(infisical_api_url, token, "litellm-core")
    values = {
        "project_id": project["id"],
        "project_slug": project["slug"],
        "master_key": read_secret_with_token(
            infisical_api_url, token, project["id"], "prod", "/runtime", "LITELLM_MASTER_KEY"
        ),
        "openrouter_api_key": read_secret_with_token(
            infisical_api_url, token, project["id"], "prod", "/runtime", "OPENROUTER_API_KEY"
        ),
    }
    return values


def fetch_qwen_price_info(url: str = OPENROUTER_PRICING_URL, timeout: int = 20) -> PriceInfo:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    content = response.text
    match = re.search(r"\$(?P<input>[0-9.]+)/M input tokens\s*\$(?P<output>[0-9.]+)/M output tokens", content)
    if not match:
        raise LiteLLMError(f"Could not parse pricing from {url}")
    info = PriceInfo(
        model="qwen/qwen3.6-plus",
        input_per_million_usd=float(match.group("input")),
        output_per_million_usd=float(match.group("output")),
        source_url=url,
    )
    cache_price_info(info)
    return info


def cache_price_info(info: PriceInfo) -> None:
    LITELLM_PRICING_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": info.model,
        "input_per_million_usd": info.input_per_million_usd,
        "output_per_million_usd": info.output_per_million_usd,
        "source_url": info.source_url,
    }
    LITELLM_PRICING_CACHE_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_cached_price_info() -> PriceInfo | None:
    if not LITELLM_PRICING_CACHE_FILE.exists():
        return None
    payload = json.loads(LITELLM_PRICING_CACHE_FILE.read_text())
    return PriceInfo(
        model=str(payload["model"]),
        input_per_million_usd=float(payload["input_per_million_usd"]),
        output_per_million_usd=float(payload["output_per_million_usd"]),
        source_url=str(payload["source_url"]),
    )


def get_price_info() -> PriceInfo:
    try:
        return fetch_qwen_price_info()
    except Exception:
        cached = load_cached_price_info()
        if cached:
            return cached
        return PriceInfo(model="qwen/qwen3.6-plus", input_per_million_usd=0.325, output_per_million_usd=1.95)


def create_virtual_key(
    base_url: str,
    master_key: str,
    *,
    key_alias: str,
    model_aliases: list[str],
    budget_usd: float | None,
    rpm_limit: int | None,
    tpm_limit: int | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key_alias": key_alias,
        "models": model_aliases,
        "metadata": metadata,
        "duration": None,
    }
    if budget_usd is not None:
        payload["max_budget"] = budget_usd
    if rpm_limit is not None:
        payload["rpm_limit"] = rpm_limit
    if tpm_limit is not None:
        payload["tpm_limit"] = tpm_limit
    response = _request(
        base_url,
        "POST",
        "/key/generate",
        api_key=master_key,
        json_body=payload,
        expected=(200,),
    )
    return response.json()


def update_virtual_key(
    base_url: str,
    master_key: str,
    *,
    key: str | None = None,
    key_alias: str | None = None,
    budget_usd: float | None,
    rpm_limit: int | None,
    tpm_limit: int | None,
    model_aliases: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if key is not None:
        payload["key"] = key
    if key_alias is not None:
        payload["key_alias"] = key_alias
    if budget_usd is not None:
        payload["max_budget"] = budget_usd
    if rpm_limit is not None:
        payload["rpm_limit"] = rpm_limit
    if tpm_limit is not None:
        payload["tpm_limit"] = tpm_limit
    if model_aliases is not None:
        payload["models"] = model_aliases
    if metadata is not None:
        payload["metadata"] = metadata
    response = _request(
        base_url,
        "POST",
        "/key/update",
        api_key=master_key,
        json_body=payload,
        expected=(200,),
    )
    return response.json()


def delete_virtual_key(base_url: str, master_key: str, *, key: str | None = None, key_alias: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if key is not None:
        payload["keys"] = [key]
    elif key_alias is not None:
        payload["key_aliases"] = [key_alias]
    else:
        raise LiteLLMError("delete_virtual_key requires key or key_alias")
    response = _request(
        base_url,
        "POST",
        "/key/delete",
        api_key=master_key,
        json_body=payload,
        expected=(200,),
    )
    return response.json()


def info_for_virtual_key(base_url: str, master_key: str, *, key: str) -> dict[str, Any]:
    response = _request(
        base_url,
        "GET",
        "/key/info",
        api_key=master_key,
        params={"key": key},
        expected=(200,),
    )
    return response.json()


def usage_by_key(base_url: str, master_key: str, *, key_alias: str) -> dict[str, Any]:
    response = _request(
        base_url,
        "GET",
        "/key/info",
        api_key=master_key,
        params={"key_alias": key_alias},
        expected=(200,),
    )
    return response.json()


def random_master_key() -> str:
    return f"sk-aquarium-{secrets.token_urlsafe(24)}"


def litellm_stack_env_defaults() -> dict[str, str]:
    infisical_env = read_env_file(INFISICAL_STACK_ENV_FILE)
    api_url = infisical_env.get("INFISICAL_API_URL", default_api_url())
    return {
        "LITELLM_API_URL": DEFAULT_LITELLM_BASE_URL,
        "LITELLM_RUNTIME_BASE_URL": DEFAULT_RUNTIME_LITELLM_BASE_URL,
        "INFISICAL_API_URL": containerized_api_url(api_url),
        "INFISICAL_ENV": "prod",
        "INFISICAL_PATH": "/runtime",
        "LITELLM_PORT": "14000",
        "LITELLM_DB_PORT": "15432",
        "LITELLM_DB_NAME": "litellm",
        "LITELLM_DB_USER": "litellm",
        "LITELLM_DB_PASSWORD": secrets.token_urlsafe(18),
    }


def write_stack_env(values: dict[str, str]) -> Path:
    env_path = LITELLM_STACK_ENV_FILE
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    return env_path


def render_stack_config(price: PriceInfo | None = None, *, extra_models: list[dict[str, Any]] | None = None) -> str:
    pricing = price or get_price_info()
    input_cost_per_token = pricing.input_per_million_usd / 1_000_000
    output_cost_per_token = pricing.output_per_million_usd / 1_000_000
    model_entries = [
        {
            "model_name": DEFAULT_MODEL_ALIAS,
            "litellm_params": {
                "model": DEFAULT_PROVIDER_MODEL,
                "api_key": "os.environ/OPENROUTER_API_KEY",
            },
            "model_info": {
                "input_cost_per_token": float(f"{input_cost_per_token:.12f}"),
                "output_cost_per_token": float(f"{output_cost_per_token:.12f}"),
            },
        }
    ]
    if extra_models:
        model_entries.extend(extra_models)
    deduped_entries: list[dict[str, Any]] = []
    seen_model_names: set[str] = set()
    for entry in model_entries:
        model_name = str(entry["model_name"])
        if model_name in seen_model_names:
            continue
        seen_model_names.add(model_name)
        deduped_entries.append(entry)
    lines = ["model_list:"]
    for entry in deduped_entries:
        lines.append(f"  - model_name: {entry['model_name']}")
        lines.append("    litellm_params:")
        for key, value in entry["litellm_params"].items():
            lines.append(f"      {key}: {value}")
        model_info = entry.get("model_info") or {}
        if model_info:
            lines.append("    model_info:")
            for key, value in model_info.items():
                lines.append(f"      {key}: {value}")
    lines.extend(
        [
            "",
            "litellm_settings:",
            "  master_key: os.environ/LITELLM_MASTER_KEY",
            "  database_url: os.environ/DATABASE_URL",
            "  set_verbose: true",
            "  ui_access_mode: all",
            "",
            "general_settings:",
            "  store_prompts_in_spend_logs: true",
            "",
        ]
    )
    return "\n".join(lines)


def write_stack_config(price: PriceInfo | None = None, *, extra_models: list[dict[str, Any]] | None = None) -> Path:
    config_path = LITELLM_STACK_CONFIG_FILE
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(render_stack_config(price, extra_models=extra_models))
    return config_path
