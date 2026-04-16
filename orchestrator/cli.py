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
    ensure_project,
    operator_token,
    read_secret_with_token,
    upsert_secret,
)
from orchestrator.models import RuntimeRecord
from orchestrator.paths import COMPOSE_FILE, COMPOSE_PROJECT_NAME, runtime_dir, runtime_env_file, runtime_home, workspace_dir
from orchestrator.shell import CommandError, run
from orchestrator.state import delete_runtime, ensure_local_layout, load_state, save_state, upsert_runtime


app = typer.Typer(no_args_is_help=True, help="Aquarium control plane for NullClaw runtimes.")
runtime_app = typer.Typer(no_args_is_help=True, help="Manage hosted NullClaw runtimes.")
app.add_typer(runtime_app, name="runtime")


def _require_venv() -> None:
    expected = str(Path.cwd() / ".venv")
    if not sys.executable.startswith(expected):
        raise typer.BadParameter(f"Run the orchestrator from the repo-local .venv. Current Python: {sys.executable}")
    if sys.version_info[:2] != (3, 12):
        raise typer.BadParameter(f"Python 3.12 is required. Current version: {sys.version.split()[0]}")


def _ensure_tool(name: str) -> None:
    if which(name) is None:
        raise typer.BadParameter(f"Required tool is missing from PATH: {name}")


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
        "NULLCLAW_MAX_ACTIONS_PER_HOUR": "20",
        "NULLCLAW_LOG_TOOL_CALLS": "true",
        "NULLCLAW_LOG_MESSAGE_RECEIPTS": "true",
        "NULLCLAW_LOG_MESSAGE_PAYLOADS": "true",
        "NULLCLAW_LOG_LLM_IO": "true",
        "NULLCLAW_TOKEN_USAGE_LEDGER_ENABLED": "true",
    }
    lines = [f"{key}={value}" for key, value in values.items()]
    env_path.write_text("\n".join(lines) + "\n")


def _runtime_api_url(api_url: str) -> str:
    override = os.environ.get("INFISICAL_RUNTIME_API_URL")
    if override:
        return override
    parsed = urlparse(api_url)
    if parsed.hostname in {"127.0.0.1", "localhost"}:
        netloc = parsed.netloc.replace(parsed.hostname or "", "host.docker.internal", 1)
        return urlunparse(parsed._replace(netloc=netloc))
    return api_url


def _runtime_record(runtime_id: str, gateway_port: int, telegram_enabled: bool, model: str, project_slug: str, project_id: str) -> RuntimeRecord:
    runtime_home_path = runtime_home(runtime_id)
    workspace_path = workspace_dir(runtime_id)
    env_path = runtime_env_file(runtime_id)
    runtime_home_path.mkdir(parents=True, exist_ok=True)
    workspace_path.mkdir(parents=True, exist_ok=True)
    return RuntimeRecord(
        id=runtime_id,
        enabled=True,
        gateway_port=gateway_port,
        telegram_enabled=telegram_enabled,
        model=model,
        infisical_project_slug=project_slug,
        infisical_project_id=project_id,
        infisical_env="prod",
        infisical_path="/runtime",
        runtime_env_file=str(env_path),
        runtime_home=str(runtime_home_path),
        workspace_dir=str(workspace_path),
        generated_config_path=str(runtime_home_path / "config.json"),
    )


def _compose_cmd(*args: str) -> list[str]:
    return ["docker", "compose", "-f", str(COMPOSE_FILE), *args]


def _up_runtime(runtime_id: str) -> None:
    run(_compose_cmd("up", "-d", "--force-recreate", f"gateway-{runtime_id}"), cwd=str(Path.cwd()))


@app.command()
def init(api_url: str = typer.Option(default_factory=default_api_url, help="Infisical API URL.")) -> None:
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
    typer.echo(f"Initialized orchestrator state under {Path.cwd() / '.aquarium'}")
    typer.echo(f"Compose project: {COMPOSE_PROJECT_NAME}")


