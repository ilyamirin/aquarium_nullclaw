from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from django.core.management import call_command
from django.db import transaction
from django.db.models import Max
from django.utils.text import slugify
from django.utils import timezone

from orchestrator.django import setup_django

setup_django()

from controlplane.domain.models import (
    Agent,
    AgentSecretBinding,
    AgentSkillBinding,
    AgentStatus,
    AgentBuildSpec,
    ChatRole,
    ConnectionScope,
    ConnectionStatus,
    Deployment,
    DeploymentStatus,
    IntegrationConnection,
    Plan,
    PrimaryChannel,
    ProviderConnection,
    ProviderKind,
    ProviderModel,
    Runtime,
    RuntimeActionLog,
    RuntimeChatMessage,
    RuntimeChatSession,
    RuntimeDiagnosticSnapshot,
    RuntimeHealthStatus,
    RuntimeLifecycleStatus,
    RuntimeProfile,
    RuntimeProfileSlug,
    RuntimeSecretRef,
    Secret,
    SecretKind,
    SkillCatalogEntry,
    Tenant,
    Workspace,
)
from orchestrator.compose import write_compose
from orchestrator.infisical import (
    InfisicalError,
    create_service_token,
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
    PriceInfo,
    containerized_api_url,
    create_virtual_key,
    default_base_url as default_litellm_base_url,
    default_api_url,
    delete_virtual_key,
    get_price_info,
    info_for_virtual_key,
    litellm_stack_env_defaults,
    master_key_from_infisical,
    runtime_base_url,
    status as litellm_status,
    update_virtual_key,
    write_stack_config,
    write_stack_env,
)
from orchestrator.models import RuntimeRecord, StateFile
from orchestrator.paths import (
    COMPOSE_FILE,
    COMPOSE_PROJECT_NAME,
    LITELLM_STACK_ENV_FILE,
    MONITORING_STACK_ENV_FILE,
    ROOT_DIR,
    runtime_dir,
    runtime_env_file,
    runtime_home,
    workspace_dir,
)
from orchestrator.shell import CommandError, run


@dataclass
class RuntimeCreateRequest:
    runtime_id: str
    gateway_port: int
    model: str = DEFAULT_MODEL_ALIAS
    telegram_enabled: bool = True
    telegram_bot_token: str = ""
    telegram_allow_from: str = "373793732"
    runtime_role: str | None = None
    budget_usd: float | None = None
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    tenant_slug: str | None = None
    plan_slug: str | None = None
    desired_channels: dict[str, bool] | None = None
    settings: dict[str, Any] | None = None
    default_provider_connection_id: int | None = None
    default_provider_model_id: int | None = None
    api_url: str = default_api_url()
    litellm_base_url: str = default_litellm_base_url()


@dataclass
class AgentCreateRequest:
    name: str
    slug: str
    description: str = ""
    personality_prompt: str = ""
    model_alias: str = DEFAULT_MODEL_ALIAS
    gateway_port: int | None = None
    runtime_template: str = "generic-runtime"
    environment_profile: dict[str, Any] | None = None
    startup_policy: dict[str, Any] | None = None
    observability_profile: dict[str, Any] | None = None
    autonomy_limits: dict[str, Any] | None = None
    safety_limits: dict[str, Any] | None = None
    channel_config: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    secret_bindings: dict[str, str] | None = None
    skill_keys: list[str] | None = None
    litellm_budget_usd: float | None = None
    litellm_rpm_limit: int | None = None
    litellm_tpm_limit: int | None = None


PROVIDER_CATALOG: list[dict[str, str]] = [
    {"kind": ProviderKind.OPENROUTER, "label": "OpenRouter"},
    {"kind": ProviderKind.OPENAI, "label": "OpenAI"},
    {"kind": ProviderKind.OPENAI_COMPATIBLE, "label": "OpenAI Compatible"},
    {"kind": ProviderKind.ANTHROPIC, "label": "Anthropic"},
    {"kind": ProviderKind.GEMINI, "label": "Gemini"},
    {"kind": ProviderKind.CUSTOM, "label": "Custom"},
]

RUNTIME_SECRET_DEFINITIONS: dict[str, dict[str, Any]] = {
    SecretKind.TELEGRAM_BOT_TOKEN: {
        "secret_name": "TELEGRAM_BOT_TOKEN",
        "integration_type": "telegram",
        "masked_label": "Configured",
    },
    SecretKind.TELEGRAM_ALLOW_FROM: {
        "secret_name": "TELEGRAM_ALLOW_FROM",
        "integration_type": "telegram",
        "masked_label": "Configured",
    },
    SecretKind.SLACK_BOT_TOKEN: {
        "secret_name": "SLACK_BOT_TOKEN",
        "integration_type": "slack",
        "masked_label": "Configured",
    },
    SecretKind.SLACK_APP_TOKEN: {
        "secret_name": "SLACK_APP_TOKEN",
        "integration_type": "slack",
        "masked_label": "Configured",
    },
    SecretKind.SLACK_SIGNING_SECRET: {
        "secret_name": "SLACK_SIGNING_SECRET",
        "integration_type": "slack",
        "masked_label": "Configured",
    },
    SecretKind.MATTERMOST_BOT_TOKEN: {
        "secret_name": "MATTERMOST_BOT_TOKEN",
        "integration_type": "mattermost",
        "masked_label": "Configured",
    },
    SecretKind.SEARCH_API_KEY: {
        "secret_name": "SEARCH_API_KEY",
        "integration_type": "search",
        "masked_label": "Configured",
    },
}

INTEGRATION_RUNTIME_CHANNELS: dict[str, str | None] = {
    "telegram": "telegram",
    "slack": "slack",
    "mattermost": "mattermost",
    "search": None,
}

NULLCLAW_MAX_ACTIONS_PER_HOUR = "1000000"


def ensure_controlplane_ready() -> None:
    setup_django()
    call_command("migrate", interactive=False, verbosity=0)
    bootstrap_reference_data()


def bootstrap_reference_data() -> None:
    for slug, name in [
        (RuntimeProfileSlug.LIVE, "Live"),
        (RuntimeProfileSlug.PROBE, "Probe"),
        (RuntimeProfileSlug.LIMIT_PROBE, "Limit Probe"),
        (RuntimeProfileSlug.PLAYGROUND, "Playground"),
        (RuntimeProfileSlug.CUSTOM, "Custom"),
    ]:
        RuntimeProfile.objects.get_or_create(slug=slug, defaults={"display_name": name})
    Tenant.objects.get_or_create(slug="default", defaults={"name": "Default Tenant"})
    Plan.objects.get_or_create(slug="default", defaults={"display_name": "Default Plan"})
    Workspace.objects.get_or_create(
        slug="default-workspace",
        defaults={
            "display_name": "Default Workspace",
            "authelia_subject": "local-operator",
            "infisical_project_slug": "workspace-default",
        },
    )


def import_json_state_if_empty() -> None:
    ensure_controlplane_ready()
    bootstrap_reference_data()
    if Runtime.objects.exists():
        return
    from orchestrator.state import load_state

    state = load_state()
    default_tenant = Tenant.objects.get(slug="default")
    default_plan = Plan.objects.get(slug="default")
    profile_map = {profile.slug: profile for profile in RuntimeProfile.objects.all()}
    for runtime in state.runtimes.values():
        tenant = Tenant.objects.get_or_create(
            slug=runtime.tenant_id or "default",
            defaults={"name": (runtime.tenant_id or "default").replace("-", " ").title()},
        )[0]
        plan = Plan.objects.get_or_create(
            slug=runtime.plan_id or "default",
            defaults={"display_name": (runtime.plan_id or "default").replace("-", " ").title()},
        )[0]
        Runtime.objects.create(
            runtime_id=runtime.id,
            enabled=runtime.enabled,
            tenant=tenant or default_tenant,
            plan=plan or default_plan,
            runtime_profile=profile_map.get(runtime.runtime_role) or profile_map[RuntimeProfileSlug.CUSTOM],
            gateway_port=runtime.gateway_port,
            model=runtime.model,
            telegram_enabled=runtime.telegram_enabled,
            desired_channels={"telegram": runtime.telegram_enabled},
            infisical_project_slug=runtime.infisical_project_slug,
            infisical_project_id=runtime.infisical_project_id,
            infisical_env=runtime.infisical_env,
            infisical_path=runtime.infisical_path,
            litellm_key_name=runtime.litellm_key_name,
            litellm_budget_usd=runtime.litellm_budget_usd,
            litellm_rpm_limit=runtime.litellm_rpm_limit,
            litellm_tpm_limit=runtime.litellm_tpm_limit,
            litellm_model_alias=runtime.litellm_model_alias,
            litellm_price_input_per_million_usd=runtime.litellm_price_input_per_million_usd,
            litellm_price_output_per_million_usd=runtime.litellm_price_output_per_million_usd,
            runtime_env_file=runtime.runtime_env_file,
            runtime_home=runtime.runtime_home,
            workspace_dir=runtime.workspace_dir,
            generated_config_path=runtime.generated_config_path,
        )
    backfill_runtime_related_records()


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


def _env_dict(path: str) -> dict[str, str]:
    return {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in Path(path).read_text().splitlines()
        if "=" in line
    }


def _host_api_url(api_url: str) -> str:
    if "host.docker.internal" in api_url:
        return api_url.replace("host.docker.internal", "127.0.0.1", 1)
    return api_url


def _runtime_api_url(api_url: str) -> str:
    if "127.0.0.1" in api_url or "localhost" in api_url:
        return api_url.replace("127.0.0.1", "host.docker.internal").replace("localhost", "host.docker.internal")
    return api_url


def _up_runtime(runtime_id: str) -> None:
    run(_compose_cmd("up", "-d", "--force-recreate", f"gateway-{runtime_id}"), cwd=str(Path.cwd()))


def _selected_provider_defaults(model_alias: str) -> tuple[ProviderConnection | None, ProviderModel | None]:
    provider_model = ProviderModel.objects.select_related("provider_connection").filter(alias=model_alias, is_enabled=True).first()
    if provider_model is None:
        return None, None
    return provider_model.provider_connection, provider_model


def _runtime_record_from_db(runtime: Runtime) -> RuntimeRecord:
    return RuntimeRecord(
        id=runtime.runtime_id,
        enabled=runtime.enabled,
        gateway_port=runtime.gateway_port,
        telegram_enabled=runtime.telegram_enabled,
        model=runtime.model,
        runtime_role=runtime.runtime_profile.slug if runtime.runtime_profile else RuntimeProfileSlug.CUSTOM,
        tenant_id=runtime.tenant.slug if runtime.tenant else None,
        plan_id=runtime.plan.slug if runtime.plan else None,
        infisical_project_slug=runtime.infisical_project_slug,
        infisical_project_id=runtime.infisical_project_id,
        infisical_env=runtime.infisical_env,
        infisical_path=runtime.infisical_path,
        litellm_key_name=runtime.litellm_key_name,
        litellm_budget_usd=runtime.litellm_budget_usd,
        litellm_rpm_limit=runtime.litellm_rpm_limit,
        litellm_tpm_limit=runtime.litellm_tpm_limit,
        litellm_model_alias=runtime.litellm_model_alias,
        litellm_price_input_per_million_usd=runtime.litellm_price_input_per_million_usd,
        litellm_price_output_per_million_usd=runtime.litellm_price_output_per_million_usd,
        runtime_env_file=runtime.runtime_env_file,
        runtime_home=runtime.runtime_home,
        workspace_dir=runtime.workspace_dir,
        generated_config_path=runtime.generated_config_path,
    )


def _state_from_db() -> StateFile:
    runtimes = {runtime.runtime_id: _runtime_record_from_db(runtime) for runtime in Runtime.objects.all()}
    return StateFile(runtimes=runtimes)


def sync_compose_from_db() -> None:
    write_compose(_state_from_db())


def mirror_json_state() -> None:
    from orchestrator.state import save_state

    save_state(_state_from_db())


AGENT_SKILL_CATALOG: list[dict[str, str]] = [
    {
        "key": "telegram-ops",
        "display_name": "Telegram Ops",
        "description": "Operator-friendly Telegram messaging behaviors.",
        "source_path": "knowledge/skills/telegram-ops.md",
    },
    {
        "key": "status-reporter",
        "display_name": "Status Reporter",
        "description": "Concise summaries, updates, and structured reporting.",
        "source_path": "knowledge/skills/status-reporter.md",
    },
    {
        "key": "retrieval-briefing",
        "display_name": "Retrieval Briefing",
        "description": "Summarize retrieved context before taking action.",
        "source_path": "knowledge/skills/retrieval-briefing.md",
    },
]


