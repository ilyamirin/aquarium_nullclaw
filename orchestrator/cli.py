from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from shutil import which
from urllib.parse import urlparse, urlunparse

import requests
import typer

from orchestrator.compose import write_compose
from orchestrator.infisical import (
    InfisicalError,
    create_service_token,
    default_api_url,
    delete_secret,
    ensure_project,
    operator_token,
    read_env_file,
    read_secret_with_token,
    upsert_secret,
)
from orchestrator.litellm import (
    DEFAULT_MODEL_ALIAS,
    DEFAULT_PROVIDER_MODEL,
    LiteLLMError,
    create_virtual_key,
    containerized_api_url,
    default_base_url as default_litellm_base_url,
    delete_virtual_key,
    ensure_core_secrets,
    fetch_qwen_price_info,
    get_price_info,
    info_for_virtual_key,
    litellm_stack_env_defaults,
    load_cached_price_info,
    master_key_from_infisical,
    random_master_key,
    runtime_base_url,
    status as litellm_status,
    update_virtual_key,
    write_stack_config,
    write_stack_env,
)
from orchestrator.models import RuntimeRecord
from orchestrator.paths import COMPOSE_FILE, COMPOSE_PROJECT_NAME, LITELLM_STACK_ENV_FILE, MONITORING_STACK_ENV_FILE, runtime_dir, runtime_env_file, runtime_home, workspace_dir
from orchestrator.shell import CommandError, run
from orchestrator.service_layer import (
    RuntimeCreateRequest,
    create_or_update_runtime,
    delete_runtime_service,
    import_json_state_if_empty,
    inspect_runtime_key,
    list_runtime_lines,
    read_runtime_limits,
    recreate_runtime,
    revoke_runtime_key,
    rotate_runtime_key,
    runtime_probe_check as runtime_probe_check_service,
    runtime_status_payload,
    smoke_test_runtime,
    start_runtime,
    stop_runtime,
    sync_runtime_limits,
    update_runtime_limits,
)
from orchestrator.state import delete_runtime, ensure_local_layout, load_state, save_state, upsert_runtime


app = typer.Typer(no_args_is_help=True, help="Aquarium control plane for NullClaw runtimes.")
runtime_app = typer.Typer(no_args_is_help=True, help="Manage hosted NullClaw runtimes.")
litellm_app = typer.Typer(no_args_is_help=True, help="Manage the LiteLLM gateway.")
app.add_typer(runtime_app, name="runtime")
app.add_typer(litellm_app, name="litellm")

NULLCLAW_MAX_ACTIONS_PER_HOUR = "1000000"


def _require_venv() -> None:
    expected = str(Path.cwd() / ".venv")
    if not sys.executable.startswith(expected):
        raise typer.BadParameter(f"Run the orchestrator from the repo-local .venv. Current Python: {sys.executable}")
    if sys.version_info[:2] != (3, 12):
        raise typer.BadParameter(f"Python 3.12 is required. Current version: {sys.version.split()[0]}")


def _ensure_tool(name: str) -> None:
    if which(name) is None:
        raise typer.BadParameter(f"Required tool is missing from PATH: {name}")


def _env_dict(path: str) -> dict[str, str]:
    return {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in Path(path).read_text().splitlines()
        if "=" in line
    }


def _host_api_url(api_url: str) -> str:
    parsed = urlparse(api_url)
    if parsed.hostname == "host.docker.internal":
        netloc = parsed.netloc.replace("host.docker.internal", "127.0.0.1", 1)
        return urlunparse(parsed._replace(netloc=netloc))
    return api_url


def _compose_cmd(*args: str) -> list[str]:
    return ["docker", "compose", "-f", str(COMPOSE_FILE), *args]


def _role_defaults(runtime_id: str) -> tuple[str, int | None, int | None]:
    if runtime_id == "test-nullclaw":
        return ("live", 180, 400_000)
    if runtime_id == "probe":
        return ("probe", 10, 20_000)
    if runtime_id == "limit-probe":
        return ("limit-probe", 1, 20_000)
    return ("custom", 30, 60_000)