@runtime_app.command("create")
def runtime_create(
    runtime_id: str = typer.Option(..., "--id", help="Runtime identifier."),
    gateway_port: int = typer.Option(3000, help="Gateway host port."),
    model: str = typer.Option("openrouter/qwen/qwen3.6-plus", help="Primary model."),
    telegram_enabled: bool = typer.Option(True, "--telegram/--no-telegram", help="Enable Telegram channel."),
    openrouter_api_key: str = typer.Option("", envvar="OPENROUTER_API_KEY", help="OpenRouter API key."),
    telegram_bot_token: str = typer.Option("", envvar="TELEGRAM_BOT_TOKEN", help="Telegram bot token."),
    telegram_allow_from: str = typer.Option("373793732", envvar="TELEGRAM_ALLOW_FROM", help="Telegram allowlist user id."),
    api_url: str = typer.Option(default_factory=default_api_url, help="Infisical API URL."),
) -> None:
    """Create or update a NullClaw runtime and start its gateway."""
    _require_venv()
    ensure_local_layout()
    if not openrouter_api_key:
        raise typer.BadParameter("OPENROUTER_API_KEY is required.")
    if telegram_enabled and not telegram_bot_token:
        raise typer.BadParameter("TELEGRAM_BOT_TOKEN is required when Telegram is enabled.")

    state = load_state()
    token = operator_token(api_url)
    project = ensure_project(api_url, token, runtime_id)

    upsert_secret(api_url, token, project["id"], "prod", "/runtime", "OPENROUTER_API_KEY", openrouter_api_key)
    if telegram_enabled:
        upsert_secret(api_url, token, project["id"], "prod", "/runtime", "TELEGRAM_BOT_TOKEN", telegram_bot_token)
        upsert_secret(api_url, token, project["id"], "prod", "/runtime", "TELEGRAM_ALLOW_FROM", telegram_allow_from)

    runtime = _runtime_record(runtime_id, gateway_port, telegram_enabled, model, project["slug"], project["id"])
    service_token = create_service_token(api_url, project["id"], runtime.id, runtime.infisical_env, runtime.infisical_path)
    _write_runtime_env(runtime, service_token, api_url)

    state = upsert_runtime(state, runtime)
    save_state(state)
    write_compose(state)
    _up_runtime(runtime.id)
    typer.echo(f"Runtime {runtime.id} is up in compose project {COMPOSE_PROJECT_NAME}.")


@runtime_app.command("up")
def runtime_up(runtime_id: str = typer.Option(..., "--id", help="Runtime identifier.")) -> None:
    state = load_state()
    if runtime_id not in state.runtimes:
        raise typer.BadParameter(f"Unknown runtime: {runtime_id}")
    write_compose(state)
    _up_runtime(runtime_id)
    typer.echo(f"Started runtime {runtime_id}.")


@runtime_app.command("stop")
def runtime_stop(runtime_id: str = typer.Option(..., "--id", help="Runtime identifier.")) -> None:
    state = load_state()
    if runtime_id not in state.runtimes:
        raise typer.BadParameter(f"Unknown runtime: {runtime_id}")
    write_compose(state)
    run(_compose_cmd("stop", f"gateway-{runtime_id}", f"agent-{runtime_id}"))
    typer.echo(f"Stopped runtime {runtime_id}.")


@runtime_app.command("delete")
def runtime_delete(
    runtime_id: str = typer.Option(..., "--id", help="Runtime identifier."),
    keep_files: bool = typer.Option(False, "--keep-files", help="Keep local runtime directories."),
) -> None:
    state = load_state()
    if runtime_id not in state.runtimes:
        raise typer.BadParameter(f"Unknown runtime: {runtime_id}")
    runtime = state.runtimes[runtime_id]
    write_compose(state)
    try:
        run(_compose_cmd("stop", f"gateway-{runtime_id}", f"agent-{runtime_id}"))
    except CommandError:
        pass
    try:
        run(_compose_cmd("rm", "-f", "-s", f"gateway-{runtime_id}", f"agent-{runtime_id}"))
    except CommandError:
        pass
    state = delete_runtime(state, runtime_id)
    save_state(state)
    write_compose(state)
    if not keep_files:
        shutil.rmtree(runtime_dir(runtime_id), ignore_errors=True)
    typer.echo(f"Deleted runtime {runtime_id}. Infisical project was left intact.")


