from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client

from controlplane.domain.models import (
    Agent,
    AgentBuildSpec,
    AgentSecretBinding,
    AgentSkillBinding,
    ConnectionScope,
    ConnectionStatus,
    Deployment,
    IntegrationConnection,
    Plan,
    ProviderConnection,
    ProviderModel,
    Runtime,
    RuntimeActionLog,
    RuntimeDiagnosticSnapshot,
    RuntimeProfile,
    RuntimeProfileSlug,
    RuntimeSecretRef,
    SecretKind,
    SkillCatalogEntry,
    SkillSource,
    SkillTrustStatus,
    SkillType,
    Tenant,
    Workspace,
)
from orchestrator.litellm import DEFAULT_MODEL_ALIAS, DEFAULT_PROVIDER_MODEL, render_stack_config
from orchestrator.models import RuntimeRecord, StateFile
from orchestrator.service_layer import (
    AgentCreateRequest,
    NULLCLAW_MAX_ACTIONS_PER_HOUR,
    backfill_agents_from_runtimes,
    bootstrap_internal_skill_catalog,
    bootstrap_reference_data,
    create_draft_agent,
    delete_integration_connection_service,
    import_json_state_if_empty,
    internal_skill_manifest_entries,
    launch_agent,
    runtime_config_view,
    runtime_detail_payload,
    skill_catalog_payload,
    stop_agent,
    test_runtime_secret as service_test_runtime_secret,
    update_runtime_limits,
    update_runtime_skills,
    upsert_integration_connection,
    upsert_runtime_secret,
    upsert_workspace_secret,
)


def _write_internal_skill_manifest(package_dir: Path, **overrides) -> None:
    package_dir.mkdir(parents=True)
    (package_dir / "SKILL.md").write_text("# Test Skill\n", encoding="utf-8")
    manifest = {
        "key": package_dir.name,
        "display_name": "Test Skill",
        "description": "Loaded from a test manifest.",
        "category": "Diagnostics",
        "type": "hybrid",
        "source": "internal",
        "trust_status": "internal",
        "required_integrations": ["telegram"],
        "required_secrets": ["TELEGRAM_BOT_TOKEN"],
        "required_services": ["monitoring"],
        "permissions": ["diagnostics_read"],
        "entrypoints": ["diagnostics.summary"],
        "default_enabled": False,
    }
    manifest.update(overrides)
    (package_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.fixture
def operator_client(db) -> Client:
    user = get_user_model().objects.create_user(
        username="operator",
        password="operator-pass",
        is_staff=True,
        is_superuser=True,
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def regular_client(db) -> Client:
    user = get_user_model().objects.create_user(
        username="viewer",
        password="viewer-pass",
        is_staff=False,
        is_superuser=False,
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def runtime_fixture(db, monkeypatch, tmp_path) -> Runtime:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)

    tenant = Tenant.objects.create(slug="tenant-a", name="Tenant A")
    profile = RuntimeProfile.objects.create(slug=RuntimeProfileSlug.LIVE, display_name="Live")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "channels": {"telegram": {"accounts": {"main": {"bot_token": "telegram-secret-token"}}}},
                "models": {"providers": {"custom": {"api_key": "provider-secret-key"}}},
                "security": {"slack_signing_secret": "slack-secret"},
            }
        )
    )
    env_path = tmp_path / "runtime.env"
    env_path.write_text("INFISICAL_API_URL=http://127.0.0.1:18080\nINFISICAL_TOKEN=test-token\n")
    return Runtime.objects.create(
        runtime_id="demo-runtime",
        enabled=True,
        tenant=tenant,
        runtime_profile=profile,
        gateway_port=3900,
        model="openai/qwen/qwen3.6-plus",
        telegram_enabled=True,
        desired_channels={"telegram": True},
        infisical_project_slug="demo-runtime",
        infisical_project_id="project-demo-runtime",
        infisical_env="prod",
        infisical_path="/runtime",
        litellm_key_name="runtime-demo-runtime",
        litellm_budget_usd=10.0,
        litellm_rpm_limit=60,
        litellm_tpm_limit=50000,
        litellm_model_alias="openai/qwen/qwen3.6-plus",
        runtime_env_file=str(env_path),
        runtime_home=str(tmp_path / "home"),
        workspace_dir=str(tmp_path / "workspace"),
        generated_config_path=str(config_path),
    )


@pytest.mark.django_db
def test_runtime_config_view_masks_sensitive_values(runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)

    payload = runtime_config_view(runtime_fixture.runtime_id)

    assert payload["exists"] is True
    assert payload["config"]["channels"]["telegram"]["accounts"]["main"]["bot_token"] == "***"
    assert payload["config"]["models"]["providers"]["custom"]["api_key"] == "***"
    assert payload["config"]["security"]["slack_signing_secret"] == "***"


@pytest.mark.django_db
def test_skill_catalog_entry_defaults_to_internal_behavior_skill() -> None:
    skill = SkillCatalogEntry.objects.create(
        key="support-triage",
        display_name="Support Triage",
        description="Classify operator requests.",
        category="Operator Workflow",
        source_path="skills/support-triage/SKILL.md",
        required_integrations=["telegram"],
        required_secrets=["TELEGRAM_BOT_TOKEN"],
        required_services=["controlplane"],
        permissions=["runtime_read"],
        entrypoints=["runtime.status"],
    )

    assert skill.skill_type == SkillType.BEHAVIOR
    assert skill.source == SkillSource.INTERNAL
    assert skill.trust_status == SkillTrustStatus.INTERNAL
    assert skill.source_url == ""
    assert skill.required_integrations == ["telegram"]
    assert skill.required_secrets == ["TELEGRAM_BOT_TOKEN"]
    assert skill.required_services == ["controlplane"]
    assert skill.permissions == ["runtime_read"]
    assert skill.entrypoints == ["runtime.status"]


@pytest.mark.django_db
def test_bootstrap_reference_data_creates_internal_operator_skill_catalog_idempotently() -> None:
    manifests = {manifest["key"]: manifest for manifest in internal_skill_manifest_entries()}
    expected_keys = set(manifests)

    bootstrap_reference_data()
    bootstrap_reference_data()

    skills = SkillCatalogEntry.objects.filter(key__in=expected_keys)
    assert skills.count() == len(expected_keys)
    assert set(skills.values_list("key", flat=True)) == expected_keys
    assert SkillCatalogEntry.objects.filter(key="runtime-operator").count() == 1

    runtime_operator = SkillCatalogEntry.objects.get(key="runtime-operator")
    runtime_operator_manifest = manifests["runtime-operator"]
    assert runtime_operator.skill_type == runtime_operator_manifest["type"]
    assert runtime_operator.source == runtime_operator_manifest["source"]
    assert runtime_operator.trust_status == runtime_operator_manifest["trust_status"]
    assert runtime_operator.source_path == runtime_operator_manifest["source_path"]
    assert runtime_operator.category == runtime_operator_manifest["category"]
    assert runtime_operator.required_services == runtime_operator_manifest["required_services"]
    assert runtime_operator.permissions == runtime_operator_manifest["permissions"]
    assert runtime_operator.entrypoints == runtime_operator_manifest["entrypoints"]
    assert runtime_operator.default_enabled == runtime_operator_manifest["default_enabled"]
    assert runtime_operator.status == "active"

    support_triage = SkillCatalogEntry.objects.get(key="support-triage")
    support_triage_manifest = manifests["support-triage"]
    assert support_triage.skill_type == support_triage_manifest["type"]
    assert support_triage.required_integrations == support_triage_manifest["required_integrations"]
    assert support_triage.permissions == support_triage_manifest["permissions"]
    assert support_triage.default_enabled == support_triage_manifest["default_enabled"]