def _budget_for_role(runtime_role: str) -> float | None:
    if runtime_role == "live":
        return 10.0
    if runtime_role == "probe":
        return 0.05
    if runtime_role == "limit-probe":
        pricing = get_price_info()
        return round(((50 * pricing.input_per_million_usd) + (20 * pricing.output_per_million_usd)) / 1_000_000, 8)
    return 0.10


def _runtime_api_url(api_url: str) -> str:
    override = os.environ.get("INFISICAL_RUNTIME_API_URL")
    if override:
        return override
    parsed = urlparse(api_url)
    if parsed.hostname in {"127.0.0.1", "localhost"}:
        netloc = parsed.netloc.replace(parsed.hostname or "", "host.docker.internal", 1)
        return urlunparse(parsed._replace(netloc=netloc))
    return api_url


def _monitoring_runtime_env(monitoring_env_file: Path | None = None) -> dict[str, str]:
    env_file = monitoring_env_file or MONITORING_STACK_ENV_FILE
    values = read_env_file(env_file)
    if not values.get("INFISICAL_PROJECT_ID") or not values.get("INFISICAL_TOKEN"):
        return {}
    otlp_port = values.get("OTLP_HTTP_PORT", "4318")
    return {
        "NULLCLAW_OTEL_ENABLED": "true",
        "NULLCLAW_OTEL_ENDPOINT": f"http://alloy.local:{otlp_port}",
        "NULLCLAW_OTEL_SERVICE_NAME": f"nullclaw-{values.get('RUNTIME_ID', '<runtime-id>')}",
    }


def _write_runtime_env(runtime: RuntimeRecord, service_token: str, api_url: str) -> None:
    env_path = Path(runtime.runtime_env_file)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_api_url = _runtime_api_url(api_url)
    values = {
        "INFISICAL_API_URL": runtime_api_url,
        "INFISICAL_ENV": runtime.infisical_env,
        "INFISICAL_PATH": runtime.infisical_path,
        "INFISICAL_PROJECT_ID": runtime.infisical_project_id,
        "INFISICAL_TOKEN": service_token,
        "NULLCLAW_ENABLE_TELEGRAM": "true" if runtime.telegram_enabled else "false",
        "NULLCLAW_MODEL": runtime.model,
        "NULLCLAW_GATEWAY_HOST": "127.0.0.1",
        "NULLCLAW_GATEWAY_PORT": str(runtime.gateway_port),
        "NULLCLAW_REQUIRE_PAIRING": "true",
        "NULLCLAW_AUTONOMY_LEVEL": "supervised",
        "NULLCLAW_WORKSPACE_ONLY": "true",
        "NULLCLAW_MAX_ACTIONS_PER_HOUR": NULLCLAW_MAX_ACTIONS_PER_HOUR,
        "NULLCLAW_LOG_TOOL_CALLS": "true",
        "NULLCLAW_LOG_MESSAGE_RECEIPTS": "true",
        "NULLCLAW_LOG_MESSAGE_PAYLOADS": "true",
        "NULLCLAW_LOG_LLM_IO": "true",
        "NULLCLAW_TOKEN_USAGE_LEDGER_ENABLED": "true",
        "LITELLM_BASE_URL": runtime_base_url(),
    }
    monitoring_values = _monitoring_runtime_env()
    if monitoring_values:
        monitoring_values["NULLCLAW_OTEL_SERVICE_NAME"] = f"nullclaw-{runtime.id}"
        values.update(monitoring_values)
    env_path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")