def _workspace_subject(actor: Any = None) -> str:
    if actor is not None and getattr(actor, "username", ""):
        return str(actor.username)
    return "local-operator"


def _workspace_slug(subject: str) -> str:
    slug = slugify(subject) or "default-workspace"
    return slug[:50]


def _next_agent_gateway_port() -> int:
    highest = AgentBuildSpec.objects.aggregate(highest=Max("gateway_port"))["highest"] or 3009
    return highest + 1


def _workspace_secret_backend_name(secret_kind: str, name: str) -> str:
    base = slugify(name).replace("-", "_").upper() or "SECRET"
    return f"WORKSPACE_{base}"


def ensure_workspace(actor: Any = None, *, ensure_backend: bool = True) -> Workspace:
    ensure_controlplane_ready()
    subject = _workspace_subject(actor)
    workspace, _ = Workspace.objects.get_or_create(
        authelia_subject=subject,
        defaults={
            "slug": _workspace_slug(subject),
            "display_name": "Default Workspace",
            "infisical_project_slug": f"workspace-{_workspace_slug(subject)}",
        },
    )
    if ensure_backend and not workspace.infisical_project_id:
        project = ensure_project(operator_token(default_api_url()), workspace.infisical_project_slug)
        workspace.infisical_project_id = project["id"]
        workspace.infisical_project_slug = project["slug"]
        workspace.save(
            update_fields=[
                "infisical_project_id",
                "infisical_project_slug",
                "updated_at",
            ]
        )
    return workspace


def bootstrap_skill_catalog() -> list[SkillCatalogEntry]:
    ensure_controlplane_ready()
    items: list[SkillCatalogEntry] = []
    for entry in AGENT_SKILL_CATALOG:
        skill, _ = SkillCatalogEntry.objects.update_or_create(
            key=entry["key"],
            defaults={
                "display_name": entry["display_name"],
                "description": entry["description"],
                "source_path": entry["source_path"],
                "is_enabled": True,
            },
        )
        items.append(skill)
    return items


def skill_catalog_entries() -> list[SkillCatalogEntry]:
    bootstrap_skill_catalog()
    order = [entry["key"] for entry in AGENT_SKILL_CATALOG]
    items = {skill.key: skill for skill in SkillCatalogEntry.objects.filter(is_enabled=True)}
    return [items[key] for key in order if key in items] + [skill for key, skill in items.items() if key not in order]


def list_agents() -> list[Agent]:
    ensure_controlplane_ready()
    backfill_agents_from_runtimes()
    return list(
        Agent.objects.select_related("workspace", "current_build_spec", "current_deployment")
        .prefetch_related("current_build_spec__skill_bindings__skill", "current_build_spec__secret_bindings__secret")
        .order_by("slug")
    )


def get_agent(slug: str) -> Agent:
    ensure_controlplane_ready()
    backfill_agents_from_runtimes()
    return Agent.objects.select_related("workspace", "current_build_spec", "current_deployment").get(slug=slug)


def list_workspace_secrets(actor: Any = None) -> list[Secret]:
    workspace = ensure_workspace(actor, ensure_backend=False)
    return list(workspace.secrets.order_by("name"))


def upsert_workspace_secret(name: str, secret_kind: str, secret_value: str, *, actor: Any = None) -> Secret:
    workspace = ensure_workspace(actor, ensure_backend=True)
    secret_name = _workspace_secret_backend_name(secret_kind, name)
    upsert_secret(
        default_api_url(),
        operator_token(default_api_url()),
        workspace.infisical_project_id,
        secret_name=secret_name,
        secret_value=secret_value,
        environment=workspace.infisical_env,
        secret_path=workspace.infisical_path,
    )
    secret, _ = Secret.objects.update_or_create(
        workspace=workspace,
        name=name,
        defaults={
            "secret_kind": secret_kind,
            "backend_ref": workspace.infisical_project_id,
            "backend_secret_name": secret_name,
            "masked_label": "Configured",
            "last_error": "",
        },
    )
    return secret


def _resolve_workspace_secret(secret: Secret) -> str:
    return read_secret_with_token(
        default_api_url(),
        operator_token(default_api_url()),
        project_id=secret.workspace.infisical_project_id,
        environment=secret.workspace.infisical_env,
        secret_path=secret.workspace.infisical_path,
        secret_name=secret.backend_secret_name,
    )


def create_draft_agent(request: AgentCreateRequest, *, actor: Any = None) -> Agent:
    ensure_controlplane_ready()
    workspace = ensure_workspace(actor, ensure_backend=False)
    bootstrap_skill_catalog()
    with transaction.atomic():
        agent = Agent.objects.create(
            workspace=workspace,
            name=request.name,
            slug=request.slug,
            description=request.description,
            status=AgentStatus.DRAFT,
            primary_channel=PrimaryChannel.TELEGRAM
            if (request.channel_config or {}).get("telegram_enabled", True)
            else PrimaryChannel.INTERNAL,
        )
        build_spec = AgentBuildSpec.objects.create(
            agent=agent,
            personality_prompt=request.personality_prompt,
            model_alias=request.model_alias,
            runtime_template=request.runtime_template,
            gateway_port=request.gateway_port or _next_agent_gateway_port(),
            environment_profile=request.environment_profile or {},
            startup_policy=request.startup_policy or {},
            observability_profile=request.observability_profile or {},
            autonomy_limits=request.autonomy_limits or {},
            safety_limits=request.safety_limits or {},
            channel_config=request.channel_config or {},
            settings=request.settings or {},
            litellm_budget_usd=request.litellm_budget_usd,
            litellm_rpm_limit=request.litellm_rpm_limit,
            litellm_tpm_limit=request.litellm_tpm_limit,
            build_state=AgentStatus.DRAFT,
        )
        for position, skill_key in enumerate(request.skill_keys or []):
            skill = SkillCatalogEntry.objects.get(key=skill_key)
            AgentSkillBinding.objects.create(build_spec=build_spec, skill=skill, position=position, enabled=True)
        for logical_role, secret_name in (request.secret_bindings or {}).items():
            secret = Secret.objects.get(workspace=workspace, name=secret_name)
            AgentSecretBinding.objects.create(build_spec=build_spec, secret=secret, logical_role=logical_role, required=True)
        agent.current_build_spec = build_spec
        agent.save(update_fields=["current_build_spec", "updated_at"])
    return agent


def _validate_agent_build_spec(build_spec: AgentBuildSpec) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not build_spec.model_alias:
        errors["model_alias"] = "Model alias is required."
    if build_spec.channel_config.get("telegram_enabled"):
        roles = set(build_spec.secret_bindings.values_list("logical_role", flat=True))
        if "telegram_bot_token" not in roles:
            errors["telegram_bot_token"] = "Telegram launch requires a bot token binding."
    return errors


def _compiled_prompt(build_spec: AgentBuildSpec) -> str:
    sections = [build_spec.personality_prompt.strip()]
    for binding in build_spec.skill_bindings.select_related("skill").order_by("position"):
        sections.append(f"[{binding.skill.key}] {binding.skill.description}".strip())
    return "\n\n".join(section for section in sections if section)


def launch_agent(slug: str, *, actor: Any = None) -> Deployment:
    ensure_controlplane_ready()
    agent = get_agent(slug)
    build_spec = agent.current_build_spec
    if build_spec is None:
        raise ValueError("Agent has no build spec.")
    errors = _validate_agent_build_spec(build_spec)
    if errors:
        raise ValueError("; ".join(errors.values()))

    build_spec.refresh_from_db()
    secret_map = {
        binding.logical_role: _resolve_workspace_secret(binding.secret)
        for binding in build_spec.secret_bindings.select_related("secret", "secret__workspace")
    }
    deployment = Deployment.objects.create(
        agent=agent,
        build_spec=build_spec,
        status=DeploymentStatus.LAUNCHING,
        launch_summary={"skill_keys": list(build_spec.skill_bindings.values_list("skill__key", flat=True))},
    )
    agent.status = AgentStatus.LAUNCHING
    agent.current_deployment = deployment
    agent.save(update_fields=["status", "current_deployment", "updated_at"])

    runtime = create_or_update_runtime(
        RuntimeCreateRequest(
            runtime_id=agent.slug,
            gateway_port=build_spec.gateway_port,
            model=build_spec.model_alias,
            telegram_enabled=bool(build_spec.channel_config.get("telegram_enabled", False)),
            telegram_bot_token=secret_map.get("telegram_bot_token", ""),
            telegram_allow_from=secret_map.get("telegram_allow_from", build_spec.channel_config.get("allow_from", "373793732")),
            runtime_role="custom",
            budget_usd=build_spec.litellm_budget_usd,
            rpm_limit=build_spec.litellm_rpm_limit,
            tpm_limit=build_spec.litellm_tpm_limit,
            desired_channels={"telegram": bool(build_spec.channel_config.get("telegram_enabled", False))},
            settings={
                **build_spec.settings,
                "system_prompt": _compiled_prompt(build_spec),
                "skill_stack": list(build_spec.skill_bindings.order_by("position").values_list("skill__key", flat=True)),
                "agent_slug": agent.slug,
                "build_spec_id": build_spec.pk,
            },
        ),
        actor=actor,
    )
    deployment.runtime = runtime
    deployment.runtime_ref = runtime.runtime_id
    deployment.status = DeploymentStatus.RUNNING
    deployment.launched_at = timezone.now()
    deployment.save(update_fields=["runtime", "runtime_ref", "status", "launched_at", "updated_at"])

    agent.status = AgentStatus.RUNNING
    agent.last_launched_at = deployment.launched_at
    agent.current_deployment = deployment
    agent.save(update_fields=["status", "last_launched_at", "current_deployment", "updated_at"])
    return deployment


def stop_agent(slug: str, *, actor: Any = None) -> Deployment:
    ensure_controlplane_ready()
    agent = get_agent(slug)
    deployment = agent.current_deployment
    if deployment is None:
        raise ValueError("Agent has no active deployment.")
    if deployment.runtime_ref:
        stop_runtime(deployment.runtime_ref, actor=actor)
    deployment.status = DeploymentStatus.STOPPED
    deployment.stopped_at = timezone.now()
    deployment.save(update_fields=["status", "stopped_at", "updated_at"])
    agent.status = AgentStatus.STOPPED
    agent.save(update_fields=["status", "updated_at"])
    return deployment


def _deployment_status_from_runtime(runtime: Runtime) -> str:
    if runtime.lifecycle_status == RuntimeLifecycleStatus.RUNNING:
        return DeploymentStatus.RUNNING
    if runtime.lifecycle_status == RuntimeLifecycleStatus.ERROR:
        return DeploymentStatus.FAILED
    return DeploymentStatus.STOPPED


def _agent_status_from_runtime(runtime: Runtime) -> str:
    if runtime.lifecycle_status == RuntimeLifecycleStatus.RUNNING:
        if runtime.health_status in {RuntimeHealthStatus.DEGRADED, RuntimeHealthStatus.UNHEALTHY}:
            return AgentStatus.DEGRADED
        return AgentStatus.RUNNING
    if runtime.lifecycle_status == RuntimeLifecycleStatus.STOPPED:
        return AgentStatus.STOPPED
    if runtime.lifecycle_status == RuntimeLifecycleStatus.ERROR:
        return AgentStatus.ERROR
    return AgentStatus.READY


