from orchestrator.models import RuntimeRecord
from orchestrator.state import delete_runtime, upsert_runtime
from orchestrator.models import StateFile
from orchestrator.cli import _runtime_api_url


def test_upsert_and_delete_runtime() -> None:
    state = StateFile()
    runtime = RuntimeRecord(
        id="probe",
        enabled=True,
        gateway_port=3002,
        telegram_enabled=False,
        model="openai/qwen/qwen3.6-plus",
        runtime_role="probe",
        infisical_project_slug="probe",
        infisical_project_id="project-probe",
        infisical_env="prod",
        infisical_path="/runtime",
        litellm_key_name="runtime-probe",
        litellm_budget_usd=0.05,
        litellm_rpm_limit=10,
        litellm_tpm_limit=20000,
        runtime_env_file="/tmp/probe/runtime.env",
        runtime_home="/tmp/probe/home",
        workspace_dir="/tmp/probe/home/workspace",
        generated_config_path="/tmp/probe/home/config.json",
    )

    upsert_runtime(state, runtime)
    assert "probe" in state.runtimes

    delete_runtime(state, "probe")
    assert "probe" not in state.runtimes


def test_runtime_api_url_rewrites_localhost_for_containers() -> None:
    assert _runtime_api_url("http://127.0.0.1:18080") == "http://host.docker.internal:18080"
    assert _runtime_api_url("http://localhost:18080") == "http://host.docker.internal:18080"
    assert _runtime_api_url("https://infisical.internal") == "https://infisical.internal"
