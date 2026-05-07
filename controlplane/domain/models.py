from __future__ import annotations

from django.conf import settings
from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"


class WorkspaceStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"


class PlanStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    DISABLED = "disabled", "Disabled"


class RuntimeProfileSlug(models.TextChoices):
    LIVE = "live", "Live"
    PROBE = "probe", "Probe"
    LIMIT_PROBE = "limit-probe", "Limit Probe"
    PLAYGROUND = "playground", "Playground"
    CUSTOM = "custom", "Custom"


class RuntimeLifecycleStatus(models.TextChoices):
    CREATED = "created", "Created"
    RUNNING = "running", "Running"
    STOPPED = "stopped", "Stopped"
    ERROR = "error", "Error"
    UNKNOWN = "unknown", "Unknown"


class RuntimeHealthStatus(models.TextChoices):
    HEALTHY = "healthy", "Healthy"
    DEGRADED = "degraded", "Degraded"
    UNHEALTHY = "unhealthy", "Unhealthy"
    UNKNOWN = "unknown", "Unknown"


class ConnectionScope(models.TextChoices):
    PLATFORM = "platform", "Platform"
    TENANT = "tenant", "Tenant"
    RUNTIME = "runtime", "Runtime"


class ProviderKind(models.TextChoices):
    OPENROUTER = "openrouter", "OpenRouter"
    OPENAI = "openai", "OpenAI"
    OPENAI_COMPATIBLE = "openai-compatible", "OpenAI Compatible"
    ANTHROPIC = "anthropic", "Anthropic"
    GEMINI = "gemini", "Gemini"
    CUSTOM = "custom", "Custom"


class ConnectionStatus(models.TextChoices):
    CONFIGURED = "configured", "Configured"
    VERIFIED = "verified", "Verified"
    ERROR = "error", "Error"
    PENDING = "pending", "Pending"
    DISABLED = "disabled", "Disabled"


class IntegrationType(models.TextChoices):
    TELEGRAM = "telegram", "Telegram"
    SLACK = "slack", "Slack"
    MATTERMOST = "mattermost", "Mattermost"
    GITEA = "gitea", "Gitea"
    KANBOARD = "kanboard", "Kanboard"
    SEARCH = "search", "Search"
    OPENWEBUI = "openwebui", "OpenWebUI"


class SecretKind(models.TextChoices):
    PROVIDER_API_KEY = "provider_api_key", "Provider API Key"
    PROVIDER_API_BASE = "provider_api_base", "Provider API Base"
    TELEGRAM_BOT_TOKEN = "telegram_bot_token", "Telegram Bot Token"
    TELEGRAM_ALLOW_FROM = "telegram_allow_from", "Telegram Allow From"
    SLACK_BOT_TOKEN = "slack_bot_token", "Slack Bot Token"
    SLACK_APP_TOKEN = "slack_app_token", "Slack App Token"
    SLACK_SIGNING_SECRET = "slack_signing_secret", "Slack Signing Secret"
    MATTERMOST_BOT_TOKEN = "mattermost_bot_token", "Mattermost Bot Token"
    GITEA_TOKEN = "gitea_token", "Gitea Token"
    KANBOARD_PASSWORD = "kanboard_password", "Kanboard Password"
    SEARCH_API_KEY = "search_api_key", "Search API Key"


class ChatRole(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"
    SYSTEM = "system", "System"


class AgentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    READY = "ready", "Ready"
    LAUNCHING = "launching", "Launching"
    RUNNING = "running", "Running"
    STOPPED = "stopped", "Stopped"
    DEGRADED = "degraded", "Degraded"
    ERROR = "error", "Error"


class DeploymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    LAUNCHING = "launching", "Launching"
    RUNNING = "running", "Running"
    STOPPED = "stopped", "Stopped"
    FAILED = "failed", "Failed"


class PrimaryChannel(models.TextChoices):
    TELEGRAM = "telegram", "Telegram"
    INTERNAL = "internal", "Internal"


class SkillType(models.TextChoices):
    BEHAVIOR = "behavior", "Behavior"
    HYBRID = "hybrid", "Hybrid"
    EXECUTABLE = "executable", "Executable"


class SkillSource(models.TextChoices):
    INTERNAL = "internal", "Internal"
    NULLCLAW_REGISTRY = "nullclaw-registry", "NullClaw Registry"
    GITHUB = "github", "GitHub"


class SkillTrustStatus(models.TextChoices):
    INTERNAL = "internal", "Internal"
    REVIEWED = "reviewed", "Reviewed"
    QUARANTINE = "quarantine", "Quarantine"
    BLOCKED = "blocked", "Blocked"
class Tenant(TimestampedModel):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=TenantStatus.choices, default=TenantStatus.ACTIVE)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.name