def _runtime_record(
    *,
    runtime_id: str,
    gateway_port: int,
    telegram_enabled: bool,
    model: str,
    runtime_role: str,
    project_slug: str,
    project_id: str,
    litellm_key_name: str,
    litellm_budget_usd: float | None,
    litellm_rpm_limit: int | None,
    litellm_tpm_limit: int | None,
    tenant_id: str | None,
    plan_id: str | None,
) -> RuntimeRecord:
    runtime_home_path = runtime_home(runtime_id)
    workspace_path = workspace_dir(runtime_id)
    env_path = runtime_env_file(runtime_id)
    runtime_home_path.mkdir(parents=True, exist_ok=True)
    workspace_path.mkdir(parents=True, exist_ok=True)
    pricing = load_cached_price_info() or get_price_info()
    return RuntimeRecord(
        id=runtime_id,
        enabled=True,
        gateway_port=gateway_port,
        telegram_enabled=telegram_enabled,
        model=model,
        runtime_role=runtime_role,
        tenant_id=tenant_id,
        plan_id=plan_id,
        infisical_project_slug=project_slug,
        infisical_project_id=project_id,
        infisical_env="prod",
        infisical_path="/runtime",
        litellm_key_name=litellm_key_name,
        litellm_budget_usd=litellm_budget_usd,
        litellm_rpm_limit=litellm_rpm_limit,
        litellm_tpm_limit=litellm_tpm_limit,
        litellm_model_alias=model,
        litellm_price_input_per_million_usd=pricing.input_per_million_usd,
        litellm_price_output_per_million_usd=pricing.output_per_million_usd,
        runtime_env_file=str(env_path),
        runtime_home=str(runtime_home_path),
        workspace_dir=str(workspace_path),
        generated_config_path=str(runtime_home_path / "config.json"),
    )


def _up_runtime(runtime_id: str) -> None:
    run(_compose_cmd("up", "-d", "--force-recreate", f"gateway-{runtime_id}"), cwd=str(Path.cwd()))


def _current_runtime_key(api_url: str, runtime: RuntimeRecord) -> str | None:
    try:
        token = operator_token(api_url)
        return read_secret_with_token(
            api_url,
            token,
            runtime.infisical_project_id,
            runtime.infisical_env,
            runtime.infisical_path,
            "LITELLM_API_KEY",
        )
    except InfisicalError:
        return None


def _ensure_litellm_available(api_url: str, base_url: str) -> None:
    ensure_core_secrets(api_url)
    try:
        litellm_status(base_url)
    except Exception as exc:
        raise typer.Exit(f"LiteLLM is not reachable at {base_url}: {exc}") from exc


def _provision_litellm_key(
    *,
    runtime_id: str,
    runtime_role: str,
    model: str,
    budget_usd: float | None,
    rpm_limit: int | None,
    tpm_limit: int | None,
    tenant_id: str | None,
    plan_id: str | None,
    base_url: str,
    infisical_api_url: str,
) -> dict[str, str]:
    master_key = master_key_from_infisical(infisical_api_url)
    metadata = {
        "runtime_id": runtime_id,
        "runtime_role": runtime_role,
        "tenant_id": tenant_id,
        "plan_id": plan_id,
        "managed_by": "aquarium-orchestrator",
    }
    created = create_virtual_key(
        base_url,
        master_key,
        key_alias=f"runtime-{runtime_id}",
        model_aliases=[model],
        budget_usd=budget_usd,
        rpm_limit=rpm_limit,
        tpm_limit=tpm_limit,
        metadata=metadata,
    )
    key_value = created.get("key") or created.get("token") or created.get("virtual_key")
    if not isinstance(key_value, str) or not key_value:
        raise typer.Exit(f"LiteLLM key creation returned an unexpected payload: {json.dumps(created)}")
    return {"key": key_value, "key_name": f"runtime-{runtime_id}"}


def _cleanup_legacy_provider_secret(api_url: str, runtime: RuntimeRecord) -> None:
    token = operator_token(api_url)
    delete_secret(
        api_url,
        token,
        runtime.infisical_project_id,
        runtime.infisical_env,
        runtime.infisical_path,
        "OPENROUTER_API_KEY",
    )


