from __future__ import annotations

from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html
from unfold.admin import ModelAdmin

from controlplane.domain.models import (
    IntegrationConnection,
    Plan,
    ProviderConnection,
    ProviderModel,
    Runtime,
    RuntimeActionLog,
    RuntimeChatSession,
    RuntimeDiagnosticSnapshot,
    RuntimeProfile,
    RuntimeSecretRef,
    SkillCatalogEntry,
    Tenant,
)


def _service():
    from orchestrator import service_layer

    return service_layer


class HiddenFromMenuAdmin(ModelAdmin):
    def get_model_perms(self, request):
        return {}


@admin.register(Tenant)
class TenantAdmin(HiddenFromMenuAdmin):
    list_display = ["slug", "name", "status", "updated_at"]
    search_fields = ["slug", "name"]


@admin.register(Plan)
class PlanAdmin(HiddenFromMenuAdmin):
    list_display = ["slug", "display_name", "status", "updated_at"]
    search_fields = ["slug", "display_name"]


@admin.register(SkillCatalogEntry)
class SkillCatalogEntryAdmin(HiddenFromMenuAdmin):
    list_display = ["key", "display_name", "category", "skill_type", "source", "trust_status", "status", "default_enabled"]
    list_filter = ["skill_type", "source", "trust_status", "status", "default_enabled", "category"]
    search_fields = ["key", "display_name", "description", "source_path", "source_url"]


@admin.register(RuntimeProfile)
class RuntimeProfileAdmin(HiddenFromMenuAdmin):
    list_display = ["slug", "display_name", "updated_at"]


@admin.action(description="Start selected runtimes")
def action_start(modeladmin: ModelAdmin, request, queryset):
    for runtime in queryset:
        _service().start_runtime(runtime.runtime_id, actor=request.user)
    messages.success(request, f"Started {queryset.count()} runtime(s).")


@admin.action(description="Stop selected runtimes")
def action_stop(modeladmin: ModelAdmin, request, queryset):
    for runtime in queryset:
        _service().stop_runtime(runtime.runtime_id, actor=request.user)
    messages.success(request, f"Stopped {queryset.count()} runtime(s).")


@admin.action(description="Restart selected runtimes")
def action_restart(modeladmin: ModelAdmin, request, queryset):
    for runtime in queryset:
        _service().recreate_runtime(runtime.runtime_id, actor=request.user)
    messages.success(request, f"Restarted {queryset.count()} runtime(s).")


@admin.action(description="Rotate LiteLLM keys")
def action_rotate_keys(modeladmin: ModelAdmin, request, queryset):
    for runtime in queryset:
        _service().rotate_runtime_key(runtime.runtime_id, actor=request.user)
    messages.success(request, f"Rotated keys for {queryset.count()} runtime(s).")


@admin.action(description="Sync LiteLLM limits")
def action_sync_limits(modeladmin: ModelAdmin, request, queryset):
    for runtime in queryset:
        _service().sync_runtime_limits(runtime.runtime_id, actor=request.user)
    messages.success(request, f"Synced limits for {queryset.count()} runtime(s).")


@admin.action(description="Run smoke test")
def action_smoke_test(modeladmin: ModelAdmin, request, queryset):
    for runtime in queryset:
        _service().smoke_test_runtime(runtime.runtime_id, actor=request.user)
    messages.success(request, f"Smoke-tested {queryset.count()} runtime(s).")


@admin.action(description="Refresh diagnostics")
def action_refresh_diagnostics(modeladmin: ModelAdmin, request, queryset):
    for runtime in queryset:
        _service().refresh_runtime_diagnostics(runtime.runtime_id)
    messages.success(request, f"Refreshed diagnostics for {queryset.count()} runtime(s).")


@admin.register(Runtime)
class RuntimeAdmin(HiddenFromMenuAdmin):
    list_display = [
        "runtime_link",
        "runtime_profile",
        "tenant",
        "plan",
        "gateway_port",
        "model",
        "health_status",
        "lifecycle_status",
        "chat_link",
        "diagnostics_link",
    ]
    list_filter = ["runtime_profile", "health_status", "lifecycle_status", "tenant", "plan"]
    search_fields = ["runtime_id", "model", "infisical_project_slug"]
    actions = [action_start, action_stop, action_restart, action_rotate_keys, action_sync_limits, action_smoke_test, action_refresh_diagnostics]

    def runtime_link(self, obj: Runtime) -> str:
        return format_html('<a href="{}">{}</a>', reverse("controlplane-runtime-detail", args=[obj.runtime_id]), obj.runtime_id)

    runtime_link.short_description = "Runtime"

    def chat_link(self, obj: Runtime) -> str:
        return format_html('<a href="{}">Chat</a>', reverse("controlplane-runtime-chat", args=[obj.runtime_id]))

    chat_link.short_description = "Chat"

    def diagnostics_link(self, obj: Runtime) -> str:
        return format_html('<a href="{}">Diagnostics</a>', reverse("controlplane-runtime-diagnostics", args=[obj.runtime_id]))

    diagnostics_link.short_description = "Diagnostics"


@admin.register(ProviderConnection)
class ProviderConnectionAdmin(HiddenFromMenuAdmin):
    list_display = ["name", "display_name", "provider_kind", "scope", "tenant", "status", "last_verified_at"]
    list_filter = ["provider_kind", "scope", "status"]
    search_fields = ["name", "display_name"]


@admin.register(ProviderModel)
class ProviderModelAdmin(HiddenFromMenuAdmin):
    list_display = ["alias", "display_name", "provider_connection", "tenant", "is_custom", "is_platform_default", "is_enabled"]
    list_filter = ["is_custom", "is_platform_default", "is_enabled"]
    search_fields = ["alias", "display_name", "provider_model"]


@admin.register(IntegrationConnection)
class IntegrationConnectionAdmin(HiddenFromMenuAdmin):
    list_display = ["name", "display_name", "integration_type", "scope", "tenant", "runtime", "status"]
    list_filter = ["integration_type", "scope", "status"]
    search_fields = ["name", "display_name"]


@admin.register(RuntimeSecretRef)
class RuntimeSecretRefAdmin(HiddenFromMenuAdmin):
    list_display = ["name", "secret_kind", "tenant", "runtime", "provider_connection", "integration_connection", "masked_label", "last_verified_at"]
    list_filter = ["secret_kind"]
    search_fields = ["name", "secret_name", "masked_label"]


@admin.register(RuntimeDiagnosticSnapshot)
class RuntimeDiagnosticSnapshotAdmin(HiddenFromMenuAdmin):
    list_display = ["runtime", "updated_at"]
    readonly_fields = ["summary", "logs", "traces", "metrics", "updated_at"]


@admin.register(RuntimeActionLog)
class RuntimeActionLogAdmin(HiddenFromMenuAdmin):
    list_display = ["created_at", "action", "runtime", "actor", "status"]
    list_filter = ["action", "status"]
    search_fields = ["action", "message"]
    readonly_fields = ["payload"]


@admin.register(RuntimeChatSession)
class RuntimeChatSessionAdmin(HiddenFromMenuAdmin):
    list_display = ["id", "runtime", "actor", "title", "updated_at"]
    search_fields = ["title", "runtime__runtime_id"]