class Workspace(TimestampedModel):
    slug = models.SlugField(unique=True)
    display_name = models.CharField(max_length=255)
    authelia_subject = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=32, choices=WorkspaceStatus.choices, default=WorkspaceStatus.ACTIVE)
    infisical_project_slug = models.CharField(max_length=255, default="workspace-default")
    infisical_project_id = models.CharField(max_length=255, blank=True)
    infisical_env = models.CharField(max_length=64, default="prod")
    infisical_path = models.CharField(max_length=255, default="/workspace")

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.display_name


class Plan(TimestampedModel):
    slug = models.SlugField(unique=True)
    display_name = models.CharField(max_length=255)
    status = models.CharField(max_length=32, choices=PlanStatus.choices, default=PlanStatus.ACTIVE)
    policy_defaults = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.display_name


class SkillCatalogEntry(TimestampedModel):
    key = models.SlugField(unique=True)
    display_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=255, blank=True)
    source_path = models.CharField(max_length=1024)
    compatibility_rules = models.JSONField(default=dict, blank=True)
    default_enabled = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=32, choices=PlanStatus.choices, default=PlanStatus.ACTIVE)
    skill_type = models.CharField(max_length=32, choices=SkillType.choices, default=SkillType.BEHAVIOR)
    source = models.CharField(max_length=64, choices=SkillSource.choices, default=SkillSource.INTERNAL)
    trust_status = models.CharField(max_length=32, choices=SkillTrustStatus.choices, default=SkillTrustStatus.INTERNAL)
    source_url = models.URLField(blank=True)
    required_integrations = models.JSONField(default=list, blank=True)
    required_secrets = models.JSONField(default=list, blank=True)
    required_services = models.JSONField(default=list, blank=True)
    permissions = models.JSONField(default=list, blank=True)
    entrypoints = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["category", "display_name", "key"]

    def __str__(self) -> str:
        return self.display_name


class RuntimeProfile(TimestampedModel):
    slug = models.CharField(max_length=32, choices=RuntimeProfileSlug.choices, unique=True)
    display_name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    defaults = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["slug"]

    def __str__(self) -> str:
        return self.display_name


class ProviderConnection(TimestampedModel):
    name = models.SlugField(unique=True)
    display_name = models.CharField(max_length=255)
    scope = models.CharField(max_length=32, choices=ConnectionScope.choices, default=ConnectionScope.PLATFORM)
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="provider_connections")
    provider_kind = models.CharField(max_length=64, choices=ProviderKind.choices)
    status = models.CharField(max_length=32, choices=ConnectionStatus.choices, default=ConnectionStatus.PENDING)
    base_url = models.URLField(blank=True)
    api_key_secret_name = models.CharField(max_length=255, blank=True)
    api_base_secret_name = models.CharField(max_length=255, blank=True)
    extra_config = models.JSONField(default=dict, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.display_name


class ProviderModel(TimestampedModel):
    alias = models.CharField(max_length=255, unique=True)
    display_name = models.CharField(max_length=255)
    provider_connection = models.ForeignKey(
        ProviderConnection,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="models",
    )
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="provider_models")
    provider_model = models.CharField(max_length=255)
    is_platform_default = models.BooleanField(default=False)
    is_custom = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)
    model_info = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["alias"]

    def __str__(self) -> str:
        return self.alias