@pytest.mark.django_db
def test_bootstrap_internal_skill_catalog_reads_manifest_source_of_truth(monkeypatch, tmp_path) -> None:
    package_dir = tmp_path / "skills" / "manifest-backed"
    _write_internal_skill_manifest(
        package_dir,
        key="manifest-backed",
        display_name="Manifest Backed",
        description="Loaded from the package manifest.",
    )

    monkeypatch.setattr("orchestrator.service_layer.INTERNAL_SKILLS_DIR", tmp_path / "skills")

    bootstrap_internal_skill_catalog()

    skill = SkillCatalogEntry.objects.get(key="manifest-backed")
    assert skill.display_name == "Manifest Backed"
    assert skill.description == "Loaded from the package manifest."
    assert skill.category == "Diagnostics"
    assert skill.skill_type == SkillType.HYBRID
    assert skill.source == SkillSource.INTERNAL
    assert skill.trust_status == SkillTrustStatus.INTERNAL
    assert skill.source_path == str(Path("skills/manifest-backed/SKILL.md"))
    assert skill.required_integrations == ["telegram"]
    assert skill.required_secrets == ["TELEGRAM_BOT_TOKEN"]
    assert skill.required_services == ["monitoring"]
    assert skill.permissions == ["diagnostics_read"]
    assert skill.entrypoints == ["diagnostics.summary"]
    assert skill.default_enabled is False
    assert skill.status == "active"


def test_internal_skill_manifest_entries_rejects_duplicate_keys(monkeypatch, tmp_path) -> None:
    skills_dir = tmp_path / "skills"
    _write_internal_skill_manifest(skills_dir / "alpha", key="duplicate-skill")
    _write_internal_skill_manifest(skills_dir / "bravo", key="duplicate-skill")
    monkeypatch.setattr("orchestrator.service_layer.INTERNAL_SKILLS_DIR", skills_dir)

    with pytest.raises(ValueError, match="duplicate internal skill manifest key 'duplicate-skill'"):
        internal_skill_manifest_entries()


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        ("display_name", 123, "display_name must be a string"),
        ("default_enabled", "false", "default_enabled must be a bool"),
        ("required_services", ["monitoring", 7], "required_services must be a list of strings"),
        ("permissions", "diagnostics_read", "permissions must be a list of strings"),
    ],
)
def test_internal_skill_manifest_entries_rejects_malformed_field_types(
    monkeypatch,
    tmp_path,
    field: str,
    value,
    expected_message: str,
) -> None:
    skills_dir = tmp_path / "skills"
    _write_internal_skill_manifest(skills_dir / "malformed", **{field: value})
    monkeypatch.setattr("orchestrator.service_layer.INTERNAL_SKILLS_DIR", skills_dir)

    with pytest.raises(ValueError, match=expected_message):
        internal_skill_manifest_entries()


