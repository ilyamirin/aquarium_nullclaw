from orchestrator.compose import render_compose
from orchestrator.models import RuntimeRecord, StateFile


def _runtime(runtime_id: str, port: int) -> RuntimeRecord:
    return RuntimeRecord(
        id=runtime_id,
        enabled=True,
        gateway_port=port,
        telegram_enabled=runtime_id == "test-nullclaw",
        model="openai/qwen/qwen3.6-plus",
        runtime_role="live" if runtime_id == "test-nullclaw" else "probe",
        infisical_project_slug=runtime_id,
        infisical_project_id=f"project-{runtime_id}",
        infisical_env="prod",
        infisical_path="/runtime",
        litellm_key_name=f"runtime-{runtime_id}",
        litellm_budget_usd=1.0 if runtime_id == "test-nullclaw" else 0.05,
        litellm_rpm_limit=60 if runtime_id == "test-nullclaw" else 10,
        litellm_tpm_limit=120000 if runtime_id == "test-nullclaw" else 20000,
        runtime_env_file=f"/tmp/{runtime_id}.env",
        runtime_home=f"/tmp/{runtime_id}/home",
        workspace_dir=f"/tmp/{runtime_id}/home/workspace",
        generated_config_path=f"/tmp/{runtime_id}/home/config.json",
    )


def test_compose_uses_shared_project_name_and_runtime_services() -> None:
    state = StateFile(
        runtimes={
            "test-nullclaw": _runtime("test-nullclaw", 3000),
            "probe": _runtime("probe", 3002),
        }
    )

    compose = render_compose(state)

    assert compose["name"] == "aquarium-nullclaw-runtimes"
    assert "gateway-test-nullclaw" in compose["services"]
    assert "agent-test-nullclaw" in compose["services"]
    assert "gateway-probe" in compose["services"]
    assert compose["services"]["gateway-probe"]["ports"] == ["127.0.0.1:3002:3002"]