def backfill_agents_from_runtimes(*, actor: Any = None) -> int:
    ensure_controlplane_ready()
    workspace = ensure_workspace(actor, ensure_backend=False)
    created = 0
    for runtime in Runtime.objects.select_related("tenant", "plan", "runtime_profile").order_by("runtime_id"):
        if Agent.objects.filter(slug=runtime.runtime_id).exists():
            continue
        with transaction.atomic():
            agent = Agent.objects.create(
                workspace=workspace,
                name=runtime.runtime_id.replace("-", " ").title(),
                slug=runtime.runtime_id,
                description="Backfilled from existing runtime inventory.",
                status=_agent_status_from_runtime(runtime),
                primary_channel=PrimaryChannel.TELEGRAM if runtime.telegram_enabled else PrimaryChannel.INTERNAL,
                last_launched_at=runtime.last_action_at,
            )
            build_spec = AgentBuildSpec.objects.create(
                agent=agent,
                personality_prompt="",
                model_alias=runtime.model,
                runtime_template="generic-runtime",
                gateway_port=runtime.gateway_port,
                channel_config={
                    "telegram_enabled": runtime.telegram_enabled,
                    "desired_channels": runtime.desired_channels,
                },
                settings=runtime.settings,
                litellm_budget_usd=runtime.litellm_budget_usd,
                litellm_rpm_limit=runtime.litellm_rpm_limit,
                litellm_tpm_limit=runtime.litellm_tpm_limit,
                build_state=_agent_status_from_runtime(runtime),
            )
            deployment = Deployment.objects.create(
                agent=agent,
                build_spec=build_spec,
                runtime=runtime,
                runtime_ref=runtime.runtime_id,
                status=_deployment_status_from_runtime(runtime),
                launch_summary={"source": "runtime-backfill"},
                launched_at=runtime.last_action_at,
                last_error=runtime.last_error,
            )
            agent.current_build_spec = build_spec
            agent.current_deployment = deployment
            agent.save(update_fields=["current_build_spec", "current_deployment", "updated_at"])
        created += 1
    return created


def agent_payload(agent: Agent) -> dict[str, Any]:
    build_spec = agent.current_build_spec
    deployment = agent.current_deployment
    return {
        "id": agent.pk,
        "name": agent.name,
        "slug": agent.slug,
        "description": agent.description,
        "status": agent.status,
        "primary_channel": agent.primary_channel,
        "model": build_spec.model_alias if build_spec else None,
        "gateway_port": build_spec.gateway_port if build_spec else None,
        "last_launch": agent.last_launched_at.isoformat() if agent.last_launched_at else None,
        "last_interaction": agent.last_interaction_at.isoformat() if agent.last_interaction_at else None,
        "current_deployment": deployment.pk if deployment else None,
    }


def agent_detail_payload(slug: str) -> dict[str, Any]:
    agent = get_agent(slug)
    build_spec = agent.current_build_spec
    deployment = agent.current_deployment
    return {
        "agent": agent_payload(agent),
        "build_spec": {
            "id": build_spec.pk,
            "personality_prompt": build_spec.personality_prompt,
            "model_alias": build_spec.model_alias,
            "runtime_template": build_spec.runtime_template,
            "gateway_port": build_spec.gateway_port,
            "channel_config": build_spec.channel_config,
            "litellm_budget_usd": build_spec.litellm_budget_usd,
            "litellm_rpm_limit": build_spec.litellm_rpm_limit,
            "litellm_tpm_limit": build_spec.litellm_tpm_limit,
            "skills": [
                {
                    "key": binding.skill.key,
                    "display_name": binding.skill.display_name,
                    "position": binding.position,
                }
                for binding in build_spec.skill_bindings.select_related("skill").order_by("position")
            ],
            "secrets": [
                {
                    "name": binding.secret.name,
                    "logical_role": binding.logical_role,
                    "masked_label": binding.secret.masked_label,
                    "secret_kind": binding.secret.secret_kind,
                }
                for binding in build_spec.secret_bindings.select_related("secret").order_by("logical_role")
            ],
        }
        if build_spec
        else None,
        "deployment": {
            "id": deployment.pk,
            "status": deployment.status,
            "runtime_ref": deployment.runtime_ref,
            "launched_at": deployment.launched_at.isoformat() if deployment.launched_at else None,
            "stopped_at": deployment.stopped_at.isoformat() if deployment.stopped_at else None,
            "last_error": deployment.last_error,
        }
        if deployment
        else None,
    }


def update_agent_build_spec(
    slug: str,
    *,
    personality_prompt: str | None = None,
    model_alias: str | None = None,
    gateway_port: int | None = None,
    channel_config: dict[str, Any] | None = None,
    litellm_budget_usd: float | None = None,
    litellm_rpm_limit: int | None = None,
    litellm_tpm_limit: int | None = None,
    skill_keys: list[str] | None = None,
) -> AgentBuildSpec:
    agent = get_agent(slug)
    build_spec = agent.current_build_spec
    if build_spec is None:
        raise ValueError("Agent has no build spec.")
    changed_fields: list[str] = ["updated_at"]
    if personality_prompt is not None:
        build_spec.personality_prompt = personality_prompt
        changed_fields.append("personality_prompt")
    if model_alias is not None:
        build_spec.model_alias = model_alias
        changed_fields.append("model_alias")
    if gateway_port is not None:
        build_spec.gateway_port = gateway_port
        changed_fields.append("gateway_port")
    if channel_config is not None:
        build_spec.channel_config = channel_config
        changed_fields.append("channel_config")
    if litellm_budget_usd is not None:
        build_spec.litellm_budget_usd = litellm_budget_usd
        changed_fields.append("litellm_budget_usd")
    if litellm_rpm_limit is not None:
        build_spec.litellm_rpm_limit = litellm_rpm_limit
        changed_fields.append("litellm_rpm_limit")
    if litellm_tpm_limit is not None:
        build_spec.litellm_tpm_limit = litellm_tpm_limit
        changed_fields.append("litellm_tpm_limit")
    build_spec.save(update_fields=changed_fields)
    if skill_keys is not None:
        build_spec.skill_bindings.all().delete()
        for position, skill_key in enumerate(skill_keys):
            skill = SkillCatalogEntry.objects.get(key=skill_key)
            AgentSkillBinding.objects.create(build_spec=build_spec, skill=skill, position=position, enabled=True)
    return build_spec


def agent_skills_payload(slug: str) -> list[dict[str, Any]]:
    build_spec = get_agent(slug).current_build_spec
    if build_spec is None:
        return []
    return [
        {
            "key": binding.skill.key,
            "display_name": binding.skill.display_name,
            "description": binding.skill.description,
            "position": binding.position,
            "enabled": binding.enabled,
        }
        for binding in build_spec.skill_bindings.select_related("skill").order_by("position")
    ]


def agent_secret_bindings_payload(slug: str) -> list[dict[str, Any]]:
    build_spec = get_agent(slug).current_build_spec
    if build_spec is None:
        return []
    return [
        {
            "name": binding.secret.name,
            "logical_role": binding.logical_role,
            "secret_kind": binding.secret.secret_kind,
            "masked_label": binding.secret.masked_label,
            "required": binding.required,
        }
        for binding in build_spec.secret_bindings.select_related("secret").order_by("logical_role")
    ]


def agent_deployments_payload(slug: str) -> list[dict[str, Any]]:
    agent = get_agent(slug)
    return [
        {
            "id": deployment.pk,
            "status": deployment.status,
            "runtime_ref": deployment.runtime_ref,
            "launched_at": deployment.launched_at.isoformat() if deployment.launched_at else None,
            "stopped_at": deployment.stopped_at.isoformat() if deployment.stopped_at else None,
            "last_error": deployment.last_error,
        }
        for deployment in agent.deployments.order_by("-created_at", "-pk")
    ]

def _current_runtime_key(api_url: str, runtime: Runtime) -> str | None:
    try:
        return read_secret_with_token(
            api_url,
            operator_token(api_url),
            runtime.infisical_project_id,
            runtime.infisical_env,
            runtime.infisical_path,
            "LITELLM_API_KEY",
        )
    except InfisicalError:
        return None


def _provision_litellm_key(runtime: Runtime, *, api_url: str, litellm_base_url: str) -> dict[str, Any]:
    created = create_virtual_key(
        litellm_base_url,
        master_key_from_infisical(api_url),
        key_alias=runtime.litellm_key_name or f"runtime-{runtime.runtime_id}",
        model_aliases=[runtime.model],
        budget_usd=runtime.litellm_budget_usd,
        rpm_limit=runtime.litellm_rpm_limit,
        tpm_limit=runtime.litellm_tpm_limit,
        metadata={
            "runtime_id": runtime.runtime_id,
            "runtime_role": runtime.runtime_profile.slug if runtime.runtime_profile else RuntimeProfileSlug.CUSTOM,
            "tenant_id": runtime.tenant.slug if runtime.tenant else None,
            "plan_id": runtime.plan.slug if runtime.plan else None,
            "managed_by": "aquarium-controlplane",
        },
    )
    if "key" not in created:
        raise LiteLLMError(f"LiteLLM key creation returned an unexpected payload: {json.dumps(created)}")
    return created