def test_internal_skill_manifest_entries_rejects_non_object_manifest(monkeypatch, tmp_path) -> None:
    skills_dir = tmp_path / "skills"
    package_dir = skills_dir / "malformed"
    package_dir.mkdir(parents=True)
    (package_dir / "SKILL.md").write_text("# Malformed\n", encoding="utf-8")
    (package_dir / "manifest.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    monkeypatch.setattr("orchestrator.service_layer.INTERNAL_SKILLS_DIR", skills_dir)

    with pytest.raises(ValueError, match="must contain a JSON object"):
        internal_skill_manifest_entries()


@pytest.mark.django_db
def test_skill_catalog_payload_includes_operator_skill_dependency_and_trust_fields() -> None:
    manifests = {manifest["key"]: manifest for manifest in internal_skill_manifest_entries()}
    bootstrap_reference_data()

    payload = skill_catalog_payload()
    by_key = {item["key"]: item for item in payload["items"]}

    gitea = by_key["gitea-operator"]
    manifest = manifests["gitea-operator"]
    assert gitea["skill_type"] == manifest["type"]
    assert gitea["source"] == manifest["source"]
    assert gitea["trust_status"] == manifest["trust_status"]
    assert gitea["source_path"] == manifest["source_path"]
    assert gitea["category"] == manifest["category"]
    assert gitea["required_integrations"] == manifest["required_integrations"]
    assert gitea["required_secrets"] == manifest["required_secrets"]
    assert gitea["required_services"] == manifest["required_services"]
    assert gitea["permissions"] == manifest["permissions"]
    assert gitea["entrypoints"] == manifest["entrypoints"]
    assert gitea["default_enabled"] == manifest["default_enabled"]
    assert gitea["status"] == "active"
    assert gitea["dependency_status"]["available"] is False
    assert "gitea" in gitea["dependency_status"]["missing_integrations"]


@pytest.mark.django_db
def test_update_runtime_skills_persists_stack_permissions_and_detail_payload(runtime_fixture: Runtime) -> None:
    bootstrap_reference_data()

    update_runtime_skills(
        runtime_fixture.runtime_id,
        ["support-triage", "runtime-operator", "support-triage"],
    )
    runtime_fixture.refresh_from_db()

    assert runtime_fixture.settings["skill_stack"] == ["support-triage", "runtime-operator"]
    assert runtime_fixture.settings["skill_permissions"] == ["runtime_read", "runtime_lifecycle"]
    assert "runtime.start" in runtime_fixture.settings["skill_entrypoints"]
    assert runtime_fixture.settings["skill_prompt_sections"][0]["key"] == "support-triage"

    detail = runtime_detail_payload(runtime_fixture.runtime_id)
    assert detail["skills"]["selected_keys"] == ["support-triage", "runtime-operator"]
    assert any(item["key"] == "runtime-operator" for item in detail["skills"]["catalog"])


@pytest.mark.django_db
def test_import_runtime_state_creates_db_rows(monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    state = StateFile(
        runtimes={
            "probe": RuntimeRecord(
                id="probe",
                enabled=True,
                gateway_port=3002,
                telegram_enabled=False,
                model="openai/qwen/qwen3.6-plus",
                runtime_role="probe",
                tenant_id="tenant-probe",
                plan_id="starter",
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
                workspace_dir="/tmp/probe/workspace",
                generated_config_path="/tmp/probe/home/config.json",
            )
        }
    )

    monkeypatch.setattr("orchestrator.state.load_state", lambda: state)

    import_json_state_if_empty()

    runtime = Runtime.objects.get(runtime_id="probe")
    assert runtime.runtime_profile.slug == RuntimeProfileSlug.PROBE
    assert runtime.tenant.slug == "tenant-probe"
    assert runtime.gateway_port == 3002


@pytest.mark.django_db
def test_import_runtime_state_backfills_related_records(monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    state = StateFile(
        runtimes={
            "telegram-demo": RuntimeRecord(
                id="telegram-demo",
                enabled=True,
                gateway_port=3010,
                telegram_enabled=True,
                model="openai/qwen/qwen3.6-plus",
                runtime_role="live",
                tenant_id="tenant-telegram",
                plan_id="starter",
                infisical_project_slug="telegram-demo",
                infisical_project_id="project-telegram-demo",
                infisical_env="prod",
                infisical_path="/runtime",
                litellm_key_name="runtime-telegram-demo",
                litellm_budget_usd=1.0,
                litellm_rpm_limit=30,
                litellm_tpm_limit=50000,
                runtime_env_file="/tmp/telegram-demo/runtime.env",
                runtime_home="/tmp/telegram-demo/home",
                workspace_dir="/tmp/telegram-demo/workspace",
                generated_config_path="/tmp/telegram-demo/home/config.json",
            )
        }
    )

    monkeypatch.setattr("orchestrator.state.load_state", lambda: state)

    import_json_state_if_empty()

    runtime = Runtime.objects.get(runtime_id="telegram-demo")
    assert IntegrationConnection.objects.filter(runtime=runtime, integration_type="telegram").exists()
    assert RuntimeSecretRef.objects.filter(runtime=runtime, secret_kind=SecretKind.PROVIDER_API_KEY).exists()
    assert RuntimeSecretRef.objects.filter(runtime=runtime, secret_kind=SecretKind.TELEGRAM_BOT_TOKEN).exists()
    assert RuntimeDiagnosticSnapshot.objects.filter(runtime=runtime).exists()
    assert RuntimeActionLog.objects.filter(runtime=runtime, action="imported").exists()


@pytest.mark.django_db
def test_import_json_state_if_empty_skips_backfill_when_runtime_table_is_not_empty(monkeypatch) -> None:
    tenant = Tenant.objects.create(slug="default", name="Default")
    plan = Plan.objects.create(slug="default", display_name="Default")
    profile = RuntimeProfile.objects.create(slug=RuntimeProfileSlug.LIVE, display_name="Live")
    Runtime.objects.create(
        runtime_id="existing",
        enabled=True,
        tenant=tenant,
        plan=plan,
        runtime_profile=profile,
        gateway_port=3000,
        model="openai/qwen/qwen3.6-plus",
        telegram_enabled=False,
        infisical_project_slug="existing",
        infisical_project_id="project-existing",
        infisical_env="prod",
        infisical_path="/runtime",
        litellm_key_name="runtime-existing",
        runtime_env_file="/tmp/existing.env",
        runtime_home="/tmp/existing-home",
        workspace_dir="/tmp/existing-workspace",
        generated_config_path="/tmp/existing-home/config.json",
    )

    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.bootstrap_reference_data", lambda: None)
    monkeypatch.setattr(
        "orchestrator.service_layer.backfill_runtime_related_records",
        lambda runtime_id=None: (_ for _ in ()).throw(AssertionError("Backfill must not run when runtimes already exist")),
    )

    import_json_state_if_empty()


@pytest.mark.django_db
def test_backfill_creates_platform_provider_and_default_model(runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)

    litellm_env = {
        "INFISICAL_PROJECT_ID": "litellm-core-project",
    }
    monkeypatch.setattr("orchestrator.service_layer._litellm_env_values", lambda: litellm_env)

    from orchestrator.service_layer import backfill_runtime_related_records

    backfill_runtime_related_records(runtime_fixture.runtime_id)

    provider = ProviderConnection.objects.get(name="platform-openrouter")
    model = ProviderModel.objects.get(alias="openai/qwen/qwen3.6-plus")
    runtime_fixture.refresh_from_db()

    assert provider.provider_kind == "openrouter"
    assert provider.scope == ConnectionScope.PLATFORM
    assert model.provider_connection == provider
    assert model.is_platform_default is True
    assert runtime_fixture.default_provider_connection == provider
    assert runtime_fixture.default_provider_model == model
    assert RuntimeSecretRef.objects.filter(provider_connection=provider, secret_name="OPENROUTER_API_KEY").exists()


@pytest.mark.django_db
def test_runtime_secret_test_updates_cached_verification_fields(runtime_fixture: Runtime, monkeypatch) -> None:
    secret_ref = RuntimeSecretRef.objects.create(
        name=f"{runtime_fixture.runtime_id}-telegram-bot-token",
        secret_kind=SecretKind.TELEGRAM_BOT_TOKEN,
        runtime=runtime_fixture,
        tenant=runtime_fixture.tenant,
        infisical_project_id=runtime_fixture.infisical_project_id,
        secret_name="TELEGRAM_BOT_TOKEN",
        masked_label="Configured",
    )

    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.operator_token", lambda api_url: "operator-token")
    monkeypatch.setattr("orchestrator.service_layer.read_secret_with_token", lambda *args, **kwargs: "secret-value")

    result = service_test_runtime_secret(runtime_fixture.runtime_id, secret_ref.pk)

    secret_ref.refresh_from_db()
    assert result["status"] == "ok"
    assert secret_ref.last_verified_at is not None
    assert secret_ref.last_error == ""


@pytest.mark.django_db
def test_operator_api_requires_staff(regular_client: Client) -> None:
    response = regular_client.get("/api/providers/catalog")

    assert response.status_code == 403


@pytest.mark.django_db
def test_operator_api_lists_runtime_and_limits(operator_client: Client, runtime_fixture: Runtime) -> None:
    list_response = operator_client.get("/api/runtimes")
    limits_response = operator_client.get(f"/api/runtimes/{runtime_fixture.runtime_id}/limits")

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["runtime_id"] == runtime_fixture.runtime_id
    assert limits_response.status_code == 200
    assert limits_response.json()["rpm_limit"] == 60


@pytest.mark.django_db
def test_explicit_diagnostics_probe_still_refreshes(operator_client: Client, runtime_fixture: Runtime, monkeypatch) -> None:
    snapshot = SimpleNamespace(
        summary={"health": {"health_status": "healthy"}},
        logs={"items": []},
        traces={"items": []},
        metrics={"items": []},
    )
    calls: list[str] = []

    def fake_refresh(runtime_id: str):
        calls.append(runtime_id)
        return snapshot

    monkeypatch.setattr("orchestrator.service_layer.refresh_runtime_diagnostics", fake_refresh)

    response = operator_client.post(f"/api/runtimes/{runtime_fixture.runtime_id}/diagnostics/probe")

    assert response.status_code == 200
    assert calls == [runtime_fixture.runtime_id]
    assert response.json()["summary"]["health"]["health_status"] == "healthy"


@pytest.mark.django_db
def test_runtime_wizard_validate_and_create(operator_client: Client, runtime_fixture: Runtime, monkeypatch) -> None:
    validation = operator_client.post(
        "/api/runtime-wizard/validate",
        data=json.dumps({"runtime_id": "new-runtime", "gateway_port": 3100, "telegram_enabled": True}),
        content_type="application/json",
    )

    assert validation.status_code == 200
    assert validation.json()["valid"] is False
    assert "telegram_bot_token" in validation.json()["errors"]

    captured = {}

    def fake_create_or_update_runtime(request, actor=None):
        captured["request"] = request
        return runtime_fixture

    monkeypatch.setattr("orchestrator.service_layer.create_or_update_runtime", fake_create_or_update_runtime)

    created = operator_client.post(
        "/api/runtime-wizard/create",
        data=json.dumps(
            {
                "runtime_id": "new-runtime",
                "gateway_port": 3100,
                "model": runtime_fixture.model,
                "skill_keys": ["support-triage", "runtime-operator"],
            }
        ),
        content_type="application/json",
    )

    assert created.status_code == 201
    assert created.json()["runtime"]["runtime_id"] == runtime_fixture.runtime_id
    assert created.json()["next_steps"] == ["chat", "diagnostics", "secrets"]
    assert captured["request"].skill_keys == ["support-triage", "runtime-operator"]


@pytest.mark.django_db
def test_provider_secret_listing_stays_masked(operator_client: Client, runtime_fixture: Runtime) -> None:
    connection = ProviderConnection.objects.create(
        name="tenant-openrouter",
        display_name="Tenant OpenRouter",
        provider_kind="openrouter",
        scope=ConnectionScope.TENANT,
        tenant=runtime_fixture.tenant,
        status=ConnectionStatus.CONFIGURED,
    )
    RuntimeSecretRef.objects.create(
        name="tenant-openrouter-key",
        secret_kind=SecretKind.PROVIDER_API_KEY,
        provider_connection=connection,
        tenant=runtime_fixture.tenant,
        infisical_project_id="litellm-core-id",
        secret_name="PROVIDER_TENANT_OPENROUTER_API_KEY",
        masked_label="Configured",
    )

    response = operator_client.get("/api/secrets/provider-connections")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["masked_label"] == "Configured"
    assert "secretValue" not in response.content.decode("utf-8")


@pytest.mark.django_db
def test_runtime_secret_api_and_integration_test_flow(operator_client: Client, runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.operator_token", lambda api_url: "operator-token")
    monkeypatch.setattr("orchestrator.service_layer.upsert_secret", lambda *args, **kwargs: None)
    monkeypatch.setattr("orchestrator.service_layer.read_secret_with_token", lambda *args, **kwargs: "resolved-secret")
    monkeypatch.setattr(
        "orchestrator.service_layer.recreate_runtime",
        lambda runtime_id, actor=None: Runtime.objects.get(runtime_id=runtime_id),
    )

    created = operator_client.post(
        f"/api/runtimes/{runtime_fixture.runtime_id}/secrets",
        data=json.dumps({"secret_kind": SecretKind.TELEGRAM_BOT_TOKEN, "secret_value": "super-secret-token"}),
        content_type="application/json",
    )

    assert created.status_code == 201
    assert "super-secret-token" not in created.content.decode("utf-8")

    listing = operator_client.get(f"/api/runtimes/{runtime_fixture.runtime_id}/secrets")
    assert listing.status_code == 200
    payload = listing.json()["items"]
    telegram_secret = next(item for item in payload if item["secret_kind"] == SecretKind.TELEGRAM_BOT_TOKEN)
    assert telegram_secret["masked_label"] == "Configured"

    tested = operator_client.post(
        f"/api/runtimes/{runtime_fixture.runtime_id}/secrets/{telegram_secret['id']}/test"
    )
    assert tested.status_code == 200
    assert tested.json()["status"] == "ok"

    integration = operator_client.post(
        "/api/integrations",
        data=json.dumps(
            {
                "integration_type": "telegram",
                "runtime_id": runtime_fixture.runtime_id,
                "display_name": "Demo Telegram",
                "enabled": True,
                "config": {"enabled": True},
            }
        ),
        content_type="application/json",
    )
    assert integration.status_code == 201

    integrations = operator_client.get("/api/integrations")
    assert integrations.status_code == 200
    telegram_conn = next(item for item in integrations.json()["items"] if item["runtime"] == runtime_fixture.runtime_id)

    test_result = operator_client.post(f"/api/integrations/{telegram_conn['id']}/test")
    assert test_result.status_code == 200
    assert test_result.json()["status"] == "ok"


@pytest.mark.django_db
def test_integration_api_reports_missing_secrets(operator_client: Client, runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr(
        "orchestrator.service_layer.recreate_runtime",
        lambda runtime_id, actor=None: Runtime.objects.get(runtime_id=runtime_id),
    )
    isolated_runtime = Runtime.objects.create(
        runtime_id="plain-runtime",
        enabled=True,
        tenant=runtime_fixture.tenant,
        runtime_profile=runtime_fixture.runtime_profile,
        gateway_port=3910,
        model=runtime_fixture.model,
        telegram_enabled=False,
        desired_channels={},
        infisical_project_slug="plain-runtime",
        infisical_project_id="project-plain-runtime",
        infisical_env="prod",
        infisical_path="/runtime",
        litellm_key_name="runtime-plain-runtime",
        litellm_budget_usd=1.0,
        litellm_rpm_limit=10,
        litellm_tpm_limit=10000,
        runtime_env_file=runtime_fixture.runtime_env_file,
        runtime_home=runtime_fixture.runtime_home,
        workspace_dir=runtime_fixture.workspace_dir,
        generated_config_path=runtime_fixture.generated_config_path,
    )
    created = operator_client.post(
        "/api/integrations",
        data=json.dumps(
            {
                "integration_type": "telegram",
                "runtime_id": isolated_runtime.runtime_id,
                "display_name": "Broken Telegram",
                "enabled": True,
                "config": {"enabled": True},
            }
        ),
        content_type="application/json",
    )
    assert created.status_code == 201
    connection_id = created.json()["id"]

    tested = operator_client.post(f"/api/integrations/{connection_id}/test")
    assert tested.status_code == 200
    assert tested.json()["status"] == "error"
    assert SecretKind.TELEGRAM_BOT_TOKEN in tested.json()["missing"]


@pytest.mark.django_db
def test_runtime_detail_payload_and_operator_pages_render(operator_client: Client, runtime_fixture: Runtime, monkeypatch) -> None:
    RuntimeSecretRef.objects.create(
        name=f"{runtime_fixture.runtime_id}-litellm-api-key",
        secret_kind=SecretKind.PROVIDER_API_KEY,
        runtime=runtime_fixture,
        tenant=runtime_fixture.tenant,
        infisical_project_id=runtime_fixture.infisical_project_id,
        secret_name="LITELLM_API_KEY",
        masked_label="Configured",
    )
    monkeypatch.setattr(
        "orchestrator.service_layer.refresh_runtime_diagnostics",
        lambda runtime_id: (_ for _ in ()).throw(AssertionError("GET views must not refresh diagnostics")),
    )
    monkeypatch.setattr(
        "orchestrator.service_layer.runtime_secret_check",
        lambda runtime_id: (_ for _ in ()).throw(AssertionError("GET views must not verify secrets")),
    )
    monkeypatch.setattr(
        "orchestrator.service_layer.backfill_runtime_related_records",
        lambda runtime_id=None: (_ for _ in ()).throw(AssertionError("GET views must not backfill records")),
    )
    monkeypatch.setattr("orchestrator.service_layer.inspect_runtime_key", lambda runtime_id: {"status": "cached"})

    detail_payload = operator_client.get(f"/api/runtimes/{runtime_fixture.runtime_id}")
    assert detail_payload.status_code == 200
    body = detail_payload.json()
    assert body["runtime"]["runtime_id"] == runtime_fixture.runtime_id
    assert "links" in body["diagnostics"]
    assert any(item["name"].endswith("litellm-api-key") for item in body["secrets"])

    admin_index = operator_client.get("/admin/")
    dashboard = operator_client.get("/admin/dashboard/", follow=False)
    runtimes = operator_client.get("/admin/runtimes/", follow=False)
    wizard = operator_client.get("/admin/runtime-wizard/")
    wizard_skills = operator_client.get("/admin/runtime-wizard/?step=3")
    detail = operator_client.get(f"/admin/runtimes/{runtime_fixture.runtime_id}/")
    diagnostics = operator_client.get(f"/admin/runtimes/{runtime_fixture.runtime_id}/diagnostics/")
    providers = operator_client.get("/admin/providers/")
    models = operator_client.get("/admin/models/")
    integrations = operator_client.get("/admin/integrations/")
    secrets = operator_client.get("/admin/secrets/")

    assert admin_index.status_code == 200
    assert dashboard.status_code == 302
    assert dashboard.headers["Location"] == "/admin/"
    assert runtimes.status_code == 302
    assert runtimes.headers["Location"] == "/admin/"
    assert wizard.status_code == 200
    assert wizard_skills.status_code == 200
    assert detail.status_code == 200
    assert diagnostics.status_code == 200
    assert providers.status_code == 200
    assert models.status_code == 200
    assert integrations.status_code == 200
    assert secrets.status_code == 200
    assert b"Aquarium Operator Console" in admin_index.content
    assert b"/admin/domain/runtime/" not in admin_index.content
    assert b"Limits &amp; Keys" in detail.content
    assert b"Operator Skills" in detail.content
    assert b"Runtime Wizard" in wizard.content
    assert b"Operator Skills" in wizard_skills.content
    assert b"Diagnostics" in diagnostics.content
    assert b"Providers" in providers.content
    assert b"Secrets" in secrets.content


@pytest.mark.django_db
def test_admin_home_is_read_only(operator_client: Client, runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr(
        "orchestrator.service_layer.runtime_detail_payload",
        lambda runtime_id: (_ for _ in ()).throw(AssertionError("Admin home must not use full runtime detail payloads")),
    )
    monkeypatch.setattr(
        "orchestrator.service_layer.backfill_runtime_related_records",
        lambda runtime_id=None: (_ for _ in ()).throw(AssertionError("Admin home must not backfill records")),
    )
    monkeypatch.setattr(
        "orchestrator.service_layer.monitoring_surface_payload",
        lambda: {
            "url": "http://127.0.0.1:13000",
            "available": False,
            "healthy": False,
            "label": "Grafana offline",
            "reason": "Monitoring stack is not bootstrapped.",
        },
    )

    response = operator_client.get("/admin/")

    assert response.status_code == 200
    assert b"demo-runtime" in response.content
    assert b"Grafana offline" in response.content
    assert b">Offline<" in response.content


@pytest.mark.django_db
def test_diagnostics_summary_get_is_read_only(operator_client: Client, runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr(
        "orchestrator.service_layer.refresh_runtime_diagnostics",
        lambda runtime_id: (_ for _ in ()).throw(AssertionError("GET diagnostics summary must not refresh")),
    )
    monkeypatch.setattr(
        "orchestrator.service_layer.runtime_secret_check",
        lambda runtime_id: (_ for _ in ()).throw(AssertionError("GET diagnostics summary must not verify secrets")),
    )

    response = operator_client.get(f"/api/runtimes/{runtime_fixture.runtime_id}/diagnostics/summary")

    assert response.status_code == 200
    assert response.json()["runtime_id"] == runtime_fixture.runtime_id
    assert response.json()["metrics"]["summary"]["status"] == "unknown"


@pytest.mark.django_db
def test_admin_pages_render(operator_client: Client, runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr(
        "orchestrator.service_layer.refresh_runtime_diagnostics",
        lambda runtime_id: (_ for _ in ()).throw(AssertionError("GET views must not refresh diagnostics")),
    )
    monkeypatch.setattr(
        "orchestrator.service_layer.runtime_secret_check",
        lambda runtime_id: (_ for _ in ()).throw(AssertionError("GET views must not verify secrets")),
    )
    monkeypatch.setattr("orchestrator.service_layer.inspect_runtime_key", lambda runtime_id: {"status": "cached"})

    dashboard = operator_client.get("/admin/dashboard/", follow=False)
    diagnostics = operator_client.get(f"/admin/runtimes/{runtime_fixture.runtime_id}/diagnostics/")

    assert dashboard.status_code == 302
    assert dashboard.headers["Location"] == "/admin/"
    assert diagnostics.status_code == 200
    assert runtime_fixture.runtime_id.encode("utf-8") in diagnostics.content


@pytest.mark.django_db
def test_raw_admin_routes_redirect_to_operator_pages(operator_client: Client, runtime_fixture: Runtime) -> None:
    snapshot = RuntimeDiagnosticSnapshot.objects.create(runtime=runtime_fixture)
    chat_session = runtime_fixture.chat_sessions.create(title="Demo chat")

    runtime_redirect = operator_client.get("/admin/domain/runtime/", follow=False)
    providers_redirect = operator_client.get("/admin/domain/providerconnection/", follow=False)
    models_redirect = operator_client.get("/admin/domain/providermodel/", follow=False)
    integrations_redirect = operator_client.get("/admin/domain/integrationconnection/", follow=False)
    secrets_redirect = operator_client.get("/admin/domain/runtimesecretref/", follow=False)
    actions_redirect = operator_client.get("/admin/domain/runtimeactionlog/", follow=False)
    snapshot_redirect = operator_client.get(f"/admin/domain/runtimediagnosticsnapshot/{snapshot.pk}/change/", follow=False)
    chat_redirect = operator_client.get(f"/admin/domain/runtimechatsession/{chat_session.pk}/change/", follow=False)

    assert runtime_redirect.status_code == 302
    assert runtime_redirect.headers["Location"] == "/admin/"
    assert providers_redirect.headers["Location"] == "/admin/providers/"
    assert models_redirect.headers["Location"] == "/admin/models/"
    assert integrations_redirect.headers["Location"] == "/admin/integrations/"
    assert secrets_redirect.headers["Location"] == "/admin/secrets/"
    assert actions_redirect.headers["Location"] == "/admin/"
    assert snapshot_redirect.headers["Location"] == f"/admin/runtimes/{runtime_fixture.runtime_id}/diagnostics/"
    assert chat_redirect.headers["Location"] == f"/admin/runtimes/{runtime_fixture.runtime_id}/chat/?session={chat_session.pk}"


def test_render_stack_config_deduplicates_default_model_alias() -> None:
    rendered = render_stack_config(
        extra_models=[
            {
                "model_name": DEFAULT_MODEL_ALIAS,
                "litellm_params": {
                    "model": DEFAULT_PROVIDER_MODEL,
                    "api_key": "os.environ/OPENROUTER_API_KEY",
                },
                "model_info": {
                    "input_cost_per_token": 3.25e-07,
                    "output_cost_per_token": 1.95e-06,
                },
            }
        ]
    )

    assert rendered.count(f"model_name: {DEFAULT_MODEL_ALIAS}") == 1


@pytest.mark.django_db
def test_update_runtime_limits_auto_applies_litellm_without_recreate(runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.mirror_json_state", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer._current_runtime_key", lambda api_url, runtime: "vk-demo")
    monkeypatch.setattr("orchestrator.service_layer.master_key_from_infisical", lambda api_url: "master-key")

    seen: dict[str, object] = {}

    def fake_update_virtual_key(base_url, master_key, **payload):
        seen["base_url"] = base_url
        seen["master_key"] = master_key
        seen["payload"] = payload
        return {"ok": True}

    recreate_calls: list[str] = []

    monkeypatch.setattr("orchestrator.service_layer.update_virtual_key", fake_update_virtual_key)
    monkeypatch.setattr("orchestrator.service_layer.recreate_runtime", lambda runtime_id, actor=None: recreate_calls.append(runtime_id))

    updated = update_runtime_limits(runtime_fixture.runtime_id, budget_usd=12.5, rpm_limit=90, tpm_limit=75000)

    runtime_fixture.refresh_from_db()
    assert updated["budget_usd"] == 12.5
    assert updated["rpm_limit"] == 90
    assert updated["tpm_limit"] == 75000
    assert runtime_fixture.litellm_budget_usd == 12.5
    assert runtime_fixture.litellm_rpm_limit == 90
    assert runtime_fixture.litellm_tpm_limit == 75000
    assert seen["payload"]["budget_usd"] == 12.5
    assert seen["payload"]["rpm_limit"] == 90
    assert seen["payload"]["tpm_limit"] == 75000
    assert seen["payload"]["model_aliases"] == [runtime_fixture.model]
    assert recreate_calls == []


@pytest.mark.django_db
def test_update_runtime_limits_model_change_rewrites_bootstrap_and_recreates(runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.mirror_json_state", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer._current_runtime_key", lambda api_url, runtime: "vk-demo")
    monkeypatch.setattr("orchestrator.service_layer.master_key_from_infisical", lambda api_url: "master-key")
    monkeypatch.setattr("orchestrator.service_layer.update_virtual_key", lambda base_url, master_key, **payload: {"payload": payload})

    connection = ProviderConnection.objects.create(
        name="tenant-model-provider",
        display_name="Tenant Model Provider",
        provider_kind="openrouter",
        scope=ConnectionScope.TENANT,
        tenant=runtime_fixture.tenant,
        status=ConnectionStatus.CONFIGURED,
    )
    provider_model = ProviderModel.objects.create(
        alias="openai/test/updated-model",
        display_name="Updated Model",
        provider_model="openrouter/test/updated-model",
        provider_connection=connection,
        tenant=runtime_fixture.tenant,
        is_custom=True,
        is_enabled=True,
    )

    recreate_calls: list[str] = []

    def fake_recreate_runtime(runtime_id, actor=None):
        recreate_calls.append(runtime_id)
        return Runtime.objects.get(runtime_id=runtime_id)

    monkeypatch.setattr("orchestrator.service_layer.recreate_runtime", fake_recreate_runtime)

    updated = update_runtime_limits(runtime_fixture.runtime_id, model=provider_model.alias)

    runtime_fixture.refresh_from_db()
    env_text = Path(runtime_fixture.runtime_env_file).read_text()

    assert updated["model"] == provider_model.alias
    assert runtime_fixture.model == provider_model.alias
    assert runtime_fixture.litellm_model_alias == provider_model.alias
    assert runtime_fixture.default_provider_connection == connection
    assert runtime_fixture.default_provider_model == provider_model
    assert "NULLCLAW_MODEL=openai/test/updated-model" in env_text
    assert f"NULLCLAW_MAX_ACTIONS_PER_HOUR={NULLCLAW_MAX_ACTIONS_PER_HOUR}" in env_text
    assert recreate_calls == [runtime_fixture.runtime_id]


@pytest.mark.django_db
def test_upsert_runtime_secret_recreates_runtime(runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.operator_token", lambda api_url: "operator-token")
    monkeypatch.setattr("orchestrator.service_layer.upsert_secret", lambda *args, **kwargs: None)

    recreate_calls: list[str] = []

    def fake_recreate_runtime(runtime_id, actor=None):
        recreate_calls.append(runtime_id)
        return Runtime.objects.get(runtime_id=runtime_id)

    monkeypatch.setattr("orchestrator.service_layer.recreate_runtime", fake_recreate_runtime)

    ref = upsert_runtime_secret(runtime_fixture.runtime_id, SecretKind.TELEGRAM_BOT_TOKEN, "updated-telegram-token")

    assert ref.secret_kind == SecretKind.TELEGRAM_BOT_TOKEN
    assert recreate_calls == [runtime_fixture.runtime_id]


@pytest.mark.django_db
def test_upsert_integration_connection_recreates_runtime_and_updates_env(runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.operator_token", lambda api_url: "operator-token")
    monkeypatch.setattr("orchestrator.service_layer.upsert_secret", lambda *args, **kwargs: None)

    recreate_calls: list[str] = []

    def fake_recreate_runtime(runtime_id, actor=None):
        recreate_calls.append(runtime_id)
        return Runtime.objects.get(runtime_id=runtime_id)

    monkeypatch.setattr("orchestrator.service_layer.recreate_runtime", fake_recreate_runtime)

    connection = upsert_integration_connection(
        integration_type="slack",
        runtime_id=runtime_fixture.runtime_id,
        enabled=True,
        config={"enabled": True},
    )

    runtime_fixture.refresh_from_db()
    env_text = Path(runtime_fixture.runtime_env_file).read_text()

    assert connection.integration_type == "slack"
    assert runtime_fixture.desired_channels["slack"] is True
    assert "NULLCLAW_ENABLE_SLACK=true" in env_text
    assert recreate_calls == [runtime_fixture.runtime_id]


@pytest.mark.django_db
def test_delete_search_integration_clears_runtime_settings_and_recreates(runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)

    runtime_fixture.settings = {"search_provider": "serpapi", "search_base_url": "http://search.local"}
    runtime_fixture.save(update_fields=["settings", "updated_at"])
    connection = IntegrationConnection.objects.create(
        name=f"{runtime_fixture.runtime_id}-search",
        display_name="Demo Search",
        integration_type="search",
        scope=ConnectionScope.RUNTIME,
        tenant=runtime_fixture.tenant,
        runtime=runtime_fixture,
        status=ConnectionStatus.CONFIGURED,
        config={"provider": "serpapi", "base_url": "http://search.local"},
    )

    recreate_calls: list[str] = []

    def fake_recreate_runtime(runtime_id, actor=None):
        recreate_calls.append(runtime_id)
        return Runtime.objects.get(runtime_id=runtime_id)

    monkeypatch.setattr("orchestrator.service_layer.recreate_runtime", fake_recreate_runtime)

    delete_integration_connection_service(connection.pk)

    runtime_fixture.refresh_from_db()
    env_text = Path(runtime_fixture.runtime_env_file).read_text()

    assert "search_provider" not in runtime_fixture.settings
    assert "search_base_url" not in runtime_fixture.settings
    assert "NULLCLAW_SEARCH_PROVIDER" not in env_text
    assert "NULLCLAW_SEARCH_BASE_URL" not in env_text
    assert recreate_calls == [runtime_fixture.runtime_id]


@pytest.mark.django_db
def test_runtime_limits_patch_applies_immediately(operator_client: Client, runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.mirror_json_state", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer._current_runtime_key", lambda api_url, runtime: "vk-demo")
    monkeypatch.setattr("orchestrator.service_layer.master_key_from_infisical", lambda api_url: "master-key")
    monkeypatch.setattr("orchestrator.service_layer.recreate_runtime", lambda runtime_id, actor=None: Runtime.objects.get(runtime_id=runtime_id))

    calls: list[dict[str, object]] = []

    def fake_update_virtual_key(base_url, master_key, **payload):
        calls.append(payload)
        return {"ok": True}

    monkeypatch.setattr("orchestrator.service_layer.update_virtual_key", fake_update_virtual_key)

    response = operator_client.patch(
        f"/api/runtimes/{runtime_fixture.runtime_id}/limits",
        data=json.dumps({"budget_usd": 7.5, "rpm_limit": 44, "tpm_limit": 22000}),
        content_type="application/json",
    )

    runtime_fixture.refresh_from_db()

    assert response.status_code == 200
    assert response.json()["budget_usd"] == 7.5
    assert runtime_fixture.litellm_rpm_limit == 44
    assert calls and calls[0]["budget_usd"] == 7.5


def test_render_nullclaw_config_uses_effectively_unbounded_action_cap(tmp_path) -> None:
    home = tmp_path / "nullclaw-home"
    env = {
        "NULLCLAW_HOME": str(home),
        "NULLCLAW_ENABLE_TELEGRAM": "false",
        "LITELLM_API_KEY": "runtime-key",
        "LITELLM_BASE_URL": "http://host.docker.internal:14000/v1",
    }

    subprocess.run(
        ["sh", "scripts/render-nullclaw-config.sh"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
    )

    rendered = json.loads((home / "config.json").read_text())

    assert rendered["autonomy"]["max_actions_per_hour"] == int(NULLCLAW_MAX_ACTIONS_PER_HOUR)


@pytest.mark.django_db
def test_sqlite_connection_uses_wal_and_busy_timeout() -> None:
    if connection.vendor != "sqlite":
        pytest.skip("SQLite-specific test")

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode;")
        journal_mode = cursor.fetchone()[0]
        cursor.execute("PRAGMA busy_timeout;")
        busy_timeout = cursor.fetchone()[0]

    assert connection.settings_dict["OPTIONS"]["timeout"] == 20
    assert busy_timeout == 20000
    assert journal_mode.lower() in {"wal", "memory"}


@pytest.mark.django_db
def test_agent_draft_launch_and_stop_flow(runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.operator_token", lambda api_url: "operator-token")
    monkeypatch.setattr(
        "orchestrator.service_layer.ensure_project",
        lambda *args, **kwargs: {
            "id": "workspace-default-id",
            "slug": "workspace-default",
        },
    )
    monkeypatch.setattr("orchestrator.service_layer.upsert_secret", lambda *args, **kwargs: None)
    monkeypatch.setattr("orchestrator.service_layer.read_secret_with_token", lambda *args, **kwargs: "resolved-secret")

    upsert_workspace_secret("telegram-main", SecretKind.TELEGRAM_BOT_TOKEN, "telegram-secret-token")
    upsert_workspace_secret("telegram-allow", SecretKind.TELEGRAM_ALLOW_FROM, "373793732")

    monkeypatch.setattr(
        "orchestrator.service_layer.bootstrap_skill_catalog",
        lambda: [
            SkillCatalogEntry.objects.create(
                key="telegram-ops",
                display_name="Telegram Ops",
                description="Telegram-first operator behaviors",
                source_path="skills/telegram_ops.md",
            ),
            SkillCatalogEntry.objects.create(
                key="status-reporter",
                display_name="Status Reporter",
                description="Summaries and structured updates",
                source_path="skills/status_reporter.md",
            ),
        ],
    )

    created_runtime_ids: list[str] = []

    def fake_create_runtime(request, actor=None):
        created_runtime_ids.append(request.runtime_id)
        return Runtime.objects.create(
            runtime_id=request.runtime_id,
            enabled=True,
            tenant=runtime_fixture.tenant,
            plan=runtime_fixture.plan,
            runtime_profile=runtime_fixture.runtime_profile,
            gateway_port=request.gateway_port,
            model=request.model,
            telegram_enabled=request.telegram_enabled,
            desired_channels={"telegram": request.telegram_enabled},
            settings={"system_prompt": "compiled"},
            infisical_project_slug=request.runtime_id,
            infisical_project_id=f"project-{request.runtime_id}",
            infisical_env="prod",
            infisical_path="/runtime",
            litellm_key_name=f"runtime-{request.runtime_id}",
            litellm_budget_usd=request.budget_usd,
            litellm_rpm_limit=request.rpm_limit,
            litellm_tpm_limit=request.tpm_limit,
            runtime_env_file=runtime_fixture.runtime_env_file,
            runtime_home=runtime_fixture.runtime_home,
            workspace_dir=runtime_fixture.workspace_dir,
            generated_config_path=runtime_fixture.generated_config_path,
        )

    monkeypatch.setattr("orchestrator.service_layer.create_or_update_runtime", fake_create_runtime)
    monkeypatch.setattr(
        "orchestrator.service_layer.stop_runtime",
        lambda runtime_id, actor=None: Runtime.objects.filter(runtime_id=runtime_id).update(lifecycle_status="stopped"),
    )

    agent = create_draft_agent(
        AgentCreateRequest(
            name="Research Bot",
            slug="research-bot",
            description="Telegram-first analyst",
            personality_prompt="Be concise and analytical.",
            model_alias=runtime_fixture.model,
            gateway_port=3911,
            channel_config={"telegram_enabled": True},
            secret_bindings={
                "telegram_bot_token": "telegram-main",
                "telegram_allow_from": "telegram-allow",
            },
            skill_keys=["telegram-ops", "status-reporter"],
            litellm_budget_usd=4.5,
            litellm_rpm_limit=20,
            litellm_tpm_limit=12000,
        )
    )

    assert agent.status == "draft"
    assert list(agent.current_build_spec.skill_bindings.order_by("position").values_list("skill__key", flat=True)) == [
        "telegram-ops",
        "status-reporter",
    ]
    assert agent.secret_bindings.count() == 2

    deployment = launch_agent(agent.slug)
    agent.refresh_from_db()

    assert deployment.status == "running"
    assert agent.status == "running"
    assert agent.current_deployment == deployment
    assert created_runtime_ids == ["research-bot"]

    stopped = stop_agent(agent.slug)
    agent.refresh_from_db()
    deployment.refresh_from_db()

    assert stopped.status == "stopped"
    assert deployment.status == "stopped"
    assert agent.status == "stopped"


@pytest.mark.django_db
def test_agent_api_and_operator_pages_render(operator_client: Client, runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.operator_token", lambda api_url: "operator-token")
    monkeypatch.setattr(
        "orchestrator.service_layer.ensure_project",
        lambda *args, **kwargs: {
            "id": "workspace-default-id",
            "slug": "workspace-default",
        },
    )
    monkeypatch.setattr("orchestrator.service_layer.upsert_secret", lambda *args, **kwargs: None)
    monkeypatch.setattr("orchestrator.service_layer.read_secret_with_token", lambda *args, **kwargs: "resolved-secret")

    SkillCatalogEntry.objects.create(
        key="telegram-ops",
        display_name="Telegram Ops",
        description="Telegram-first operator behaviors",
        source_path="skills/telegram_ops.md",
    )

    created = operator_client.post(
        "/api/workspace/secrets",
        data=json.dumps(
            {
                "name": "telegram-main",
                "secret_kind": SecretKind.TELEGRAM_BOT_TOKEN,
                "value": "telegram-secret-token",
            }
        ),
        content_type="application/json",
    )
    assert created.status_code == 201
    assert "telegram-secret-token" not in created.content.decode("utf-8")

    agent_response = operator_client.post(
        "/api/agents",
        data=json.dumps(
            {
                "name": "Ops Bot",
                "slug": "ops-bot",
                "description": "Operator-facing Telegram agent",
                "personality_prompt": "Be calm and useful.",
                "model_alias": runtime_fixture.model,
                "gateway_port": 3912,
                "channel_config": {"telegram_enabled": True},
                "secret_bindings": {"telegram_bot_token": "telegram-main"},
                "skill_keys": ["telegram-ops"],
            }
        ),
        content_type="application/json",
    )

    assert agent_response.status_code == 201
    assert agent_response.json()["agent"]["slug"] == "ops-bot"
    assert agent_response.json()["agent"]["status"] == "draft"

    listing = operator_client.get("/api/agents")
    catalog = operator_client.get("/api/skills/catalog")
    vault = operator_client.get("/api/workspace/secrets")
    home = operator_client.get("/admin/")
    wizard = operator_client.get("/admin/agents/new/")
    studio = operator_client.get("/admin/agents/ops-bot/")

    assert listing.status_code == 200
    assert any(item["slug"] == "ops-bot" for item in listing.json()["items"])
    assert catalog.status_code == 200
    assert catalog.json()["items"][0]["key"] == "telegram-ops"
    assert vault.status_code == 200
    assert vault.json()["items"][0]["name"] == "telegram-main"
    assert home.status_code == 200
    assert wizard.status_code == 200
    assert studio.status_code == 200
    assert b"Agent Home" in home.content
    assert b"Create Agent" in wizard.content
    assert b"Agent Studio" in studio.content


@pytest.mark.django_db
def test_agent_wizard_renders_personality_preset_cards(operator_client: Client, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)

    response = operator_client.get("/admin/agents/new/")

    assert response.status_code == 200
    assert b"Choose a personality preset" in response.content
    assert b"mara-field-operator" in response.content
    assert b"Mara" in response.content
    assert b"The Field Operator" in response.content


@pytest.mark.django_db
def test_admin_home_inline_agent_builder_renders_personality_preset_cards(
    operator_client: Client, monkeypatch
) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)

    response = operator_client.get("/admin/")

    assert response.status_code == 200
    assert b"Choose a personality preset" in response.content
    assert b"viktor-hard-reviewer" in response.content
    assert b"Viktor" in response.content
    assert b"The Hard Reviewer" in response.content


@pytest.mark.django_db
def test_agent_wizard_post_saves_custom_personality_prompt_exactly(
    operator_client: Client, monkeypatch
) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    custom_prompt = "  Custom prompt\nwith deliberate spacing\nand # symbols.  "

    response = operator_client.post(
        "/admin/agents/new/",
        data={
            "action": "create_agent_inline",
            "name": "Custom Bot",
            "slug": "custom-bot",
            "description": "Uses edited personality text.",
            "personality_prompt": custom_prompt,
            "model_alias": "openai/qwen/qwen3.6-plus",
            "gateway_port": "3915",
            "telegram_enabled": "on",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/admin/agents/custom-bot/"
    assert AgentBuildSpec.objects.get(agent__slug="custom-bot").personality_prompt == custom_prompt


@pytest.mark.django_db
def test_agent_build_spec_and_deployments_api(operator_client: Client, runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.operator_token", lambda api_url: "operator-token")
    monkeypatch.setattr(
        "orchestrator.service_layer.ensure_project",
        lambda *args, **kwargs: {
            "id": "workspace-default-id",
            "slug": "workspace-default",
        },
    )
    monkeypatch.setattr("orchestrator.service_layer.upsert_secret", lambda *args, **kwargs: None)
    monkeypatch.setattr("orchestrator.service_layer.read_secret_with_token", lambda *args, **kwargs: "resolved-secret")
    monkeypatch.setattr(
        "orchestrator.service_layer.create_or_update_runtime",
        lambda request, actor=None: Runtime.objects.create(
            runtime_id=request.runtime_id,
            enabled=True,
            tenant=runtime_fixture.tenant,
            plan=runtime_fixture.plan,
            runtime_profile=runtime_fixture.runtime_profile,
            gateway_port=request.gateway_port,
            model=request.model,
            telegram_enabled=request.telegram_enabled,
            desired_channels={"telegram": request.telegram_enabled},
            settings=request.settings or {},
            infisical_project_slug=request.runtime_id,
            infisical_project_id=f"project-{request.runtime_id}",
            infisical_env="prod",
            infisical_path="/runtime",
            litellm_key_name=f"runtime-{request.runtime_id}",
            runtime_env_file=runtime_fixture.runtime_env_file,
            runtime_home=runtime_fixture.runtime_home,
            workspace_dir=runtime_fixture.workspace_dir,
            generated_config_path=runtime_fixture.generated_config_path,
        ),
    )

    SkillCatalogEntry.objects.create(
        key="telegram-ops",
        display_name="Telegram Ops",
        description="Telegram-first operator behaviors",
        source_path="skills/telegram_ops.md",
    )
    operator_client.post(
        "/api/workspace/secrets",
        data=json.dumps({"name": "telegram-main", "secret_kind": SecretKind.TELEGRAM_BOT_TOKEN, "value": "token"}),
        content_type="application/json",
    )

    created = operator_client.post(
        "/api/agents",
        data=json.dumps(
            {
                "name": "Planner Bot",
                "slug": "planner-bot",
                "personality_prompt": "Initial prompt",
                "model_alias": runtime_fixture.model,
                "gateway_port": 3913,
                "channel_config": {"telegram_enabled": True},
                "secret_bindings": {"telegram_bot_token": "telegram-main"},
                "skill_keys": ["telegram-ops"],
            }
        ),
        content_type="application/json",
    )
    assert created.status_code == 201

    updated = operator_client.patch(
        "/api/agents/planner-bot/build-spec",
        data=json.dumps(
            {
                "personality_prompt": "Updated prompt",
                "litellm_budget_usd": 3.2,
                "litellm_rpm_limit": 22,
                "skill_keys": ["telegram-ops"],
            }
        ),
        content_type="application/json",
    )
    assert updated.status_code == 200
    assert updated.json()["build_spec"]["personality_prompt"] == "Updated prompt"

    launched = operator_client.post("/api/agents/planner-bot/launch")
    assert launched.status_code == 200

    skills = operator_client.get("/api/agents/planner-bot/skills")
    secrets = operator_client.get("/api/agents/planner-bot/secrets")
    deployments = operator_client.get("/api/agents/planner-bot/deployments")

    assert skills.status_code == 200
    assert skills.json()["items"][0]["key"] == "telegram-ops"
    assert secrets.status_code == 200
    assert secrets.json()["items"][0]["logical_role"] == "telegram_bot_token"
    assert deployments.status_code == 200
    assert deployments.json()["items"][0]["status"] == "running"


@pytest.mark.django_db
def test_backfill_agents_from_existing_runtimes(runtime_fixture: Runtime, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.service_layer.ensure_controlplane_ready", lambda: None)
    monkeypatch.setattr("orchestrator.service_layer.import_json_state_if_empty", lambda: None)
    monkeypatch.setattr(
        "orchestrator.service_layer.ensure_workspace",
        lambda actor=None, ensure_backend=False: Workspace.objects.create(
            slug="default-workspace",
            display_name="Default Workspace",
            authelia_subject="local-operator",
        ),
    )

    second_runtime = Runtime.objects.create(
        runtime_id="probe",
        enabled=True,
        tenant=runtime_fixture.tenant,
        plan=runtime_fixture.plan,
        runtime_profile=runtime_fixture.runtime_profile,
        gateway_port=3901,
        model="openai/qwen/qwen3.6-plus",
        telegram_enabled=False,
        desired_channels={},
        infisical_project_slug="probe",
        infisical_project_id="project-probe",
        infisical_env="prod",
        infisical_path="/runtime",
        litellm_key_name="runtime-probe",
        litellm_budget_usd=1.0,
        litellm_rpm_limit=10,
        litellm_tpm_limit=10000,
        runtime_env_file=runtime_fixture.runtime_env_file,
        runtime_home=runtime_fixture.runtime_home,
        workspace_dir=runtime_fixture.workspace_dir,
        generated_config_path=runtime_fixture.generated_config_path,
        lifecycle_status="running",
        health_status="healthy",
    )

    created = backfill_agents_from_runtimes()

    assert created == 2
    assert Agent.objects.count() == 2
    demo_agent = Agent.objects.get(slug=runtime_fixture.runtime_id)
    probe_agent = Agent.objects.get(slug=second_runtime.runtime_id)
    assert demo_agent.current_build_spec.gateway_port == runtime_fixture.gateway_port
    assert demo_agent.current_deployment.runtime_ref == runtime_fixture.runtime_id
    assert probe_agent.status == "running"
    assert probe_agent.current_deployment.status == "running"