@runtime_app.command("list")
def runtime_list() -> None:
    state = load_state()
    if not state.runtimes:
        typer.echo("No runtimes defined.")
        return
    for runtime_id in sorted(state.runtimes):
        runtime = state.runtimes[runtime_id]
        typer.echo(
            f"{runtime.id} port={runtime.gateway_port} telegram={'on' if runtime.telegram_enabled else 'off'} "
            f"project={runtime.infisical_project_slug}"
        )


@runtime_app.command("status")
def runtime_status(runtime_id: str = typer.Option(..., "--id", help="Runtime identifier.")) -> None:
    state = load_state()
    if runtime_id not in state.runtimes:
        raise typer.BadParameter(f"Unknown runtime: {runtime_id}")
    runtime = state.runtimes[runtime_id]
    write_compose(state)
    status: dict[str, object] = runtime.model_dump()
    try:
        compose_ps = run(_compose_cmd("ps", f"gateway-{runtime_id}", "--format", "json"))
        status["compose"] = json.loads(compose_ps) if compose_ps else []
    except (CommandError, json.JSONDecodeError):
        status["compose"] = []
    try:
        response = requests.get(f"http://127.0.0.1:{runtime.gateway_port}/health", timeout=10)
        status["health"] = {"status_code": response.status_code, "body": response.text.strip()}
    except requests.RequestException as exc:
        status["health"] = {"error": str(exc)}
    typer.echo(json.dumps(status, indent=2, sort_keys=True))


@runtime_app.command("probe-check")
def runtime_probe_check(
    runtime_id: str = typer.Option(..., "--id", help="Runtime identifier to use as probe."),
    target: str = typer.Option(..., "--target", help="Runtime identifier that must stay isolated."),
) -> None:
    state = load_state()
    if runtime_id not in state.runtimes:
        raise typer.BadParameter(f"Unknown runtime: {runtime_id}")
    if target not in state.runtimes:
        raise typer.BadParameter(f"Unknown target runtime: {target}")
    probe = state.runtimes[runtime_id]
    target_runtime = state.runtimes[target]
    probe_env = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in Path(probe.runtime_env_file).read_text().splitlines()
        if "=" in line
    }
    target_env = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in Path(target_runtime.runtime_env_file).read_text().splitlines()
        if "=" in line
    }
    own_probe = read_secret_with_token(
        probe_env["INFISICAL_API_URL"],
        probe_env["INFISICAL_TOKEN"],
        probe.infisical_project_id,
        probe.infisical_env,
        probe.infisical_path,
        "OPENROUTER_API_KEY",
    )
    own_target = read_secret_with_token(
        target_env["INFISICAL_API_URL"],
        target_env["INFISICAL_TOKEN"],
        target_runtime.infisical_project_id,
        target_runtime.infisical_env,
        target_runtime.infisical_path,
        "OPENROUTER_API_KEY",
    )
    if own_probe == own_target:
        raise typer.Exit("Probe and target have the same OPENROUTER_API_KEY value, so isolation proof is ambiguous.")
    try:
        cross_from_probe = read_secret_with_token(
            probe_env["INFISICAL_API_URL"],
            probe_env["INFISICAL_TOKEN"],
            target_runtime.infisical_project_id,
            target_runtime.infisical_env,
            target_runtime.infisical_path,
            "OPENROUTER_API_KEY",
        )
    except InfisicalError:
        cross_from_probe = None

    try:
        cross_from_target = read_secret_with_token(
            target_env["INFISICAL_API_URL"],
            target_env["INFISICAL_TOKEN"],
            probe.infisical_project_id,
            probe.infisical_env,
            probe.infisical_path,
            "OPENROUTER_API_KEY",
        )
    except InfisicalError:
        cross_from_target = None

    probe_isolated = cross_from_probe is None or (cross_from_probe == own_probe and cross_from_probe != own_target)
    target_isolated = cross_from_target is None or (cross_from_target == own_target and cross_from_target != own_probe)

    if probe_isolated and target_isolated:
        typer.echo(f"Isolation check passed: {runtime_id} and {target} cannot read each other's secrets.")
        return

    raise typer.Exit(f"Isolation check failed: runtime service tokens crossed project boundaries between {runtime_id} and {target}.")


def main() -> None:
    app()