def _write_runtime_env(runtime: Runtime, service_token: str, api_url: str) -> None:
    env_path = Path(runtime.runtime_env_file)
    env_path.parent.mkdir(parents=True, exist_ok=True)
    values = {
        "INFISICAL_API_URL": _runtime_api_url(api_url),
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
    if runtime.desired_channels.get("slack"):
        values["NULLCLAW_ENABLE_SLACK"] = "true"
    if runtime.desired_channels.get("mattermost"):
        values["NULLCLAW_ENABLE_MATTERMOST"] = "true"
    if runtime.settings.get("http_enabled"):
        values["NULLCLAW_HTTP_ENABLED"] = "true"
    if runtime.settings.get("search_provider"):
        values["NULLCLAW_SEARCH_PROVIDER"] = str(runtime.settings["search_provider"])
    if runtime.settings.get("search_base_url"):
        values["NULLCLAW_SEARCH_BASE_URL"] = str(runtime.settings["search_base_url"])
    env_path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")


def _read_runtime_bootstrap(runtime: Runtime) -> dict[str, str]:
    path = Path(runtime.runtime_env_file)
    if not path.exists():
        return {}
    return _env_dict(str(path))


def _sync_runtime_bootstrap(runtime: Runtime, *, api_url: str | None = None, service_token: str | None = None) -> None:
    bootstrap = _read_runtime_bootstrap(runtime)
    resolved_api_url = api_url or _host_api_url(bootstrap.get("INFISICAL_API_URL", default_api_url()))
    resolved_service_token = service_token or bootstrap.get("INFISICAL_TOKEN")
    if not resolved_service_token:
        resolved_service_token = create_service_token(
            resolved_api_url,
            runtime.infisical_project_id,
            runtime.runtime_id,
            runtime.infisical_env,
            runtime.infisical_path,
        )
    _write_runtime_env(runtime, resolved_service_token, resolved_api_url)


def _apply_runtime_bootstrap(runtime: Runtime, *, recreate: bool = False, actor: Any = None) -> Runtime:
    _sync_runtime_bootstrap(runtime)
    if recreate:
        return recreate_runtime(runtime.runtime_id, actor=actor)
    return runtime


def _reload_litellm_stack() -> None:
    compose_file = ROOT_DIR / "litellm-stack" / "docker-compose.yml"
    run(["docker", "compose", "-f", str(compose_file), "up", "-d", "litellm"], cwd=str(ROOT_DIR))


def _monitoring_enabled() -> bool:
    return MONITORING_STACK_ENV_FILE.exists()


def _litellm_env_values() -> dict[str, str]:
    if not LITELLM_STACK_ENV_FILE.exists():
        return {}
    return _env_dict(str(LITELLM_STACK_ENV_FILE))


def _apply_litellm_limits(runtime: Runtime, *, api_url: str | None = None, litellm_base_url: str | None = None) -> dict[str, Any]:
    host_api_url = api_url or default_api_url()
    base_url = litellm_base_url or default_litellm_base_url()
    current_key = _current_runtime_key(host_api_url, runtime)
    if not current_key:
        raise LiteLLMError(f"No LiteLLM key secret found for runtime {runtime.runtime_id}.")
    response = update_virtual_key(
        base_url,
        master_key_from_infisical(host_api_url),
        key=current_key,
        budget_usd=runtime.litellm_budget_usd,
        rpm_limit=runtime.litellm_rpm_limit,
        tpm_limit=runtime.litellm_tpm_limit,
        model_aliases=[runtime.model],
        metadata={
            "runtime_id": runtime.runtime_id,
            "runtime_role": runtime.runtime_profile.slug if runtime.runtime_profile else RuntimeProfileSlug.CUSTOM,
            "tenant_id": runtime.tenant.slug if runtime.tenant else None,
            "plan_id": runtime.plan.slug if runtime.plan else None,
            "managed_by": "aquarium-controlplane",
        },
    )
    runtime.last_action_at = timezone.now()
    runtime.save(update_fields=["last_action_at", "updated_at"])
    return response


def ensure_platform_provider_records() -> tuple[ProviderConnection | None, ProviderModel | None]:
    ensure_controlplane_ready()
    env_values = _litellm_env_values()
    project_id = env_values.get("INFISICAL_PROJECT_ID")
    if not project_id:
        return None, None

    connection, _ = ProviderConnection.objects.update_or_create(
        name="platform-openrouter",
        defaults={
            "display_name": "Platform OpenRouter",
            "provider_kind": ProviderKind.OPENROUTER,
            "scope": ConnectionScope.PLATFORM,
            "status": ConnectionStatus.CONFIGURED,
            "api_key_secret_name": "OPENROUTER_API_KEY",
            "api_base_secret_name": "",
        },
    )
    ensure_runtime_secret_ref(
        name="platform-openrouter-provider-api-key",
        secret_kind=SecretKind.PROVIDER_API_KEY,
        provider_connection=connection,
        infisical_project_id=project_id,
        secret_name="OPENROUTER_API_KEY",
        masked_label="Configured",
    )
    model, _ = ProviderModel.objects.update_or_create(
        alias=DEFAULT_MODEL_ALIAS,
        defaults={
            "display_name": "Platform Default Model",
            "provider_connection": connection,
            "provider_model": DEFAULT_PROVIDER_MODEL,
            "is_custom": False,
            "is_platform_default": True,
            "is_enabled": True,
        },
    )
    Runtime.objects.filter(model=DEFAULT_MODEL_ALIAS, default_provider_connection__isnull=True).update(default_provider_connection=connection)
    Runtime.objects.filter(model=DEFAULT_MODEL_ALIAS, default_provider_model__isnull=True).update(default_provider_model=model)
    return connection, model


def ensure_runtime_secret_ref(
    *,
    name: str,
    secret_kind: str,
    runtime: Runtime | None = None,
    provider_connection: ProviderConnection | None = None,
    integration_connection: IntegrationConnection | None = None,
    tenant: Tenant | None = None,
    infisical_project_id: str,
    secret_name: str,
    masked_label: str = "",
) -> RuntimeSecretRef:
    ref, _ = RuntimeSecretRef.objects.update_or_create(
        name=name,
        defaults={
            "secret_kind": secret_kind,
            "runtime": runtime,
            "provider_connection": provider_connection,
            "integration_connection": integration_connection,
            "tenant": tenant,
            "infisical_project_id": infisical_project_id,
            "secret_name": secret_name,
            "masked_label": masked_label,
        },
    )
    return ref


def _ensure_integration_connection(
    runtime: Runtime,
    integration_type: str,
    *,
    tenant: Tenant | None = None,
    config: dict[str, Any] | None = None,
    status: str = ConnectionStatus.CONFIGURED,
) -> IntegrationConnection:
    return IntegrationConnection.objects.update_or_create(
        name=f"{runtime.runtime_id}-{integration_type}",
        defaults={
            "display_name": f"{runtime.runtime_id} {integration_type.title()}",
            "integration_type": integration_type,
            "scope": ConnectionScope.RUNTIME,
            "tenant": tenant or runtime.tenant,
            "runtime": runtime,
            "status": status,
            "config": config or {},
        },
    )[0]


def ensure_runtime_related_records(runtime: Runtime) -> None:
    tenant = runtime.tenant
    ensure_runtime_secret_ref(
        name=f"{runtime.runtime_id}-litellm-api-key",
        secret_kind=SecretKind.PROVIDER_API_KEY,
        runtime=runtime,
        tenant=tenant,
        infisical_project_id=runtime.infisical_project_id,
        secret_name="LITELLM_API_KEY",
        masked_label="Managed by Aquarium",
    )
    if runtime.telegram_enabled or runtime.desired_channels.get("telegram"):
        telegram_conn = _ensure_integration_connection(
            runtime,
            "telegram",
            tenant=tenant,
            config={"enabled": True},
            status=ConnectionStatus.CONFIGURED,
        )
        ensure_runtime_secret_ref(
            name=f"{runtime.runtime_id}-telegram-bot-token",
            secret_kind=SecretKind.TELEGRAM_BOT_TOKEN,
            runtime=runtime,
            integration_connection=telegram_conn,
            tenant=tenant,
            infisical_project_id=runtime.infisical_project_id,
            secret_name="TELEGRAM_BOT_TOKEN",
            masked_label="Configured",
        )
        ensure_runtime_secret_ref(
            name=f"{runtime.runtime_id}-telegram-allow-from",
            secret_kind=SecretKind.TELEGRAM_ALLOW_FROM,
            runtime=runtime,
            integration_connection=telegram_conn,
            tenant=tenant,
            infisical_project_id=runtime.infisical_project_id,
            secret_name="TELEGRAM_ALLOW_FROM",
            masked_label="Configured",
        )
    for integration_type, channel_name in INTEGRATION_RUNTIME_CHANNELS.items():
        is_enabled = bool(runtime.desired_channels.get(channel_name)) if channel_name else bool(runtime.settings.get("search_provider"))
        if is_enabled and integration_type != "telegram":
            status = ConnectionStatus.CONFIGURED
            config: dict[str, Any] = {}
            if integration_type == "search":
                config = {
                    "provider": runtime.settings.get("search_provider", ""),
                    "base_url": runtime.settings.get("search_base_url", ""),
                }
            _ensure_integration_connection(runtime, integration_type, tenant=tenant, config=config, status=status)
    RuntimeDiagnosticSnapshot.objects.get_or_create(runtime=runtime)
    if not runtime.action_logs.exists():
        log_runtime_action(action="imported", runtime=runtime, status=ConnectionStatus.CONFIGURED, message="Imported into Django control plane.")


def backfill_runtime_related_records(runtime_id: str | None = None) -> int:
    ensure_controlplane_ready()
    ensure_platform_provider_records()
    query = Runtime.objects.select_related("tenant", "runtime_profile")
    if runtime_id:
        query = query.filter(runtime_id=runtime_id)
    count = 0
    for runtime in query:
        ensure_runtime_related_records(runtime)
        count += 1
    return count


def log_runtime_action(
    *,
    action: str,
    runtime: Runtime | None,
    status: str,
    message: str = "",
    payload: dict[str, Any] | None = None,
    actor: Any = None,
) -> RuntimeActionLog:
    return RuntimeActionLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        runtime=runtime,
        action=action,
        status=status,
        message=message,
        payload=payload or {},
    )


@transaction.atomic
def create_or_update_runtime(request: RuntimeCreateRequest, *, actor: Any = None) -> Runtime:
    ensure_controlplane_ready()
    import_json_state_if_empty()
    token = operator_token(request.api_url)
    project = ensure_project(request.api_url, token, request.runtime_id)
    existing_runtime = Runtime.objects.filter(runtime_id=request.runtime_id).select_related("default_provider_connection", "default_provider_model").first()
    tenant = None
    plan = None
    if request.tenant_slug:
        tenant = Tenant.objects.get_or_create(slug=request.tenant_slug, defaults={"name": request.tenant_slug.replace("-", " ").title()})[0]
    if request.plan_slug:
        plan = Plan.objects.get_or_create(slug=request.plan_slug, defaults={"display_name": request.plan_slug.replace("-", " ").title()})[0]
    default_role, default_rpm, default_tpm = _role_defaults(request.runtime_id)
    resolved_role = request.runtime_role or default_role
    profile = RuntimeProfile.objects.get(slug=resolved_role)
    resolved_budget = request.budget_usd if request.budget_usd is not None else _budget_for_role(resolved_role)
    resolved_rpm = request.rpm_limit if request.rpm_limit is not None else default_rpm
    resolved_tpm = request.tpm_limit if request.tpm_limit is not None else default_tpm
    default_provider_connection = (
        ProviderConnection.objects.filter(pk=request.default_provider_connection_id).first()
        if request.default_provider_connection_id
        else existing_runtime.default_provider_connection if existing_runtime else None
    )
    default_provider_model = (
        ProviderModel.objects.filter(pk=request.default_provider_model_id).first()
        if request.default_provider_model_id
        else existing_runtime.default_provider_model if existing_runtime else None
    )
    resolved_channels = request.desired_channels or (existing_runtime.desired_channels.copy() if existing_runtime else {"telegram": request.telegram_enabled})
    if "telegram" not in resolved_channels:
        resolved_channels["telegram"] = request.telegram_enabled
    resolved_settings = request.settings or (existing_runtime.settings.copy() if existing_runtime else {})
    resolved_model = request.model or (default_provider_model.alias if default_provider_model else DEFAULT_MODEL_ALIAS)
    pricing = get_price_info()
    runtime, _ = Runtime.objects.update_or_create(
        runtime_id=request.runtime_id,
        defaults={
            "enabled": True,
            "tenant": tenant,
            "plan": plan,
            "runtime_profile": profile,
            "gateway_port": request.gateway_port,
            "model": resolved_model,
            "telegram_enabled": bool(resolved_channels.get("telegram")),
            "desired_channels": resolved_channels,
            "settings": resolved_settings,
            "default_provider_connection": default_provider_connection,
            "default_provider_model": default_provider_model,
            "infisical_project_slug": project["slug"],
            "infisical_project_id": project["id"],
            "infisical_env": "prod",
            "infisical_path": "/runtime",
            "litellm_key_name": f"runtime-{request.runtime_id}",
            "litellm_budget_usd": resolved_budget,
            "litellm_rpm_limit": resolved_rpm,
            "litellm_tpm_limit": resolved_tpm,
            "litellm_model_alias": resolved_model,
            "litellm_price_input_per_million_usd": pricing.input_per_million_usd,
            "litellm_price_output_per_million_usd": pricing.output_per_million_usd,
            "runtime_env_file": str(runtime_env_file(request.runtime_id)),
            "runtime_home": str(runtime_home(request.runtime_id)),
            "workspace_dir": str(workspace_dir(request.runtime_id)),
            "generated_config_path": str(runtime_home(request.runtime_id) / "config.json"),
        },
    )
    if resolved_channels.get("telegram") and request.telegram_bot_token:
        telegram_conn, _ = IntegrationConnection.objects.update_or_create(
            name=f"{runtime.runtime_id}-telegram",
            defaults={
                "display_name": f"{runtime.runtime_id} Telegram",
                "integration_type": "telegram",
                "scope": ConnectionScope.RUNTIME,
                "tenant": tenant,
                "runtime": runtime,
                "status": ConnectionStatus.CONFIGURED,
                "config": {"enabled": True},
            },
        )
        upsert_secret(request.api_url, token, runtime.infisical_project_id, "prod", "/runtime", "TELEGRAM_BOT_TOKEN", request.telegram_bot_token)
        ensure_runtime_secret_ref(
            name=f"{runtime.runtime_id}-telegram-bot-token",
            secret_kind=SecretKind.TELEGRAM_BOT_TOKEN,
            runtime=runtime,
            integration_connection=telegram_conn,
            tenant=tenant,
            infisical_project_id=runtime.infisical_project_id,
            secret_name="TELEGRAM_BOT_TOKEN",
            masked_label="Configured",
        )
    if resolved_channels.get("telegram") and request.telegram_allow_from:
        telegram_conn, _ = IntegrationConnection.objects.update_or_create(
            name=f"{runtime.runtime_id}-telegram",
            defaults={
                "display_name": f"{runtime.runtime_id} Telegram",
                "integration_type": "telegram",
                "scope": ConnectionScope.RUNTIME,
                "tenant": tenant,
                "runtime": runtime,
                "status": ConnectionStatus.CONFIGURED,
                "config": {"enabled": True},
            },
        )
        upsert_secret(request.api_url, token, runtime.infisical_project_id, "prod", "/runtime", "TELEGRAM_ALLOW_FROM", request.telegram_allow_from)
        ensure_runtime_secret_ref(
            name=f"{runtime.runtime_id}-telegram-allow-from",
            secret_kind=SecretKind.TELEGRAM_ALLOW_FROM,
            runtime=runtime,
            integration_connection=telegram_conn,
            tenant=tenant,
            infisical_project_id=runtime.infisical_project_id,
            secret_name="TELEGRAM_ALLOW_FROM",
            masked_label=request.telegram_allow_from,
        )
    current_key = _current_runtime_key(request.api_url, runtime)
    if current_key:
        try:
            delete_virtual_key(request.litellm_base_url, master_key_from_infisical(request.api_url), key=current_key)
        except LiteLLMError:
            pass
    provisioned = _provision_litellm_key(runtime, api_url=request.api_url, litellm_base_url=request.litellm_base_url)
    upsert_secret(request.api_url, token, runtime.infisical_project_id, "prod", "/runtime", "LITELLM_API_KEY", provisioned["key"])
    ensure_runtime_secret_ref(
        name=f"{runtime.runtime_id}-litellm-api-key",
        secret_kind=SecretKind.PROVIDER_API_KEY,
        runtime=runtime,
        tenant=tenant,
        infisical_project_id=runtime.infisical_project_id,
        secret_name="LITELLM_API_KEY",
        masked_label="Configured",
    )
    service_token = create_service_token(request.api_url, runtime.infisical_project_id, runtime.runtime_id, runtime.infisical_env, runtime.infisical_path)
    _write_runtime_env(runtime, service_token, request.api_url)
    ensure_runtime_related_records(runtime)
    sync_compose_from_db()
    mirror_json_state()
    _up_runtime(runtime.runtime_id)
    runtime.lifecycle_status = RuntimeLifecycleStatus.RUNNING
    runtime.last_action_at = timezone.now()
    runtime.save(update_fields=["lifecycle_status", "last_action_at", "updated_at"])
    log_runtime_action(action="create_or_update", runtime=runtime, status=ConnectionStatus.VERIFIED, actor=actor)
    return runtime


