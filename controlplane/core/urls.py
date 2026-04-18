from __future__ import annotations

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, re_path

from controlplane.domain import api, views


urlpatterns = [
    path("", lambda request: redirect("/admin/")),
    path("admin/", admin.site.admin_view(views.admin_home_view), name="controlplane-home"),
    path("admin/dashboard/", admin.site.admin_view(views.dashboard_view), name="controlplane-dashboard"),
    path("admin/runtimes/", admin.site.admin_view(views.runtimes_view), name="controlplane-runtimes"),
    path("admin/runtime-wizard/", admin.site.admin_view(views.runtime_wizard_view), name="controlplane-runtime-wizard"),
    path("admin/runtimes/<str:runtime_id>/", admin.site.admin_view(views.runtime_detail_view), name="controlplane-runtime-detail"),
    path(
        "admin/runtimes/<str:runtime_id>/diagnostics/",
        admin.site.admin_view(views.runtime_diagnostics_view),
        name="controlplane-runtime-diagnostics",
    ),
    path(
        "admin/runtimes/<str:runtime_id>/chat/",
        admin.site.admin_view(views.runtime_chat_view),
        name="controlplane-runtime-chat",
    ),
    path("admin/providers/", admin.site.admin_view(views.providers_view), name="controlplane-providers"),
    path("admin/models/", admin.site.admin_view(views.models_view), name="controlplane-models"),
    path("admin/integrations/", admin.site.admin_view(views.integrations_view), name="controlplane-integrations"),
    path("admin/secrets/", admin.site.admin_view(views.secrets_view), name="controlplane-secrets"),
    re_path(r"^admin/domain/runtime(?:/.*)?$", admin.site.admin_view(views.raw_runtime_admin_redirect_view)),
    re_path(r"^admin/domain/providerconnection(?:/.*)?$", admin.site.admin_view(views.raw_provider_admin_redirect_view)),
    re_path(r"^admin/domain/providermodel(?:/.*)?$", admin.site.admin_view(views.raw_model_admin_redirect_view)),
    re_path(r"^admin/domain/integrationconnection(?:/.*)?$", admin.site.admin_view(views.raw_integration_admin_redirect_view)),
    re_path(r"^admin/domain/runtimesecretref(?:/.*)?$", admin.site.admin_view(views.raw_secret_admin_redirect_view)),
    re_path(
        r"^admin/domain/runtimediagnosticsnapshot/(?P<snapshot_id>\d+)/(?:change|delete|history)/$",
        admin.site.admin_view(views.raw_diagnostic_snapshot_redirect_view),
    ),
    re_path(
        r"^admin/domain/runtimechatsession/(?P<session_id>\d+)/(?:change|delete|history)/$",
        admin.site.admin_view(views.raw_chat_session_redirect_view),
    ),
    re_path(r"^admin/domain/runtimediagnosticsnapshot(?:/.*)?$", admin.site.admin_view(views.raw_diagnostic_snapshot_redirect_view)),
    re_path(r"^admin/domain/runtimeactionlog(?:/.*)?$", admin.site.admin_view(views.raw_action_log_admin_redirect_view)),
    re_path(r"^admin/domain/runtimechatsession(?:/.*)?$", admin.site.admin_view(views.raw_chat_session_redirect_view)),
    path("admin/", admin.site.urls),
    path("api/runtimes", api.runtimes_collection, name="api-runtimes"),
    path("api/runtimes/<str:runtime_id>", api.runtime_detail, name="api-runtime-detail"),
    path("api/runtimes/<str:runtime_id>/limits", api.runtime_limits, name="api-runtime-limits"),
    path("api/runtimes/<str:runtime_id>/limits/sync", api.runtime_sync_limits, name="api-runtime-sync-limits"),
    path("api/runtimes/<str:runtime_id>/keys/<str:action>", api.runtime_key_action, name="api-runtime-key-action"),
    path("api/runtimes/<str:runtime_id>/diagnostics/<str:kind>", api.runtime_diagnostics, name="api-runtime-diagnostics"),
    path("api/runtimes/<str:runtime_id>/secrets", api.runtime_secrets, name="api-runtime-secrets"),
    path("api/runtimes/<str:runtime_id>/secrets/<int:secret_ref_id>/test", api.runtime_secret_test, name="api-runtime-secret-test"),
    path("api/runtimes/<str:runtime_id>/chat/sessions", api.runtime_chat_sessions, name="api-runtime-chat-sessions"),
    path(
        "api/runtimes/<str:runtime_id>/chat/sessions/<int:session_id>",
        api.runtime_chat_session_detail,
        name="api-runtime-chat-session-detail",
    ),
    path(
        "api/runtimes/<str:runtime_id>/chat/sessions/<int:session_id>/messages",
        api.runtime_chat_messages,
        name="api-runtime-chat-messages",
    ),
    path(
        "api/runtimes/<str:runtime_id>/chat/sessions/<int:session_id>/reset",
        api.runtime_chat_reset,
        name="api-runtime-chat-reset",
    ),
    path("api/runtimes/<str:runtime_id>/<str:action>", api.runtime_action, name="api-runtime-action"),
    path("api/providers/catalog", api.providers_catalog, name="api-providers-catalog"),
    path("api/provider-connections", api.provider_connections_collection, name="api-provider-connections"),
    path(
        "api/provider-connections/<int:connection_id>",
        api.provider_connection_detail,
        name="api-provider-connection-detail",
    ),
    path(
        "api/provider-connections/<int:connection_id>/test",
        api.provider_connection_test,
        name="api-provider-connection-test",
    ),
    path("api/integrations", api.integrations_collection, name="api-integrations"),
    path("api/integrations/<int:connection_id>", api.integration_detail, name="api-integration-detail"),
    path("api/integrations/<int:connection_id>/test", api.integration_test, name="api-integration-test"),
    path("api/models/catalog", api.models_catalog, name="api-models-catalog"),
    path("api/models/custom", api.custom_models_collection, name="api-custom-models"),
    path("api/models/custom/<int:model_id>", api.custom_model_detail, name="api-custom-model-detail"),
    path("api/runtime-wizard/options", api.runtime_wizard_options, name="api-runtime-wizard-options"),
    path("api/runtime-wizard/validate", api.runtime_wizard_validate, name="api-runtime-wizard-validate"),
    path("api/runtime-wizard/create", api.runtime_wizard_create, name="api-runtime-wizard-create"),
    path("api/secrets/integrations", api.integration_secrets, name="api-secrets-integrations"),
    path("api/secrets/provider-connections", api.provider_connection_secrets, name="api-secrets-provider-connections"),
    path(
        "api/secrets/provider-connections/<int:connection_id>",
        api.provider_connection_secret_detail,
        name="api-provider-connection-secret-detail",
    ),
    path(
        "api/secrets/provider-connections/<int:connection_id>/test",
        api.provider_connection_secret_test,
        name="api-provider-connection-secret-test",
    ),
]