def _save_runtime_secret(api_url: str, runtime: RuntimeRecord, name: str, value: str) -> None:
    token = operator_token(api_url)
    upsert_secret(api_url, token, runtime.infisical_project_id, runtime.infisical_env, runtime.infisical_path, name, value)


def _read_runtime_secret_or_empty(api_url: str, project_id: str, env_slug: str, secret_path: str, name: str) -> str:
    try:
        return read_secret_with_token(api_url, operator_token(api_url), project_id, env_slug, secret_path, name)
    except InfisicalError:
        return ""


def _build_runtime(
    *,
    runtime_id: str,
    gateway_port: int,
    model: str,
    telegram_enabled: bool,
    telegram_bot_token: str,
    telegram_allow_from: str,
    runtime_role: str | None,
    budget_usd: float | None,
    rpm_limit: int | None,
    tpm_limit: int | None,
    tenant_id: str | None,
    plan_id: str | None,
    api_url: str,
    litellm_base_url: str,
) -> RuntimeRecord:
    state = load_state()
    _ensure_litellm_available(api_url, litellm_base_url)

    default_role, default_rpm, default_tpm = _role_defaults(runtime_id)
    resolved_role = runtime_role or default_role
    resolved_budget = budget_usd if budget_usd is not None else _budget_for_role(resolved_role)
    resolved_rpm = rpm_limit if rpm_limit is not None else default_rpm
    resolved_tpm = tpm_limit if tpm_limit is not None else default_tpm

    token = operator_token(api_url)
    project = ensure_project(api_url, token, runtime_id)
    if telegram_enabled and not telegram_bot_token:
        telegram_bot_token = _read_runtime_secret_or_empty(api_url, project["id"], "prod", "/runtime", "TELEGRAM_BOT_TOKEN")
    if telegram_enabled and not telegram_allow_from:
        telegram_allow_from = _read_runtime_secret_or_empty(api_url, project["id"], "prod", "/runtime", "TELEGRAM_ALLOW_FROM")
    runtime = _runtime_record(
        runtime_id=runtime_id,
        gateway_port=gateway_port,
        telegram_enabled=telegram_enabled,
        model=model,
        runtime_role=resolved_role,
        project_slug=project["slug"],
        project_id=project["id"],
        litellm_key_name=f"runtime-{runtime_id}",
        litellm_budget_usd=resolved_budget,
        litellm_rpm_limit=resolved_rpm,
        litellm_tpm_limit=resolved_tpm,
        tenant_id=tenant_id,
        plan_id=plan_id,
    )

    current_key = _current_runtime_key(api_url, runtime)
    if current_key:
        try:
            delete_virtual_key(litellm_base_url, master_key_from_infisical(api_url), key=current_key)
        except LiteLLMError:
            pass

    provisioned = _provision_litellm_key(
        runtime_id=runtime.id,
        runtime_role=runtime.runtime_role,
        model=runtime.model,
        budget_usd=runtime.litellm_budget_usd,
        rpm_limit=runtime.litellm_rpm_limit,
        tpm_limit=runtime.litellm_tpm_limit,
        tenant_id=runtime.tenant_id,
        plan_id=runtime.plan_id,
        base_url=litellm_base_url,
        infisical_api_url=api_url,
    )
    _save_runtime_secret(api_url, runtime, "LITELLM_API_KEY", provisioned["key"])
    if telegram_enabled:
        _save_runtime_secret(api_url, runtime, "TELEGRAM_BOT_TOKEN", telegram_bot_token)
        _save_runtime_secret(api_url, runtime, "TELEGRAM_ALLOW_FROM", telegram_allow_from)
    _cleanup_legacy_provider_secret(api_url, runtime)

    service_token = create_service_token(api_url, project["id"], runtime.id, runtime.infisical_env, runtime.infisical_path)
    _write_runtime_env(runtime, service_token, api_url)

    state = upsert_runtime(state, runtime)
    save_state(state)
    write_compose(state)
    _up_runtime(runtime.id)
    return runtime