def list_runtimes() -> list[Runtime]:
    ensure_controlplane_ready()
    import_json_state_if_empty()
    return list(Runtime.objects.select_related("tenant", "plan", "runtime_profile").all())


def list_runtime_lines() -> list[str]:
    lines: list[str] = []
    for runtime in list_runtimes():
        lines.append(
            f"{runtime.runtime_id} port={runtime.gateway_port} role={runtime.runtime_profile.slug if runtime.runtime_profile else RuntimeProfileSlug.CUSTOM} "
            f"telegram={'on' if runtime.telegram_enabled else 'off'} project={runtime.infisical_project_slug}"
        )
    return lines


def get_runtime(runtime_id: str) -> Runtime:
    ensure_controlplane_ready()
    import_json_state_if_empty()
    return Runtime.objects.select_related("tenant", "plan", "runtime_profile").get(runtime_id=runtime_id)


def start_runtime(runtime_id: str, *, actor: Any = None) -> Runtime:
    runtime = get_runtime(runtime_id)
    sync_compose_from_db()
    _up_runtime(runtime_id)
    runtime.lifecycle_status = RuntimeLifecycleStatus.RUNNING
    runtime.last_action_at = timezone.now()
    runtime.save(update_fields=["lifecycle_status", "last_action_at", "updated_at"])
    log_runtime_action(action="start", runtime=runtime, status=ConnectionStatus.VERIFIED, actor=actor)
    return runtime


def stop_runtime(runtime_id: str, *, actor: Any = None) -> Runtime:
    runtime = get_runtime(runtime_id)
    sync_compose_from_db()
    run(_compose_cmd("stop", f"gateway-{runtime_id}", f"agent-{runtime_id}"))
    runtime.lifecycle_status = RuntimeLifecycleStatus.STOPPED
    runtime.last_action_at = timezone.now()
    runtime.save(update_fields=["lifecycle_status", "last_action_at", "updated_at"])
    log_runtime_action(action="stop", runtime=runtime, status=ConnectionStatus.VERIFIED, actor=actor)
    return runtime


def restart_runtime(runtime_id: str, *, actor: Any = None) -> Runtime:
    stop_runtime(runtime_id, actor=actor)
    return start_runtime(runtime_id, actor=actor)


def recreate_runtime(runtime_id: str, *, actor: Any = None) -> Runtime:
    runtime = get_runtime(runtime_id)
    sync_compose_from_db()
    _up_runtime(runtime_id)
    runtime.lifecycle_status = RuntimeLifecycleStatus.RUNNING
    runtime.last_action_at = timezone.now()
    runtime.save(update_fields=["lifecycle_status", "last_action_at", "updated_at"])
    log_runtime_action(action="recreate", runtime=runtime, status=ConnectionStatus.VERIFIED, actor=actor)
    return runtime


def delete_runtime_service(runtime_id: str, *, keep_files: bool = False, actor: Any = None) -> None:
    runtime = get_runtime(runtime_id)
    sync_compose_from_db()
    try:
        run(_compose_cmd("stop", f"gateway-{runtime_id}", f"agent-{runtime_id}"))
    except CommandError:
        pass
    try:
        run(_compose_cmd("rm", "-f", "-s", f"gateway-{runtime_id}", f"agent-{runtime_id}"))
    except CommandError:
        pass
    runtime.delete()
    mirror_json_state()
    sync_compose_from_db()
    if not keep_files:
        import shutil

        shutil.rmtree(runtime_dir(runtime_id), ignore_errors=True)
    log_runtime_action(action="delete", runtime=None, status=ConnectionStatus.VERIFIED, actor=actor, payload={"runtime_id": runtime_id})


def read_runtime_limits(runtime_id: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    return {
        "runtime_id": runtime.runtime_id,
        "runtime_role": runtime.runtime_profile.slug if runtime.runtime_profile else RuntimeProfileSlug.CUSTOM,
        "budget_usd": runtime.litellm_budget_usd,
        "rpm_limit": runtime.litellm_rpm_limit,
        "tpm_limit": runtime.litellm_tpm_limit,
        "model": runtime.model,
        "price_input_per_million_usd": runtime.litellm_price_input_per_million_usd,
        "price_output_per_million_usd": runtime.litellm_price_output_per_million_usd,
    }


def update_runtime_limits(
    runtime_id: str,
    *,
    budget_usd: float | None = None,
    rpm_limit: int | None = None,
    tpm_limit: int | None = None,
    model: str | None = None,
    actor: Any = None,
) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    model_changed = False
    if budget_usd is not None:
        runtime.litellm_budget_usd = budget_usd
    if rpm_limit is not None:
        runtime.litellm_rpm_limit = rpm_limit
    if tpm_limit is not None:
        runtime.litellm_tpm_limit = tpm_limit
    if model and model != runtime.model:
        model_changed = True
        runtime.model = model
        runtime.litellm_model_alias = model
        default_provider_connection, default_provider_model = _selected_provider_defaults(model)
        runtime.default_provider_connection = default_provider_connection
        runtime.default_provider_model = default_provider_model
    runtime.last_action_at = timezone.now()
    runtime.save()
    mirror_json_state()
    _apply_litellm_limits(runtime)
    if model_changed:
        _apply_runtime_bootstrap(runtime, recreate=True, actor=actor)
    log_runtime_action(action="update_limits", runtime=runtime, status=ConnectionStatus.VERIFIED, actor=actor)
    return read_runtime_limits(runtime_id)


def sync_runtime_limits(runtime_id: str, *, api_url: str | None = None, litellm_base_url: str | None = None, actor: Any = None) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    response = _apply_litellm_limits(runtime, api_url=api_url, litellm_base_url=litellm_base_url)
    log_runtime_action(action="sync_limits", runtime=runtime, status=ConnectionStatus.VERIFIED, actor=actor)
    return response


def rotate_runtime_key(runtime_id: str, *, api_url: str | None = None, litellm_base_url: str | None = None, actor: Any = None) -> Runtime:
    runtime = get_runtime(runtime_id)
    request = RuntimeCreateRequest(
        runtime_id=runtime.runtime_id,
        gateway_port=runtime.gateway_port,
        model=runtime.model,
        telegram_enabled=runtime.telegram_enabled,
        runtime_role=runtime.runtime_profile.slug if runtime.runtime_profile else None,
        budget_usd=runtime.litellm_budget_usd,
        rpm_limit=runtime.litellm_rpm_limit,
        tpm_limit=runtime.litellm_tpm_limit,
        tenant_slug=runtime.tenant.slug if runtime.tenant else None,
        plan_slug=runtime.plan.slug if runtime.plan else None,
        api_url=api_url or default_api_url(),
        litellm_base_url=litellm_base_url or default_litellm_base_url(),
    )
    rotated = create_or_update_runtime(request, actor=actor)
    log_runtime_action(action="rotate_key", runtime=rotated, status=ConnectionStatus.VERIFIED, actor=actor)
    return rotated


def revoke_runtime_key(runtime_id: str, *, api_url: str | None = None, litellm_base_url: str | None = None, actor: Any = None) -> None:
    runtime = get_runtime(runtime_id)
    host_api_url = api_url or default_api_url()
    base_url = litellm_base_url or default_litellm_base_url()
    current_key = _current_runtime_key(host_api_url, runtime)
    if not current_key:
        raise LiteLLMError(f"No LiteLLM key secret found for runtime {runtime_id}.")
    delete_virtual_key(base_url, master_key_from_infisical(host_api_url), key=current_key)
    delete_secret(host_api_url, operator_token(host_api_url), runtime.infisical_project_id, runtime.infisical_env, runtime.infisical_path, "LITELLM_API_KEY")
    runtime.last_action_at = timezone.now()
    runtime.save(update_fields=["last_action_at", "updated_at"])
    log_runtime_action(action="revoke_key", runtime=runtime, status=ConnectionStatus.VERIFIED, actor=actor)


def inspect_runtime_key(runtime_id: str, *, api_url: str | None = None, litellm_base_url: str | None = None) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    host_api_url = api_url or default_api_url()
    base_url = litellm_base_url or default_litellm_base_url()
    current_key = _current_runtime_key(host_api_url, runtime)
    if not current_key:
        raise LiteLLMError(f"No LiteLLM key secret found for runtime {runtime_id}.")
    payload = info_for_virtual_key(base_url, master_key_from_infisical(host_api_url), key=current_key)
    return {key: value for key, value in payload.items() if key not in {"key", "token", "virtual_key"}}


def smoke_test_runtime(runtime_id: str, *, actor: Any = None) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    command = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "run",
        "--rm",
        f"agent-{runtime.runtime_id}",
        "agent",
        "-m",
        "Reply with MONITORING-OK only",
    ]
    output = run(command)
    log_runtime_action(action="smoke_test", runtime=runtime, status=ConnectionStatus.VERIFIED, actor=actor, payload={"output": output})
    return {"runtime_id": runtime.runtime_id, "output": output.strip()}


def _runtime_health_payload(runtime: Runtime) -> dict[str, Any]:
    snapshot = RuntimeDiagnosticSnapshot.objects.filter(runtime=runtime).first()
    health = snapshot.summary.get("health") if snapshot and isinstance(snapshot.summary, dict) else None
    gateway_health = health.get("gateway_health") if isinstance(health, dict) else None
    return {
        "runtime_id": runtime.runtime_id,
        "gateway_port": runtime.gateway_port,
        "health_status": runtime.health_status,
        "lifecycle_status": runtime.lifecycle_status,
        "gateway_health": gateway_health if isinstance(gateway_health, dict) else {},
        "last_healthcheck_at": runtime.last_healthcheck_at.isoformat() if runtime.last_healthcheck_at else None,
        "last_error": runtime.last_error,
    }


def _probe_runtime_health(runtime: Runtime) -> dict[str, Any]:
    payload = _runtime_health_payload(runtime)
    payload["gateway_health"] = {}
    try:
        compose_ps = run(_compose_cmd("ps", f"gateway-{runtime.runtime_id}", "--format", "json"))
        payload["compose"] = json.loads(compose_ps) if compose_ps else []
    except (CommandError, json.JSONDecodeError):
        payload["compose"] = []
    try:
        response = requests.get(f"http://127.0.0.1:{runtime.gateway_port}/health", timeout=10)
        payload["gateway_health"] = {"status_code": response.status_code, "body": response.text.strip()}
        runtime.health_status = RuntimeHealthStatus.HEALTHY if response.status_code == 200 else RuntimeHealthStatus.DEGRADED
        runtime.last_error = ""
    except requests.RequestException as exc:
        payload["gateway_health"] = {"error": str(exc)}
        runtime.health_status = RuntimeHealthStatus.UNHEALTHY
        runtime.last_error = str(exc)
    runtime.last_healthcheck_at = timezone.now()
    runtime.save(update_fields=["health_status", "last_healthcheck_at", "last_error", "updated_at"])
    payload["health_status"] = runtime.health_status
    payload["last_healthcheck_at"] = runtime.last_healthcheck_at.isoformat() if runtime.last_healthcheck_at else None
    payload["last_error"] = runtime.last_error
    return payload