class Agent(TimestampedModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="agents")
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=AgentStatus.choices, default=AgentStatus.DRAFT)
    primary_channel = models.CharField(max_length=32, choices=PrimaryChannel.choices, default=PrimaryChannel.TELEGRAM)
    current_build_spec = models.ForeignKey(
        "AgentBuildSpec",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    current_deployment = models.ForeignKey(
        "Deployment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    last_launched_at = models.DateTimeField(null=True, blank=True)
    last_interaction_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["slug"]

    @property
    def secret_bindings(self):
        if self.current_build_spec_id is None:
            return AgentSecretBinding.objects.none()
        return self.current_build_spec.secret_bindings.all()

    def __str__(self) -> str:
        return self.name


class AgentBuildSpec(TimestampedModel):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="build_specs")
    personality_prompt = models.TextField(blank=True)
    model_alias = models.CharField(max_length=255, default="openai/qwen/qwen3.6-plus")
    runtime_template = models.CharField(max_length=255, default="generic-runtime")
    gateway_port = models.PositiveIntegerField(default=0)
    environment_profile = models.JSONField(default=dict, blank=True)
    startup_policy = models.JSONField(default=dict, blank=True)
    observability_profile = models.JSONField(default=dict, blank=True)
    autonomy_limits = models.JSONField(default=dict, blank=True)
    safety_limits = models.JSONField(default=dict, blank=True)
    channel_config = models.JSONField(default=dict, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    litellm_budget_usd = models.FloatField(null=True, blank=True)
    litellm_rpm_limit = models.IntegerField(null=True, blank=True)
    litellm_tpm_limit = models.IntegerField(null=True, blank=True)
    build_state = models.CharField(max_length=32, choices=AgentStatus.choices, default=AgentStatus.DRAFT)

    class Meta:
        ordering = ["-updated_at", "-pk"]

    def __str__(self) -> str:
        return f"{self.agent.slug} build"


class Secret(TimestampedModel):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="secrets")
    name = models.SlugField()
    secret_kind = models.CharField(max_length=64, choices=SecretKind.choices)
    backend_ref = models.CharField(max_length=255, blank=True)
    backend_secret_name = models.CharField(max_length=255)
    usage_scope = models.CharField(max_length=64, default="workspace")
    masked_label = models.CharField(max_length=255, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "name"], name="unique_workspace_secret_name"),
        ]

    def __str__(self) -> str:
        return self.name


class Runtime(TimestampedModel):
    runtime_id = models.SlugField(unique=True)
    enabled = models.BooleanField(default=True)
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.SET_NULL, related_name="runtimes")
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.SET_NULL, related_name="runtimes")
    runtime_profile = models.ForeignKey(RuntimeProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="runtimes")
    gateway_port = models.PositiveIntegerField()
    model = models.CharField(max_length=255)
    telegram_enabled = models.BooleanField(default=False)
    desired_channels = models.JSONField(default=dict, blank=True)
    settings = models.JSONField(default=dict, blank=True)
    default_provider_connection = models.ForeignKey(
        ProviderConnection,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="default_runtimes",
    )
    default_provider_model = models.ForeignKey(
        ProviderModel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="default_runtimes",
    )
    infisical_project_slug = models.CharField(max_length=255)
    infisical_project_id = models.CharField(max_length=255)
    infisical_env = models.CharField(max_length=64, default="prod")
    infisical_path = models.CharField(max_length=255, default="/runtime")
    litellm_key_name = models.CharField(max_length=255, blank=True)
    litellm_budget_usd = models.FloatField(null=True, blank=True)
    litellm_rpm_limit = models.IntegerField(null=True, blank=True)
    litellm_tpm_limit = models.IntegerField(null=True, blank=True)
    litellm_model_alias = models.CharField(max_length=255, default="openai/qwen/qwen3.6-plus")
    litellm_price_input_per_million_usd = models.FloatField(null=True, blank=True)
    litellm_price_output_per_million_usd = models.FloatField(null=True, blank=True)
    runtime_env_file = models.CharField(max_length=1024)
    runtime_home = models.CharField(max_length=1024)
    workspace_dir = models.CharField(max_length=1024)
    generated_config_path = models.CharField(max_length=1024)
    lifecycle_status = models.CharField(max_length=32, choices=RuntimeLifecycleStatus.choices, default=RuntimeLifecycleStatus.CREATED)
    health_status = models.CharField(max_length=32, choices=RuntimeHealthStatus.choices, default=RuntimeHealthStatus.UNKNOWN)
    last_healthcheck_at = models.DateTimeField(null=True, blank=True)
    last_action_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["runtime_id"]

    def __str__(self) -> str:
        return self.runtime_id


class AgentSkillBinding(TimestampedModel):
    build_spec = models.ForeignKey(AgentBuildSpec, on_delete=models.CASCADE, related_name="skill_bindings")
    skill = models.ForeignKey(SkillCatalogEntry, on_delete=models.CASCADE, related_name="agent_bindings")
    position = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["build_spec", "skill"], name="unique_skill_per_build_spec"),
            models.UniqueConstraint(fields=["build_spec", "position"], name="unique_skill_position_per_build_spec"),
        ]

    def __str__(self) -> str:
        return f"{self.build_spec.agent.slug}:{self.skill.key}"