@app.command()
def init(
    api_url: str = typer.Option(default_factory=default_api_url, help="Infisical API URL."),
    litellm_base_url: str = typer.Option(default_factory=default_litellm_base_url, help="LiteLLM base URL."),
) -> None:
    """Verify local prerequisites and initialize state directories."""
    _require_venv()
    _ensure_tool("docker")
    _ensure_tool("infisical")
    run(["docker", "compose", "version"])
    run(["infisical", "--version"], env={"INFISICAL_API_URL": api_url})
    ensure_local_layout()
    try:
        response = requests.get(f"{api_url.rstrip('/')}/api/status", timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise typer.Exit(f"Infisical is not reachable at {api_url}: {exc}") from exc
    try:
        litellm_status(litellm_base_url)
        litellm_state = "reachable"
    except Exception:
        litellm_state = "not-yet-running"
    typer.echo(f"Initialized orchestrator state under {Path.cwd() / '.aquarium'}")
    typer.echo(f"Compose project: {COMPOSE_PROJECT_NAME}")
    typer.echo(f"LiteLLM: {litellm_state}")


@litellm_app.command("bootstrap")
def litellm_bootstrap(
    api_url: str = typer.Option(default_factory=default_api_url, help="Infisical API URL."),
    openrouter_api_key: str = typer.Option("", envvar="OPENROUTER_API_KEY", help="OpenRouter API key."),
    master_key: str = typer.Option("", envvar="LITELLM_MASTER_KEY", help="LiteLLM master key."),
) -> None:
    """Create or refresh LiteLLM core secrets in Infisical and write litellm-stack/.env."""
    _require_venv()
    ensure_local_layout()
    token = operator_token(api_url)
    project = ensure_project(api_url, token, "litellm-core")

    if not openrouter_api_key:
        try:
            openrouter_api_key = read_secret_with_token(
                api_url,
                token,
                project["id"],
                "prod",
                "/runtime",
                "OPENROUTER_API_KEY",
            )
        except InfisicalError:
            openrouter_api_key = ""
    if not openrouter_api_key:
        state = load_state()
        live = state.runtimes.get("test-nullclaw")
        if live is not None:
            try:
                openrouter_api_key = read_secret_with_token(
                    api_url,
                    token,
                    live.infisical_project_id,
                    live.infisical_env,
                    live.infisical_path,
                    "OPENROUTER_API_KEY",
                )
            except InfisicalError:
                openrouter_api_key = ""
    if not openrouter_api_key:
        raise typer.BadParameter("OPENROUTER_API_KEY is required for LiteLLM bootstrap.")

    if not master_key:
        try:
            master_key = read_secret_with_token(api_url, token, project["id"], "prod", "/runtime", "LITELLM_MASTER_KEY")
        except InfisicalError:
            master_key = random_master_key()

    upsert_secret(api_url, token, project["id"], "prod", "/runtime", "LITELLM_MASTER_KEY", master_key)
    upsert_secret(api_url, token, project["id"], "prod", "/runtime", "OPENROUTER_API_KEY", openrouter_api_key)
    service_token = create_service_token(api_url, project["id"], "litellm-core", "prod", "/runtime")
    pricing = get_price_info()

    env_values = litellm_stack_env_defaults()
    if LITELLM_STACK_ENV_FILE.exists():
        env_values.update(_env_dict(str(LITELLM_STACK_ENV_FILE)))
    env_values.update(
        {
            "INFISICAL_API_URL": containerized_api_url(api_url),
            "INFISICAL_PROJECT_ID": project["id"],
            "INFISICAL_ENV": "prod",
            "INFISICAL_PATH": "/runtime",
            "INFISICAL_TOKEN": service_token,
        }
    )
    env_path = write_stack_env(env_values)
    config_path = write_stack_config(pricing)
    typer.echo(f"Bootstrapped LiteLLM core secrets and wrote {env_path} and {config_path}.")


@litellm_app.command("status")
def litellm_status_cmd(
    base_url: str = typer.Option(default_factory=default_litellm_base_url, help="LiteLLM base URL."),
    api_url: str = typer.Option(default_factory=default_api_url, help="Infisical API URL."),
) -> None:
    """Show LiteLLM gateway status."""
    payload = {
        "base_url": base_url,
        "ui_url": f"{base_url.rstrip('/')}/ui/",
        "root_url": base_url,
        "openapi_url": f"{base_url.rstrip('/')}/openapi.json",
        "health": litellm_status(base_url),
        "core_secrets": ensure_core_secrets(api_url)["project_slug"],
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@runtime_app.command("create")
def runtime_create(
    runtime_id: str = typer.Option(..., "--id", help="Runtime identifier."),
    gateway_port: int = typer.Option(3000, help="Gateway host port."),
    model: str = typer.Option(DEFAULT_MODEL_ALIAS, help="Primary model alias exposed by LiteLLM."),
    telegram_enabled: bool = typer.Option(True, "--telegram/--no-telegram", help="Enable Telegram channel."),
    telegram_bot_token: str = typer.Option("", envvar="TELEGRAM_BOT_TOKEN", help="Telegram bot token."),
    telegram_allow_from: str = typer.Option("373793732", envvar="TELEGRAM_ALLOW_FROM", help="Telegram allowlist user id."),
    runtime_role: str | None = typer.Option(None, help="Runtime role: live, probe, limit-probe, custom."),
    budget_usd: float | None = typer.Option(None, help="LiteLLM max budget in USD."),
    rpm_limit: int | None = typer.Option(None, help="LiteLLM per-key RPM limit."),
    tpm_limit: int | None = typer.Option(None, help="LiteLLM per-key TPM limit."),
    tenant_id: str | None = typer.Option(None, help="Optional tenant metadata."),
    plan_id: str | None = typer.Option(None, help="Optional plan metadata."),
    api_url: str = typer.Option(default_factory=default_api_url, help="Infisical API URL."),
    litellm_base_url: str = typer.Option(default_factory=default_litellm_base_url, help="LiteLLM base URL."),
) -> None:
    """Create or update a NullClaw runtime and start its gateway."""
    _require_venv()
    ensure_local_layout()
    if telegram_enabled and not telegram_bot_token:
        state = load_state()
        existing = state.runtimes.get(runtime_id)
        if existing is None:
            raise typer.BadParameter("TELEGRAM_BOT_TOKEN is required when Telegram is enabled.")

    runtime = create_or_update_runtime(
        RuntimeCreateRequest(
            runtime_id=runtime_id,
            gateway_port=gateway_port,
            model=model,
            telegram_enabled=telegram_enabled,
            telegram_bot_token=telegram_bot_token,
            telegram_allow_from=telegram_allow_from,
            runtime_role=runtime_role,
            budget_usd=budget_usd,
            rpm_limit=rpm_limit,
            tpm_limit=tpm_limit,
            tenant_slug=tenant_id,
            plan_slug=plan_id,
            api_url=api_url,
            litellm_base_url=litellm_base_url,
        )
    )
    typer.echo(f"Runtime {runtime.runtime_id} is up in compose project {COMPOSE_PROJECT_NAME}.")


@runtime_app.command("rotate-key")
def runtime_rotate_key(
    runtime_id: str = typer.Option(..., "--id", help="Runtime identifier."),
    api_url: str = typer.Option(default_factory=default_api_url, help="Infisical API URL."),
    litellm_base_url: str = typer.Option(default_factory=default_litellm_base_url, help="LiteLLM base URL."),
) -> None:
    runtime = rotate_runtime_key(runtime_id, api_url=api_url, litellm_base_url=litellm_base_url)
    typer.echo(f"Rotated LiteLLM key for runtime {runtime.runtime_id}.")


@runtime_app.command("revoke-key")
def runtime_revoke_key(
    runtime_id: str = typer.Option(..., "--id", help="Runtime identifier."),
    api_url: str = typer.Option(default_factory=default_api_url, help="Infisical API URL."),
    litellm_base_url: str = typer.Option(default_factory=default_litellm_base_url, help="LiteLLM base URL."),
) -> None:
    revoke_runtime_key(runtime_id, api_url=api_url, litellm_base_url=litellm_base_url)
    typer.echo(f"Revoked LiteLLM key for runtime {runtime_id}.")


@runtime_app.command("inspect-key")
def runtime_inspect_key(
    runtime_id: str = typer.Option(..., "--id", help="Runtime identifier."),
    api_url: str = typer.Option(default_factory=default_api_url, help="Infisical API URL."),
    litellm_base_url: str = typer.Option(default_factory=default_litellm_base_url, help="LiteLLM base URL."),
) -> None:
    typer.echo(json.dumps(inspect_runtime_key(runtime_id, api_url=api_url, litellm_base_url=litellm_base_url), indent=2, sort_keys=True))


@runtime_app.command("limits")
def runtime_limits(runtime_id: str = typer.Option(..., "--id", help="Runtime identifier.")) -> None:
    typer.echo(json.dumps(read_runtime_limits(runtime_id), indent=2, sort_keys=True))


@runtime_app.command("sync-limits")
def runtime_sync_limits(
    runtime_id: str = typer.Option(..., "--id", help="Runtime identifier."),
    api_url: str = typer.Option(default_factory=default_api_url, help="Infisical API URL."),
    litellm_base_url: str = typer.Option(default_factory=default_litellm_base_url, help="LiteLLM base URL."),
) -> None:
    typer.echo(json.dumps(sync_runtime_limits(runtime_id, api_url=api_url, litellm_base_url=litellm_base_url), indent=2, sort_keys=True))


@runtime_app.command("up")
def runtime_up(runtime_id: str = typer.Option(..., "--id", help="Runtime identifier.")) -> None:
    start_runtime(runtime_id)
    typer.echo(f"Started runtime {runtime_id}.")


@runtime_app.command("stop")
def runtime_stop(runtime_id: str = typer.Option(..., "--id", help="Runtime identifier.")) -> None:
    stop_runtime(runtime_id)
    typer.echo(f"Stopped runtime {runtime_id}.")


@runtime_app.command("delete")
def runtime_delete(
    runtime_id: str = typer.Option(..., "--id", help="Runtime identifier."),
    keep_files: bool = typer.Option(False, "--keep-files", help="Keep local runtime directories."),
) -> None:
    delete_runtime_service(runtime_id, keep_files=keep_files)
    typer.echo(f"Deleted runtime {runtime_id}. Infisical project was left intact.")


@runtime_app.command("list")
def runtime_list() -> None:
    lines = list_runtime_lines()
    if not lines:
        typer.echo("No runtimes defined.")
        return
    for line in lines:
        typer.echo(line)


@runtime_app.command("status")
def runtime_status(
    runtime_id: str = typer.Option(..., "--id", help="Runtime identifier."),
    api_url: str = typer.Option(default_factory=default_api_url, help="Infisical API URL."),
) -> None:
    typer.echo(json.dumps(runtime_status_payload(runtime_id, api_url=api_url), indent=2, sort_keys=True))


@runtime_app.command("probe-check")
def runtime_probe_check(
    runtime_id: str = typer.Option(..., "--id", help="Runtime identifier to use as probe."),
    target: str = typer.Option(..., "--target", help="Runtime identifier that must stay isolated."),
) -> None:
    result = runtime_probe_check_service(runtime_id, target)
    if result["passed"]:
        typer.echo(f"Isolation check passed: {runtime_id} and {target} cannot read each other's LiteLLM secrets.")
        return
    raise typer.Exit(f"Isolation check failed: runtime service tokens crossed project boundaries between {runtime_id} and {target}.")


def main() -> None:
    app()
