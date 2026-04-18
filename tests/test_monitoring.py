from pathlib import Path

from orchestrator.cli import _monitoring_runtime_env


def test_monitoring_runtime_env_is_empty_without_bootstrap_file(tmp_path: Path) -> None:
    env_file = tmp_path / "monitoring.env"

    assert _monitoring_runtime_env(env_file) == {}


def test_monitoring_runtime_env_enables_otel_when_bootstrap_exists(tmp_path: Path) -> None:
    env_file = tmp_path / "monitoring.env"
    env_file.write_text(
        "\n".join(
            [
                "INFISICAL_PROJECT_ID=project-monitoring",
                "INFISICAL_TOKEN=monitoring-token",
                "OTLP_HTTP_PORT=4318",
            ]
        )
        + "\n"
    )

    assert _monitoring_runtime_env(env_file) == {
        "NULLCLAW_OTEL_ENABLED": "true",
        "NULLCLAW_OTEL_ENDPOINT": "http://alloy.local:4318",
        "NULLCLAW_OTEL_SERVICE_NAME": "nullclaw-<runtime-id>",
    }