class AgentSecretBinding(TimestampedModel):
    build_spec = models.ForeignKey(AgentBuildSpec, on_delete=models.CASCADE, related_name="secret_bindings")
    secret = models.ForeignKey(Secret, on_delete=models.CASCADE, related_name="agent_bindings")
    logical_role = models.CharField(max_length=255)
    required = models.BooleanField(default=True)

    class Meta:
        ordering = ["logical_role"]
        constraints = [
            models.UniqueConstraint(fields=["build_spec", "logical_role"], name="unique_secret_role_per_build_spec"),
        ]

    def __str__(self) -> str:
        return f"{self.build_spec.agent.slug}:{self.logical_role}"


class IntegrationConnection(TimestampedModel):
    name = models.SlugField(unique=True)
    display_name = models.CharField(max_length=255)
    integration_type = models.CharField(max_length=64, choices=IntegrationType.choices)
    scope = models.CharField(max_length=32, choices=ConnectionScope.choices, default=ConnectionScope.RUNTIME)
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="integration_connections")
    runtime = models.ForeignKey(Runtime, null=True, blank=True, on_delete=models.CASCADE, related_name="integration_connections")
    status = models.CharField(max_length=32, choices=ConnectionStatus.choices, default=ConnectionStatus.PENDING)
    config = models.JSONField(default=dict, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.display_name


class Deployment(TimestampedModel):
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="deployments")
    build_spec = models.ForeignKey(AgentBuildSpec, on_delete=models.CASCADE, related_name="deployments")
    runtime = models.ForeignKey(Runtime, null=True, blank=True, on_delete=models.SET_NULL, related_name="deployments")
    status = models.CharField(max_length=32, choices=DeploymentStatus.choices, default=DeploymentStatus.PENDING)
    runtime_ref = models.CharField(max_length=255, blank=True)
    launch_summary = models.JSONField(default=dict, blank=True)
    launched_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return f"{self.agent.slug}:{self.status}"


class RuntimeSecretRef(TimestampedModel):
    name = models.SlugField(unique=True)
    secret_kind = models.CharField(max_length=64, choices=SecretKind.choices)
    tenant = models.ForeignKey(Tenant, null=True, blank=True, on_delete=models.CASCADE, related_name="secret_refs")
    runtime = models.ForeignKey(Runtime, null=True, blank=True, on_delete=models.CASCADE, related_name="secret_refs")
    integration_connection = models.ForeignKey(
        IntegrationConnection,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="secret_refs",
    )
    provider_connection = models.ForeignKey(
        ProviderConnection,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="secret_refs",
    )
    infisical_project_id = models.CharField(max_length=255)
    infisical_env = models.CharField(max_length=64, default="prod")
    infisical_path = models.CharField(max_length=255, default="/runtime")
    secret_name = models.CharField(max_length=255)
    masked_label = models.CharField(max_length=255, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RuntimeActionLog(TimestampedModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    runtime = models.ForeignKey(Runtime, null=True, blank=True, on_delete=models.CASCADE, related_name="action_logs")
    action = models.CharField(max_length=128)
    status = models.CharField(max_length=32, choices=ConnectionStatus.choices, default=ConnectionStatus.PENDING)
    message = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} {self.runtime.runtime_id if self.runtime else 'global'}"


class RuntimeDiagnosticSnapshot(TimestampedModel):
    runtime = models.OneToOneField(Runtime, on_delete=models.CASCADE, related_name="diagnostic_snapshot")
    summary = models.JSONField(default=dict, blank=True)
    logs = models.JSONField(default=dict, blank=True)
    traces = models.JSONField(default=dict, blank=True)
    metrics = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.runtime.runtime_id


class RuntimeChatSession(TimestampedModel):
    runtime = models.ForeignKey(Runtime, on_delete=models.CASCADE, related_name="chat_sessions")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=32, choices=ConnectionStatus.choices, default=ConnectionStatus.CONFIGURED)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or f"Chat {self.pk}"


class RuntimeChatMessage(TimestampedModel):
    session = models.ForeignKey(RuntimeChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=32, choices=ChatRole.choices)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self) -> str:
        return f"{self.role} message"