def refresh_runtime_diagnostics(runtime_id: str) -> RuntimeDiagnosticSnapshot:
    runtime = get_runtime(runtime_id)
    summary = {
        "health": _probe_runtime_health(runtime),
        "config": runtime_config_view(runtime_id),
    }
    snapshot, _ = RuntimeDiagnosticSnapshot.objects.get_or_create(runtime=runtime)
    snapshot.summary = summary
    snapshot.logs = runtime_logs_view(runtime_id)
    snapshot.traces = runtime_traces_view(runtime_id)
    snapshot.metrics = runtime_metrics_view(runtime_id)
    snapshot.save()
    return snapshot


def runtime_health_summary(runtime_id: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    return _runtime_health_payload(runtime)


def runtime_status_payload(runtime_id: str, *, api_url: str | None = None) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    payload = {
        "id": runtime.runtime_id,
        "runtime_role": runtime.runtime_profile.slug if runtime.runtime_profile else RuntimeProfileSlug.CUSTOM,
        "budget_usd": runtime.litellm_budget_usd,
        "rpm_limit": runtime.litellm_rpm_limit,
        "tpm_limit": runtime.litellm_tpm_limit,
        "model": runtime.model,
        "tenant": runtime.tenant.slug if runtime.tenant else None,
        "plan": runtime.plan.slug if runtime.plan else None,
        "generated_config_path": runtime.generated_config_path,
        "litellm_runtime_base_url": runtime_base_url(),
        "has_runtime_key": _current_runtime_key(api_url or default_api_url(), runtime) is not None,
        "health": runtime_health_summary(runtime_id),
        "config": runtime_config_view(runtime_id),
    }
    return payload


def _monitoring_env() -> dict[str, str]:
    return read_env_file(Path("monitoring-stack/.env"))


def public_surface_payload() -> dict[str, str]:
    return {
        "app_url": os.environ.get("CONTROLPLANE_PUBLIC_URL", "https://app.aquarium.local"),
        "grafana_url": os.environ.get("GRAFANA_PUBLIC_URL", "https://grafana.aquarium.local"),
        "secrets_url": os.environ.get("SECRETS_PUBLIC_URL", "https://secrets.aquarium.local"),
        "auth_url": os.environ.get("AUTHELIA_PUBLIC_URL", "https://auth.aquarium.local"),
    }


def monitoring_surface_payload() -> dict[str, Any]:
    surfaces = public_surface_payload()
    env = _monitoring_env()
    probe_url = os.environ.get("GRAFANA_INTERNAL_URL") or env.get("GRAFANA_INTERNAL_URL")
    if not probe_url:
        grafana_port = env.get("GRAFANA_PORT", "13000")
        probe_url = f"http://127.0.0.1:{grafana_port}"
    if not env:
        return {
            "url": surfaces["grafana_url"],
            "probe_url": probe_url,
            "available": False,
            "healthy": False,
            "label": "Grafana offline",
            "reason": "Monitoring stack is not bootstrapped.",
        }
    try:
        response = requests.get(f"{probe_url}/api/health", timeout=2)
        response.raise_for_status()
        return {
            "url": surfaces["grafana_url"],
            "probe_url": probe_url,
            "available": True,
            "healthy": True,
            "label": "Open Grafana",
            "reason": "",
        }
    except requests.RequestException as exc:
        return {
            "url": surfaces["grafana_url"],
            "probe_url": probe_url,
            "available": False,
            "healthy": False,
            "label": "Grafana offline",
            "reason": str(exc),
        }


def _mask_sensitive_payload(value: Any, key_name: str | None = None) -> Any:
    sensitive_tokens = ("token", "password", "secret", "api_key")
    if isinstance(value, dict):
        masked: dict[str, Any] = {}
        for key, item in value.items():
            lowered = key.lower()
            if any(token in lowered for token in sensitive_tokens):
                masked[key] = "***"
            else:
                masked[key] = _mask_sensitive_payload(item, key)
        return masked
    if isinstance(value, list):
        return [_mask_sensitive_payload(item, key_name) for item in value]
    if isinstance(value, str) and key_name and any(token in key_name.lower() for token in sensitive_tokens):
        return "***"
    return value


def runtime_logs_view(runtime_id: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    env = _monitoring_env()
    loki_port = env.get("LOKI_PORT", "13100")
    query = f'{{compose_project="aquarium-nullclaw-runtimes",compose_service="gateway-{runtime.runtime_id}"}}'
    try:
        response = requests.get(
            f"http://127.0.0.1:{loki_port}/loki/api/v1/query_range",
            params={"query": query, "limit": 50},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        return {"error": str(exc), "query": query}


def runtime_traces_view(runtime_id: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    env = _monitoring_env()
    tempo_port = env.get("TEMPO_PORT", "13200")
    query = quote(f'{{resource.service.name="nullclaw-{runtime.runtime_id}"}} with (most_recent=true)')
    try:
        response = requests.get(f"http://127.0.0.1:{tempo_port}/api/search?query={query}", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        return {"error": str(exc)}


def runtime_metrics_view(runtime_id: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    env = _monitoring_env()
    mimir_port = env.get("MIMIR_PORT", "13300")
    query = quote(f'probe_success{{service="nullclaw-{runtime.runtime_id}"}}')
    try:
        response = requests.get(f"http://127.0.0.1:{mimir_port}/prometheus/api/v1/query?query={query}", timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        return {"error": str(exc)}


def runtime_config_view(runtime_id: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    path = Path(runtime.generated_config_path)
    if not path.exists():
        return {"exists": False, "path": str(path)}
    try:
        return {"exists": True, "path": str(path), "config": _mask_sensitive_payload(json.loads(path.read_text()))}
    except json.JSONDecodeError as exc:
        return {"exists": True, "path": str(path), "error": str(exc)}


def _loki_snippets(payload: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for stream in payload.get("data", {}).get("result", []):
        labels = stream.get("stream", {})
        for entry in stream.get("values", [])[-5:]:
            timestamp, line = entry
            items.append({"timestamp": timestamp, "line": line.strip(), "service": labels.get("compose_service", "")})
    return items[-5:]


def _tempo_snippets(payload: dict[str, Any]) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    candidates = payload.get("traces") or payload.get("data") or payload.get("results") or []
    if isinstance(candidates, dict):
        candidates = candidates.get("traces", [])
    for item in candidates[:5]:
        if isinstance(item, dict):
            snippets.append(
                {
                    "trace_id": item.get("traceID") or item.get("traceId"),
                    "root_service": item.get("rootServiceName"),
                    "root_name": item.get("rootTraceName"),
                    "start_time": item.get("startTimeUnixNano"),
                }
            )
    return snippets


def _mimir_summary(payload: dict[str, Any]) -> dict[str, Any]:
    results = payload.get("data", {}).get("result", [])
    if not results:
        return {"status": "unknown", "value": None}
    first = results[0]
    value = first.get("value", [None, None])[1]
    return {"status": "ok" if value == "1" else "error", "value": value, "metric": first.get("metric", {})}


def _diagnostics_links(runtime: Runtime) -> dict[str, str]:
    surfaces = public_surface_payload()
    env = _monitoring_env()
    loki_port = env.get("LOKI_PORT", "13100")
    tempo_port = env.get("TEMPO_PORT", "13200")
    mimir_port = env.get("MIMIR_PORT", "13300")
    logs_query = quote(f'{{compose_project="aquarium-nullclaw-runtimes",compose_service="gateway-{runtime.runtime_id}"}}')
    trace_query = quote(f'{{resource.service.name="nullclaw-{runtime.runtime_id}"}} with (most_recent=true)')
    metric_query = quote(f'probe_success{{service="nullclaw-{runtime.runtime_id}"}}')
    return {
        "grafana": surfaces["grafana_url"],
        "loki": f"http://127.0.0.1:{loki_port}/loki/api/v1/query_range?query={logs_query}&limit=50",
        "tempo": f"http://127.0.0.1:{tempo_port}/api/search?query={trace_query}",
        "mimir": f"http://127.0.0.1:{mimir_port}/prometheus/api/v1/query?query={metric_query}",
    }


def runtime_diagnostics_summary(runtime_id: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    snapshot = RuntimeDiagnosticSnapshot.objects.filter(runtime=runtime).first()
    summary = snapshot.summary if snapshot and isinstance(snapshot.summary, dict) else {}
    normalized_health = summary.get("health")
    if not isinstance(normalized_health, dict):
        normalized_health = _runtime_health_payload(runtime)
    config_summary = summary.get("config")
    config = config_summary if isinstance(config_summary, dict) else runtime_config_view(runtime_id)
    secret_results = [
        {
            "name": secret.name,
            "status": "ok" if not secret.last_error else "error",
            "error": secret.last_error,
            "last_verified_at": secret.last_verified_at.isoformat() if secret.last_verified_at else None,
        }
        for secret in runtime.secret_refs.all()
    ]
    latest_failure = runtime.action_logs.filter(status=ConnectionStatus.ERROR).first()
    return {
        "runtime_id": runtime.runtime_id,
        "health": normalized_health,
        "config": {
            "exists": config.get("exists", False),
            "path": config.get("path"),
            "valid": config.get("exists", False) and "error" not in config,
            "error": config.get("error"),
        },
        "secrets": {
            "checked": len(secret_results),
            "failed": [item for item in secret_results if item["status"] != "ok"],
        },
        "logs": {
            "error": snapshot.logs.get("error") if snapshot else "",
            "snippets": _loki_snippets(snapshot.logs) if snapshot else [],
        },
        "traces": {
            "error": snapshot.traces.get("error") if snapshot else "",
            "items": _tempo_snippets(snapshot.traces) if snapshot else [],
        },
        "metrics": {
            "error": snapshot.metrics.get("error") if snapshot else "",
            "summary": _mimir_summary(snapshot.metrics) if snapshot else {"status": "unknown", "value": None},
        },
        "provider_error": runtime.default_provider_connection.last_error if runtime.default_provider_connection else "",
        "last_failure": {
            "action": latest_failure.action if latest_failure else "",
            "message": latest_failure.message if latest_failure else "",
        },
        "links": _diagnostics_links(runtime),
        "raw": {
            "logs": snapshot.logs if snapshot else {},
            "traces": snapshot.traces if snapshot else {},
            "metrics": snapshot.metrics if snapshot else {},
        },
    }


def runtime_secret_check(runtime_id: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    env = _env_dict(runtime.runtime_env_file)
    api_url = _host_api_url(env["INFISICAL_API_URL"])
    token = env["INFISICAL_TOKEN"]
    results: list[dict[str, Any]] = []
    for secret in runtime.secret_refs.all():
        try:
            read_secret_with_token(api_url, token, secret.infisical_project_id, secret.infisical_env, secret.infisical_path, secret.secret_name)
            secret.last_error = ""
            secret.last_verified_at = timezone.now()
            secret.save(update_fields=["last_error", "last_verified_at", "updated_at"])
            results.append({"name": secret.name, "status": "ok"})
        except InfisicalError as exc:
            secret.last_error = str(exc)
            secret.save(update_fields=["last_error", "updated_at"])
            results.append({"name": secret.name, "status": "error", "error": str(exc)})
    return {"runtime_id": runtime.runtime_id, "results": results}


def _read_secret_with_operator(ref: RuntimeSecretRef) -> str:
    api_url = default_api_url()
    return read_secret_with_token(
        api_url,
        operator_token(api_url),
        ref.infisical_project_id,
        ref.infisical_env,
        ref.infisical_path,
        ref.secret_name,
    )


def runtime_secret_payload(runtime_id: str) -> list[dict[str, Any]]:
    runtime = get_runtime(runtime_id)
    items: list[dict[str, Any]] = []
    for ref in runtime.secret_refs.select_related("integration_connection", "provider_connection").all():
        items.append(
            {
                "id": ref.pk,
                "name": ref.name,
                "secret_kind": ref.secret_kind,
                "secret_name": ref.secret_name,
                "masked_label": ref.masked_label or "Configured",
                "last_verified_at": ref.last_verified_at.isoformat() if ref.last_verified_at else None,
                "last_error": ref.last_error,
                "integration_connection": ref.integration_connection.name if ref.integration_connection else None,
                "provider_connection": ref.provider_connection.name if ref.provider_connection else None,
                "managed_by_system": ref.secret_name == "LITELLM_API_KEY",
            }
        )
    return items


def _runtime_secret_ref_for_kind(runtime: Runtime, secret_kind: str) -> RuntimeSecretRef:
    ensure_runtime_related_records(runtime)
    try:
        return runtime.secret_refs.get(secret_kind=secret_kind)
    except RuntimeSecretRef.DoesNotExist as exc:
        raise InfisicalError(f"No runtime secret ref for kind {secret_kind} on {runtime.runtime_id}.") from exc


def upsert_runtime_secret(runtime_id: str, secret_kind: str, secret_value: str, *, actor: Any = None) -> RuntimeSecretRef:
    runtime = get_runtime(runtime_id)
    definition = RUNTIME_SECRET_DEFINITIONS.get(secret_kind)
    if definition is None:
        raise InfisicalError(f"Unsupported runtime secret kind: {secret_kind}")
    if not secret_value:
        raise InfisicalError("Secret value is required.")
    token = operator_token(default_api_url())
    integration_connection = None
    integration_type = definition.get("integration_type")
    if integration_type:
        integration_connection = _ensure_integration_connection(runtime, integration_type, tenant=runtime.tenant, config={"enabled": True})
        if integration_type in INTEGRATION_RUNTIME_CHANNELS and INTEGRATION_RUNTIME_CHANNELS[integration_type]:
            runtime.desired_channels[INTEGRATION_RUNTIME_CHANNELS[integration_type]] = True
        if integration_type == "search" and not runtime.settings.get("search_provider"):
            runtime.settings["search_provider"] = "custom"
        if integration_type == "telegram":
            runtime.telegram_enabled = True
        runtime.save(update_fields=["desired_channels", "settings", "telegram_enabled", "updated_at"])
    upsert_secret(
        default_api_url(),
        token,
        runtime.infisical_project_id,
        runtime.infisical_env,
        runtime.infisical_path,
        definition["secret_name"],
        secret_value,
    )
    ref = ensure_runtime_secret_ref(
        name=f"{runtime.runtime_id}-{secret_kind.replace('_', '-')}",
        secret_kind=secret_kind,
        runtime=runtime,
        integration_connection=integration_connection,
        tenant=runtime.tenant,
        infisical_project_id=runtime.infisical_project_id,
        secret_name=definition["secret_name"],
        masked_label=definition["masked_label"],
    )
    ref.last_error = ""
    ref.save(update_fields=["last_error", "updated_at"])
    _apply_runtime_bootstrap(runtime, recreate=True, actor=actor)
    log_runtime_action(action="runtime_secret_upsert", runtime=runtime, status=ConnectionStatus.VERIFIED, actor=actor, payload={"secret_kind": secret_kind})
    return ref


def test_runtime_secret(runtime_id: str, secret_ref_id: int) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    ref = runtime.secret_refs.get(pk=secret_ref_id)
    try:
        _read_secret_with_operator(ref)
        ref.last_verified_at = timezone.now()
        ref.last_error = ""
        ref.save(update_fields=["last_verified_at", "last_error", "updated_at"])
        return {"status": "ok", "secret_ref_id": ref.pk, "secret_kind": ref.secret_kind}
    except InfisicalError as exc:
        ref.last_error = str(exc)
        ref.save(update_fields=["last_error", "updated_at"])
        return {"status": "error", "secret_ref_id": ref.pk, "error": str(exc)}


def list_integration_connections() -> list[IntegrationConnection]:
    ensure_controlplane_ready()
    return list(IntegrationConnection.objects.select_related("tenant", "runtime").all())


def upsert_integration_connection(
    *,
    integration_type: str,
    runtime_id: str | None = None,
    tenant_slug: str | None = None,
    display_name: str | None = None,
    enabled: bool = True,
    config: dict[str, Any] | None = None,
    actor: Any = None,
) -> IntegrationConnection:
    ensure_controlplane_ready()
    runtime = get_runtime(runtime_id) if runtime_id else None
    tenant = runtime.tenant if runtime else None
    if tenant_slug:
        tenant, _ = Tenant.objects.get_or_create(slug=tenant_slug, defaults={"name": tenant_slug.replace("-", " ").title()})
    base_name = runtime.runtime_id if runtime else tenant.slug if tenant else integration_type
    conn = IntegrationConnection.objects.update_or_create(
        name=f"{base_name}-{integration_type}",
        defaults={
            "display_name": display_name or f"{base_name} {integration_type.title()}",
            "integration_type": integration_type,
            "scope": ConnectionScope.RUNTIME if runtime else ConnectionScope.TENANT,
            "tenant": tenant,
            "runtime": runtime,
            "status": ConnectionStatus.CONFIGURED if enabled else ConnectionStatus.DISABLED,
            "config": config or {},
        },
    )[0]
    if runtime:
        if integration_type in INTEGRATION_RUNTIME_CHANNELS and INTEGRATION_RUNTIME_CHANNELS[integration_type]:
            runtime.desired_channels[INTEGRATION_RUNTIME_CHANNELS[integration_type]] = enabled
        if integration_type == "telegram":
            runtime.telegram_enabled = enabled
            allow_from = (config or {}).get("allow_from", "").strip()
            if enabled and allow_from:
                token = operator_token(default_api_url())
                upsert_secret(
                    default_api_url(),
                    token,
                    runtime.infisical_project_id,
                    runtime.infisical_env,
                    runtime.infisical_path,
                    "TELEGRAM_ALLOW_FROM",
                    allow_from,
                )
                ensure_runtime_secret_ref(
                    name=f"{runtime.runtime_id}-telegram-allow-from",
                    secret_kind=SecretKind.TELEGRAM_ALLOW_FROM,
                    runtime=runtime,
                    integration_connection=conn,
                    tenant=runtime.tenant,
                    infisical_project_id=runtime.infisical_project_id,
                    secret_name="TELEGRAM_ALLOW_FROM",
                    masked_label=allow_from,
                )
        if integration_type == "search":
            if enabled:
                runtime.settings["search_provider"] = (config or {}).get("provider", runtime.settings.get("search_provider", "custom"))
                if (config or {}).get("base_url"):
                    runtime.settings["search_base_url"] = config["base_url"]
                else:
                    runtime.settings.pop("search_base_url", None)
            else:
                runtime.settings.pop("search_provider", None)
                runtime.settings.pop("search_base_url", None)
        runtime.save(update_fields=["desired_channels", "telegram_enabled", "settings", "updated_at"])
        _apply_runtime_bootstrap(runtime, recreate=True, actor=actor)
    log_runtime_action(action="integration_connection_upsert", runtime=runtime, status=ConnectionStatus.VERIFIED, actor=actor, payload={"integration_type": integration_type})
    return conn


def delete_integration_connection_service(connection_id: int, *, actor: Any = None) -> None:
    conn = IntegrationConnection.objects.select_related("runtime").get(pk=connection_id)
    runtime = conn.runtime
    integration_type = conn.integration_type
    if runtime and integration_type in INTEGRATION_RUNTIME_CHANNELS and INTEGRATION_RUNTIME_CHANNELS[integration_type]:
        runtime.desired_channels[INTEGRATION_RUNTIME_CHANNELS[integration_type]] = False
        if integration_type == "telegram":
            runtime.telegram_enabled = False
        runtime.save(update_fields=["desired_channels", "telegram_enabled", "updated_at"])
        _apply_runtime_bootstrap(runtime, recreate=True, actor=actor)
    elif runtime and integration_type == "search":
        runtime.settings.pop("search_provider", None)
        runtime.settings.pop("search_base_url", None)
        runtime.save(update_fields=["settings", "updated_at"])
        _apply_runtime_bootstrap(runtime, recreate=True, actor=actor)
    conn.delete()
    log_runtime_action(action="integration_connection_delete", runtime=runtime, status=ConnectionStatus.VERIFIED, actor=actor, payload={"connection_id": connection_id})


def test_integration_connection(connection_id: int) -> dict[str, Any]:
    conn = IntegrationConnection.objects.select_related("runtime").get(pk=connection_id)
    missing: list[str] = []
    if conn.integration_type == "telegram":
        required_kinds = {SecretKind.TELEGRAM_BOT_TOKEN}
        existing_kinds = set(conn.secret_refs.values_list("secret_kind", flat=True))
        missing = sorted(required_kinds - existing_kinds)
    if missing:
        conn.status = ConnectionStatus.ERROR
        conn.last_error = f"Missing secrets: {', '.join(missing)}"
        conn.save(update_fields=["status", "last_error", "updated_at"])
        return {"status": "error", "missing": missing}
    conn.status = ConnectionStatus.VERIFIED
    conn.last_verified_at = timezone.now()
    conn.last_error = ""
    conn.save(update_fields=["status", "last_verified_at", "last_error", "updated_at"])
    return {"status": "ok", "integration_type": conn.integration_type, "connection_id": conn.pk}


def integration_connections_payload() -> list[dict[str, Any]]:
    return [
        {
            "id": conn.pk,
            "name": conn.name,
            "display_name": conn.display_name,
            "integration_type": conn.integration_type,
            "scope": conn.scope,
            "runtime": conn.runtime.runtime_id if conn.runtime else None,
            "tenant": conn.tenant.slug if conn.tenant else None,
            "status": conn.status,
            "config": conn.config,
            "last_verified_at": conn.last_verified_at.isoformat() if conn.last_verified_at else None,
            "last_error": conn.last_error,
            "secret_count": conn.secret_refs.count(),
        }
        for conn in list_integration_connections()
    ]


def runtime_detail_payload(runtime_id: str) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    diagnostics = runtime_diagnostics_summary(runtime_id)
    key_info: dict[str, Any]
    try:
        key_info = inspect_runtime_key(runtime_id)
    except LiteLLMError as exc:
        key_info = {"error": str(exc)}
    overview = {
        "runtime_id": runtime.runtime_id,
        "runtime_profile": runtime.runtime_profile.slug if runtime.runtime_profile else RuntimeProfileSlug.CUSTOM,
        "tenant": runtime.tenant.slug if runtime.tenant else None,
        "plan": runtime.plan.slug if runtime.plan else None,
        "gateway_port": runtime.gateway_port,
        "model": runtime.model,
        "lifecycle_status": runtime.lifecycle_status,
        "health_status": runtime.health_status,
        "last_action_at": runtime.last_action_at,
        "last_healthcheck_at": runtime.last_healthcheck_at,
        "last_error": runtime.last_error,
    }
    return {
        "runtime": overview,
        "overview": overview,
        "limits": read_runtime_limits(runtime_id),
        "key": key_info,
        "channels": runtime.desired_channels,
        "settings": runtime.settings,
        "default_provider_connection": runtime.default_provider_connection,
        "default_provider_model": runtime.default_provider_model,
        "secrets": runtime_secret_payload(runtime_id),
        "integrations": [
            item
            for item in integration_connections_payload()
            if item["runtime"] == runtime.runtime_id or item["tenant"] == (runtime.tenant.slug if runtime.tenant else None)
        ],
        "diagnostics": diagnostics,
        "recent_actions": [
            {
                "id": action.pk,
                "action": action.action,
                "status": action.status,
                "message": action.message,
                "created_at": action.created_at.isoformat(),
            }
            for action in runtime.action_logs.all()[:10]
        ],
        "recent_sessions": [
            {
                "id": session.pk,
                "title": session.title,
                "updated_at": session.updated_at.isoformat(),
            }
            for session in runtime.chat_sessions.all()[:5]
        ],
    }


def runtime_inventory_payload(runtime: Runtime) -> dict[str, Any]:
    overview = {
        "runtime_id": runtime.runtime_id,
        "runtime_profile": runtime.runtime_profile.slug if runtime.runtime_profile else RuntimeProfileSlug.CUSTOM,
        "tenant": runtime.tenant.slug if runtime.tenant else None,
        "plan": runtime.plan.slug if runtime.plan else None,
        "gateway_port": runtime.gateway_port,
        "model": runtime.model,
        "lifecycle_status": runtime.lifecycle_status,
        "health_status": runtime.health_status,
        "last_action_at": runtime.last_action_at,
        "last_healthcheck_at": runtime.last_healthcheck_at,
        "last_error": runtime.last_error,
    }
    return {"runtime": overview, "overview": overview}


def runtime_probe_check(runtime_id: str, target: str) -> dict[str, Any]:
    probe = get_runtime(runtime_id)
    target_runtime = get_runtime(target)
    probe_env = _env_dict(probe.runtime_env_file)
    target_env = _env_dict(target_runtime.runtime_env_file)
    own_probe = read_secret_with_token(
        _host_api_url(probe_env["INFISICAL_API_URL"]),
        probe_env["INFISICAL_TOKEN"],
        probe.infisical_project_id,
        probe.infisical_env,
        probe.infisical_path,
        "LITELLM_API_KEY",
    )
    own_target = read_secret_with_token(
        _host_api_url(target_env["INFISICAL_API_URL"]),
        target_env["INFISICAL_TOKEN"],
        target_runtime.infisical_project_id,
        target_runtime.infisical_env,
        target_runtime.infisical_path,
        "LITELLM_API_KEY",
    )
    if own_probe == own_target:
        raise InfisicalError("Probe and target have the same LITELLM_API_KEY value, so isolation proof is ambiguous.")
    try:
        cross_from_probe = read_secret_with_token(
            _host_api_url(probe_env["INFISICAL_API_URL"]),
            probe_env["INFISICAL_TOKEN"],
            target_runtime.infisical_project_id,
            target_runtime.infisical_env,
            target_runtime.infisical_path,
            "LITELLM_API_KEY",
        )
    except InfisicalError:
        cross_from_probe = None
    try:
        cross_from_target = read_secret_with_token(
            _host_api_url(target_env["INFISICAL_API_URL"]),
            target_env["INFISICAL_TOKEN"],
            probe.infisical_project_id,
            probe.infisical_env,
            probe.infisical_path,
            "LITELLM_API_KEY",
        )
    except InfisicalError:
        cross_from_target = None
    probe_isolated = cross_from_probe is None or (cross_from_probe == own_probe and cross_from_probe != own_target)
    target_isolated = cross_from_target is None or (cross_from_target == own_target and cross_from_target != own_probe)
    return {
        "probe": runtime_id,
        "target": target,
        "probe_isolated": probe_isolated,
        "target_isolated": target_isolated,
        "passed": probe_isolated and target_isolated,
    }


def provider_connections_catalog() -> list[dict[str, str]]:
    return PROVIDER_CATALOG


def provider_connection_secret_payload() -> list[dict[str, Any]]:
    return [
        {
            "connection_id": ref.provider_connection_id,
            "provider_connection": ref.provider_connection.name if ref.provider_connection else None,
            "name": ref.name,
            "secret_kind": ref.secret_kind,
            "secret_name": ref.secret_name,
            "masked_label": ref.masked_label,
            "last_verified_at": ref.last_verified_at.isoformat() if ref.last_verified_at else None,
            "last_error": ref.last_error,
        }
        for ref in RuntimeSecretRef.objects.select_related("provider_connection").filter(provider_connection__isnull=False)
    ]


def integration_secrets_payload() -> list[dict[str, Any]]:
    return [
        {
            "integration_connection": ref.integration_connection.name if ref.integration_connection else None,
            "runtime": ref.runtime.runtime_id if ref.runtime else None,
            "name": ref.name,
            "secret_kind": ref.secret_kind,
            "secret_name": ref.secret_name,
            "masked_label": ref.masked_label,
            "last_verified_at": ref.last_verified_at.isoformat() if ref.last_verified_at else None,
            "last_error": ref.last_error,
        }
        for ref in RuntimeSecretRef.objects.select_related("integration_connection", "runtime").filter(integration_connection__isnull=False)
    ]


def list_provider_connections() -> list[ProviderConnection]:
    ensure_controlplane_ready()
    return list(ProviderConnection.objects.select_related("tenant").all())


@transaction.atomic
def upsert_provider_connection(
    *,
    name: str,
    display_name: str,
    provider_kind: str,
    scope: str = ConnectionScope.PLATFORM,
    tenant_slug: str | None = None,
    base_url: str = "",
    api_key: str = "",
    actor: Any = None,
) -> ProviderConnection:
    ensure_controlplane_ready()
    tenant = None
    if tenant_slug:
        tenant, _ = Tenant.objects.get_or_create(slug=tenant_slug, defaults={"name": tenant_slug.replace("-", " ").title()})
    conn, _ = ProviderConnection.objects.update_or_create(
        name=name,
        defaults={
            "display_name": display_name,
            "provider_kind": provider_kind,
            "scope": scope,
            "tenant": tenant,
            "base_url": base_url,
            "status": ConnectionStatus.CONFIGURED,
            "api_key_secret_name": f"PROVIDER_{name.upper().replace('-', '_')}_API_KEY",
            "api_base_secret_name": f"PROVIDER_{name.upper().replace('-', '_')}_API_BASE" if base_url else "",
        },
    )
    api_url = default_api_url()
    token = operator_token(api_url)
    litellm_project = ensure_project(api_url, token, "litellm-core")
    if api_key:
        upsert_secret(api_url, token, litellm_project["id"], "prod", "/runtime", conn.api_key_secret_name, api_key)
        ensure_runtime_secret_ref(
            name=f"{conn.name}-provider-api-key",
            secret_kind=SecretKind.PROVIDER_API_KEY,
            provider_connection=conn,
            tenant=tenant,
            infisical_project_id=litellm_project["id"],
            secret_name=conn.api_key_secret_name,
            masked_label="Configured",
        )
    if base_url and conn.api_base_secret_name:
        upsert_secret(api_url, token, litellm_project["id"], "prod", "/runtime", conn.api_base_secret_name, base_url)
        ensure_runtime_secret_ref(
            name=f"{conn.name}-provider-api-base",
            secret_kind=SecretKind.PROVIDER_API_BASE,
            provider_connection=conn,
            tenant=tenant,
            infisical_project_id=litellm_project["id"],
            secret_name=conn.api_base_secret_name,
            masked_label=base_url,
        )
    regenerate_litellm_config()
    _reload_litellm_stack()
    log_runtime_action(action="provider_connection_upsert", runtime=None, status=ConnectionStatus.VERIFIED, actor=actor, payload={"connection": conn.name})
    return conn


def delete_provider_connection_service(connection_id: int, *, actor: Any = None) -> None:
    conn = ProviderConnection.objects.get(pk=connection_id)
    conn.delete()
    regenerate_litellm_config()
    _reload_litellm_stack()
    log_runtime_action(action="provider_connection_delete", runtime=None, status=ConnectionStatus.VERIFIED, actor=actor, payload={"connection_id": connection_id})


def test_provider_connection(connection_id: int) -> dict[str, Any]:
    conn = ProviderConnection.objects.get(pk=connection_id)
    if conn.provider_kind == ProviderKind.OPENAI_COMPATIBLE and conn.base_url:
        try:
            response = requests.get(f"{conn.base_url.rstrip('/')}/models", timeout=10)
            if response.status_code == 404:
                response = requests.get(f"{conn.base_url.rstrip('/')}/v1/models", timeout=10)
            response.raise_for_status()
            conn.status = ConnectionStatus.VERIFIED
            conn.last_error = ""
            conn.last_verified_at = timezone.now()
            conn.save(update_fields=["status", "last_error", "last_verified_at", "updated_at"])
            return {"status": "ok", "models": response.json()}
        except requests.RequestException as exc:
            conn.status = ConnectionStatus.ERROR
            conn.last_error = str(exc)
            conn.save(update_fields=["status", "last_error", "updated_at"])
            return {"status": "error", "error": str(exc)}
    conn.status = ConnectionStatus.VERIFIED
    conn.last_verified_at = timezone.now()
    conn.save(update_fields=["status", "last_verified_at", "updated_at"])
    return {"status": "ok", "provider_kind": conn.provider_kind}


def models_catalog() -> list[ProviderModel]:
    ensure_controlplane_ready()
    return list(ProviderModel.objects.select_related("provider_connection", "tenant").all())


def upsert_provider_model(
    *,
    alias: str,
    display_name: str,
    provider_model: str,
    provider_connection_id: int | None = None,
    tenant_slug: str | None = None,
    is_custom: bool = False,
    is_platform_default: bool = False,
) -> ProviderModel:
    ensure_controlplane_ready()
    tenant = None
    connection = None
    if tenant_slug:
        tenant, _ = Tenant.objects.get_or_create(slug=tenant_slug, defaults={"name": tenant_slug.replace("-", " ").title()})
    if provider_connection_id is not None:
        connection = ProviderConnection.objects.get(pk=provider_connection_id)
    model, _ = ProviderModel.objects.update_or_create(
        alias=alias,
        defaults={
            "display_name": display_name,
            "provider_model": provider_model,
            "provider_connection": connection,
            "tenant": tenant,
            "is_custom": is_custom,
            "is_platform_default": is_platform_default,
            "is_enabled": True,
        },
    )
    regenerate_litellm_config()
    _reload_litellm_stack()
    return model


def set_provider_model_enabled(model_id: int, enabled: bool) -> ProviderModel:
    model = ProviderModel.objects.get(pk=model_id)
    model.is_enabled = enabled
    model.save(update_fields=["is_enabled", "updated_at"])
    regenerate_litellm_config()
    _reload_litellm_stack()
    return model


def delete_provider_model_service(model_id: int) -> None:
    model = ProviderModel.objects.get(pk=model_id)
    model.delete()
    regenerate_litellm_config()
    _reload_litellm_stack()


def regenerate_litellm_config() -> Path:
    api_url = default_api_url()
    token = operator_token(api_url)
    project = ensure_project(api_url, token, "litellm-core")
    env_values = litellm_stack_env_defaults()
    if LITELLM_STACK_ENV_FILE.exists():
        env_values.update(_env_dict(str(LITELLM_STACK_ENV_FILE)))
    env_values.update(
        {
            "INFISICAL_API_URL": containerized_api_url(api_url),
            "INFISICAL_PROJECT_ID": project["id"],
            "INFISICAL_ENV": "prod",
            "INFISICAL_PATH": "/runtime",
        }
    )
    write_stack_env(env_values)
    extra_models: list[dict[str, Any]] = []
    pricing = get_price_info()
    for model in ProviderModel.objects.select_related("provider_connection").filter(is_enabled=True):
        connection = model.provider_connection
        if connection is None:
            continue
        params: dict[str, Any] = {"model": model.provider_model}
        if connection.api_key_secret_name:
            params["api_key"] = f"os.environ/{connection.api_key_secret_name}"
        if connection.api_base_secret_name:
            params["api_base"] = f"os.environ/{connection.api_base_secret_name}"
        extra_models.append(
            {
                "model_name": model.alias,
                "litellm_params": params,
                "model_info": {
                    "input_cost_per_token": pricing.input_per_million_usd / 1_000_000,
                    "output_cost_per_token": pricing.output_per_million_usd / 1_000_000,
                },
            }
        )
    return write_stack_config(
        price=PriceInfo(pricing.model, pricing.input_per_million_usd, pricing.output_per_million_usd, pricing.source_url),
        extra_models=extra_models,
    )


def create_chat_session(runtime_id: str, *, actor: Any = None, title: str = "") -> RuntimeChatSession:
    runtime = get_runtime(runtime_id)
    return RuntimeChatSession.objects.create(runtime=runtime, actor=actor if getattr(actor, "pk", None) else None, title=title or f"{runtime_id} session")


def list_chat_sessions(runtime_id: str) -> list[RuntimeChatSession]:
    runtime = get_runtime(runtime_id)
    return list(runtime.chat_sessions.all())


def send_chat_message(runtime_id: str, session_id: int, message: str, *, actor: Any = None) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    session = RuntimeChatSession.objects.get(pk=session_id, runtime=runtime)
    RuntimeChatMessage.objects.create(session=session, role=ChatRole.USER, content=message)
    command = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "run",
        "--rm",
        f"agent-{runtime.runtime_id}",
        "agent",
        "-m",
        message,
    ]
    output = run(command)
    RuntimeChatMessage.objects.create(
        session=session,
        role=ChatRole.ASSISTANT,
        content=output.strip(),
        metadata={"model": runtime.model, "elapsed_mode": "buffered"},
    )
    session.updated_at = timezone.now()
    session.save(update_fields=["updated_at"])
    return {"session_id": session.pk, "response": output.strip(), "model": runtime.model}


def reset_chat_session(runtime_id: str, session_id: int) -> dict[str, Any]:
    runtime = get_runtime(runtime_id)
    session = RuntimeChatSession.objects.get(pk=session_id, runtime=runtime)
    session.messages.all().delete()
    return {"session_id": session.pk, "status": "reset"}
