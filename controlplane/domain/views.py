from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from controlplane.domain.models import (
    IntegrationConnection,
    ProviderConnection,
    ProviderModel,
    Runtime,
    RuntimeActionLog,
    RuntimeChatSession,
    RuntimeDiagnosticSnapshot,
    Tenant,
)

WIZARD_SESSION_KEY = "controlplane_runtime_wizard"


def _service():
    from orchestrator import service_layer

    return service_layer


def _bool_from_post(value: str | None) -> bool:
    return value in {"1", "true", "on", "yes"}


def _float_from_post(value: str | None) -> float | None:
    if not value:
        return None
    return float(value)


def _int_from_post(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


def _selected_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _operator_context(*, title: str, active_page: str, page_description: str, **extra: Any) -> dict[str, Any]:
    monitoring = _service().monitoring_surface_payload()
    context = {
        "title": title,
        "active_page": active_page,
        "page_description": page_description,
        "controlplane_public_url": settings.CONTROLPLANE_PUBLIC_URL,
        "grafana_url": settings.GRAFANA_PUBLIC_URL,
        "secrets_url": settings.SECRETS_PUBLIC_URL,
        "monitoring_direct_url": monitoring["url"],
        "monitoring": monitoring,
    }
    context.update(extra)
    return context


def _runtime_nav(runtime_id: str, active: str) -> list[dict[str, str | bool]]:
    return [
        {"label": "Overview", "href": f"/admin/runtimes/{runtime_id}/", "active": active == "overview"},
        {"label": "Diagnostics", "href": f"/admin/runtimes/{runtime_id}/diagnostics/", "active": active == "diagnostics"},
        {"label": "Chat", "href": f"/admin/runtimes/{runtime_id}/chat/", "active": active == "chat"},
    ]


def _operator_home_context() -> dict[str, Any]:
    runtimes = _service().list_runtimes()
    return _operator_context(
        title="Aquarium Operator Console",
        active_page="home",
        page_description="Единая операторская точка входа для runtime lifecycle, конфигурации, секретов и диагностики.",
        runtimes=runtimes,
        runtime_details=[_service().runtime_inventory_payload(runtime) for runtime in runtimes],
        runtime_count=len(runtimes),
        unhealthy_count=sum(1 for runtime in runtimes if runtime.health_status not in {"healthy", "unknown"}),
        recent_actions=RuntimeActionLog.objects.select_related("runtime").all()[:20],
    )


def _wizard_defaults() -> dict[str, Any]:
    return {
        "runtime_id": "",
        "gateway_port": "3000",
        "tenant": "",
        "plan": "",
        "runtime_role": "live",
        "model": "openai/qwen/qwen3.6-plus",
        "budget_usd": "",
        "rpm_limit": "",
        "tpm_limit": "",
        "provider_connection_id": "",
        "provider_model_id": "",
        "telegram_enabled": False,
        "slack_enabled": False,
        "mattermost_enabled": False,
        "search_enabled": False,
        "http_enabled": False,
        "telegram_bot_token": "",
        "telegram_allow_from": "373793732",
        "search_provider": "",
        "search_base_url": "",
    }


def _wizard_state(request: HttpRequest) -> dict[str, Any]:
    state = _wizard_defaults()
    state.update(request.session.get(WIZARD_SESSION_KEY, {}))
    return state


def _wizard_steps(current_step: int) -> list[dict[str, Any]]:
    labels = ["Identity", "Model", "Channels", "Secrets", "Validation"]
    return [
        {
            "number": index,
            "label": label,
            "status": "current" if index == current_step else "complete" if index < current_step else "upcoming",
        }
        for index, label in enumerate(labels, start=1)
    ]


def _update_wizard_state_from_post(request: HttpRequest, state: dict[str, Any], step: int) -> dict[str, Any]:
    if step == 1:
        state.update(
            {
                "runtime_id": request.POST.get("runtime_id", "").strip(),
                "gateway_port": request.POST.get("gateway_port", "").strip(),
                "tenant": request.POST.get("tenant", "").strip(),
                "plan": request.POST.get("plan", "").strip(),
                "runtime_role": request.POST.get("runtime_role", "live"),
            }
        )
    elif step == 2:
        state.update(
            {
                "model": request.POST.get("model", "").strip(),
                "budget_usd": request.POST.get("budget_usd", "").strip(),
                "rpm_limit": request.POST.get("rpm_limit", "").strip(),
                "tpm_limit": request.POST.get("tpm_limit", "").strip(),
                "provider_connection_id": request.POST.get("provider_connection_id", "").strip(),
                "provider_model_id": request.POST.get("provider_model_id", "").strip(),
            }
        )
    elif step == 3:
        state.update(
            {
                "telegram_enabled": _bool_from_post(request.POST.get("telegram_enabled")),
                "slack_enabled": _bool_from_post(request.POST.get("slack_enabled")),
                "mattermost_enabled": _bool_from_post(request.POST.get("mattermost_enabled")),
                "search_enabled": _bool_from_post(request.POST.get("search_enabled")),
                "http_enabled": _bool_from_post(request.POST.get("http_enabled")),
                "search_provider": request.POST.get("search_provider", "").strip(),
                "search_base_url": request.POST.get("search_base_url", "").strip(),
            }
        )
    elif step == 4:
        if request.POST.get("telegram_bot_token"):
            state["telegram_bot_token"] = request.POST.get("telegram_bot_token", "")
        state["telegram_allow_from"] = request.POST.get("telegram_allow_from", "").strip()
    request.session[WIZARD_SESSION_KEY] = state
    request.session.modified = True
    return state


def _provider_form_state(provider: ProviderConnection | None) -> dict[str, Any]:
    if provider is None:
        return {
            "provider_id": "",
            "name": "",
            "display_name": "",
            "provider_kind": "openrouter",
            "scope": "platform",
            "tenant": "",
            "base_url": "",
            "api_key": "",
        }
    return {
        "provider_id": provider.pk,
        "name": provider.name,
        "display_name": provider.display_name,
        "provider_kind": provider.provider_kind,
        "scope": provider.scope,
        "tenant": provider.tenant.slug if provider.tenant else "",
        "base_url": provider.base_url,
        "api_key": "",
    }


def _model_form_state(model: ProviderModel | None) -> dict[str, Any]:
    if model is None:
        return {
            "model_id": "",
            "alias": "",
            "display_name": "",
            "provider_model": "",
            "provider_connection_id": "",
            "tenant": "",
            "is_platform_default": False,
            "is_custom": True,
        }
    return {
        "model_id": model.pk,
        "alias": model.alias,
        "display_name": model.display_name,
        "provider_model": model.provider_model,
        "provider_connection_id": model.provider_connection_id or "",
        "tenant": model.tenant.slug if model.tenant else "",
        "is_platform_default": model.is_platform_default,
        "is_custom": model.is_custom,
    }


def _integration_form_state(connection: IntegrationConnection | None) -> dict[str, Any]:
    if connection is None:
        return {
            "connection_id": "",
            "integration_type": "telegram",
            "runtime_id": "",
            "tenant": "",
            "display_name": "",
            "enabled": True,
            "allow_from": "",
            "search_provider": "",
            "search_base_url": "",
        }
    return {
        "connection_id": connection.pk,
        "integration_type": connection.integration_type,
        "runtime_id": connection.runtime.runtime_id if connection.runtime else "",
        "tenant": connection.tenant.slug if connection.tenant else "",
        "display_name": connection.display_name,
        "enabled": connection.status != "disabled",
        "allow_from": connection.config.get("allow_from", ""),
        "search_provider": connection.config.get("provider", ""),
        "search_base_url": connection.config.get("base_url", ""),
    }


def admin_home_view(request: HttpRequest) -> HttpResponse:
    return render(request, "admin/operator_home.html", _operator_home_context())


def dashboard_view(request: HttpRequest) -> HttpResponse:
    return redirect("/admin/")


def runtimes_view(request: HttpRequest) -> HttpResponse:
    return redirect("/admin/")


def runtime_detail_view(request: HttpRequest, runtime_id: str) -> HttpResponse:
    runtime = _service().get_runtime(runtime_id)
    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            if action == "start":
                _service().start_runtime(runtime_id, actor=request.user)
                messages.success(request, f"Started {runtime_id}.")
            elif action == "stop":
                _service().stop_runtime(runtime_id, actor=request.user)
                messages.success(request, f"Stopped {runtime_id}.")
            elif action == "restart":
                _service().restart_runtime(runtime_id, actor=request.user)
                messages.success(request, f"Restarted {runtime_id}.")
            elif action == "recreate":
                _service().recreate_runtime(runtime_id, actor=request.user)
                messages.success(request, f"Recreated {runtime_id}.")
            elif action == "smoke_test":
                result = _service().smoke_test_runtime(runtime_id, actor=request.user)
                messages.success(request, f"Smoke test finished: {result['output']}")
            elif action == "rotate_key":
                _service().rotate_runtime_key(runtime_id, actor=request.user)
                messages.success(request, f"Rotated LiteLLM key for {runtime_id}.")
            elif action == "revoke_key":
                _service().revoke_runtime_key(runtime_id, actor=request.user)
                messages.success(request, f"Revoked LiteLLM key for {runtime_id}.")
            elif action == "sync_limits":
                _service().sync_runtime_limits(runtime_id, actor=request.user)
                messages.success(request, f"Repaired LiteLLM limit sync for {runtime_id}.")
            elif action == "update_limits":
                _service().update_runtime_limits(
                    runtime_id,
                    budget_usd=_float_from_post(request.POST.get("budget_usd")),
                    rpm_limit=_int_from_post(request.POST.get("rpm_limit")),
                    tpm_limit=_int_from_post(request.POST.get("tpm_limit")),
                    model=request.POST.get("model") or None,
                    actor=request.user,
                )
                messages.success(request, f"Applied LiteLLM limits for {runtime_id}.")
            elif action == "save_secret":
                _service().upsert_runtime_secret(
                    runtime_id,
                    request.POST["secret_kind"],
                    request.POST["secret_value"],
                    actor=request.user,
                )
                messages.success(request, "Secret updated and runtime recreated.")
            elif action == "test_secret":
                _service().test_runtime_secret(runtime_id, int(request.POST["secret_ref_id"]))
                messages.success(request, "Secret verification finished.")
            elif action == "save_integration":
                editing_connection = IntegrationConnection.objects.filter(pk=_selected_int(request.POST.get("connection_id"))).first()
                _service().upsert_integration_connection(
                    integration_type=editing_connection.integration_type if editing_connection else request.POST["integration_type"],
                    runtime_id=runtime_id,
                    display_name=request.POST.get("display_name") or None,
                    enabled=_bool_from_post(request.POST.get("enabled")),
                    config={
                        "allow_from": request.POST.get("allow_from", ""),
                        "provider": request.POST.get("search_provider", ""),
                        "base_url": request.POST.get("search_base_url", ""),
                    },
                    actor=request.user,
                )
                messages.success(request, "Integration updated and runtime recreated.")
            elif action == "test_integration":
                _service().test_integration_connection(int(request.POST["connection_id"]))
                messages.success(request, "Integration test finished.")
            elif action == "delete_runtime":
                if request.POST.get("confirm_runtime_id") != runtime_id:
                    raise ValueError(f"Type {runtime_id} to confirm runtime deletion.")
                _service().delete_runtime_service(runtime_id, actor=request.user)
                messages.success(request, f"Deleted {runtime_id}.")
                return redirect("/admin/")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, str(exc))
        return redirect(f"/admin/runtimes/{runtime_id}/")

    detail = _service().runtime_detail_payload(runtime_id)
    selected_integration = None
    if request.GET.get("edit_integration"):
        selected_integration = next(
            (item for item in detail["integrations"] if str(item["id"]) == request.GET.get("edit_integration")),
            None,
        )
    selected_secret = None
    if request.GET.get("edit_secret"):
        selected_secret = next(
            (item for item in detail["secrets"] if str(item["id"]) == request.GET.get("edit_secret")),
            None,
        )
    integration_form = {
        "connection_id": selected_integration["id"] if selected_integration else "",
        "integration_type": selected_integration["integration_type"] if selected_integration else "telegram",
        "display_name": selected_integration["display_name"] if selected_integration else "",
        "allow_from": (selected_integration.get("config") or {}).get("allow_from", "") if selected_integration else "",
        "search_provider": (selected_integration.get("config") or {}).get("provider", detail["settings"].get("search_provider", "")) if selected_integration else detail["settings"].get("search_provider", ""),
        "search_base_url": (selected_integration.get("config") or {}).get("base_url", detail["settings"].get("search_base_url", "")) if selected_integration else detail["settings"].get("search_base_url", ""),
        "enabled": (selected_integration["status"] != "disabled") if selected_integration else True,
    }
    secret_form = {
        "secret_kind": selected_secret["secret_kind"] if selected_secret else "telegram_bot_token",
    }
    return render(
        request,
        "admin/runtime_detail.html",
        _operator_context(
            title=f"Runtime {runtime_id}",
            active_page="runtime",
            page_description="Единый экран управления рантаймом: lifecycle, лимиты, ключи, интеграции, секреты и диагностика.",
            runtime=runtime,
            detail=detail,
            runtime_subnav=_runtime_nav(runtime_id, "overview"),
            selected_integration=selected_integration,
            selected_secret=selected_secret,
            integration_form=integration_form,
            secret_form=secret_form,
        ),
    )


def runtime_wizard_view(request: HttpRequest) -> HttpResponse:
    runtime = None
    step = int(request.POST.get("step") or request.GET.get("step") or "1")
    wizard_data = _wizard_state(request)
    if request.method == "GET" and request.GET.get("reset") == "1":
        wizard_data = _wizard_defaults()
        request.session[WIZARD_SESSION_KEY] = wizard_data
        request.session.modified = True
    if request.method == "POST":
        wizard_data = _update_wizard_state_from_post(request, wizard_data, step)
        action = request.POST.get("action", "next")
        if action == "previous":
            step = max(1, step - 1)
        elif action == "backfill":
            _service().backfill_runtime_related_records()
            messages.success(request, "Backfilled runtime-related records.")
        elif action == "validate":
            if not wizard_data["runtime_id"] or not wizard_data["gateway_port"]:
                messages.error(request, "runtime_id and gateway_port are required.")
            elif wizard_data["telegram_enabled"] and not wizard_data["telegram_bot_token"]:
                messages.error(request, "telegram_bot_token is required when Telegram is enabled.")
            else:
                messages.success(request, "Validation passed.")
                step = 5
        elif action == "create":
            try:
                runtime = _service().create_or_update_runtime(
                    _service().RuntimeCreateRequest(
                        runtime_id=wizard_data["runtime_id"],
                        gateway_port=int(wizard_data["gateway_port"]),
                        model=wizard_data["model"],
                        telegram_enabled=wizard_data["telegram_enabled"],
                        telegram_bot_token=wizard_data["telegram_bot_token"],
                        telegram_allow_from=wizard_data["telegram_allow_from"],
                        runtime_role=wizard_data["runtime_role"],
                        budget_usd=_float_from_post(wizard_data["budget_usd"]),
                        rpm_limit=_int_from_post(wizard_data["rpm_limit"]),
                        tpm_limit=_int_from_post(wizard_data["tpm_limit"]),
                        tenant_slug=wizard_data["tenant"] or None,
                        plan_slug=wizard_data["plan"] or None,
                        desired_channels={
                            "telegram": wizard_data["telegram_enabled"],
                            "slack": wizard_data["slack_enabled"],
                            "mattermost": wizard_data["mattermost_enabled"],
                        },
                        settings={
                            "http_enabled": wizard_data["http_enabled"],
                            "search_provider": wizard_data["search_provider"],
                            "search_base_url": wizard_data["search_base_url"],
                        },
                        default_provider_connection_id=_int_from_post(wizard_data["provider_connection_id"]),
                        default_provider_model_id=_int_from_post(wizard_data["provider_model_id"]),
                    ),
                    actor=request.user,
                )
                if request.POST.get("run_smoke_test"):
                    _service().smoke_test_runtime(runtime.runtime_id, actor=request.user)
                messages.success(request, f"Runtime {runtime.runtime_id} created.")
                request.session[WIZARD_SESSION_KEY] = _wizard_defaults()
                request.session.modified = True
                return redirect(f"/admin/runtimes/{runtime.runtime_id}/")
            except Exception as exc:  # noqa: BLE001
                messages.error(request, str(exc))
                step = 5
        else:
            step = min(5, step + 1)
    return render(
        request,
        "admin/runtime_wizard.html",
        _operator_context(
            title="Runtime Wizard",
            active_page="runtime-wizard",
            page_description="Пошаговый операторский мастер создания и первичной настройки NullClaw runtime.",
            step=step,
            wizard=wizard_data,
            providers=_service().list_provider_connections(),
            models=_service().models_catalog(),
            wizard_steps=_wizard_steps(step),
            baseline_ready=bool(_service().list_provider_connections()) and bool(_service().models_catalog()),
            runtime=runtime,
        ),
    )


def runtime_diagnostics_view(request: HttpRequest, runtime_id: str) -> HttpResponse:
    runtime = get_object_or_404(Runtime, runtime_id=runtime_id)
    diagnostics = _service().runtime_diagnostics_summary(runtime_id)
    return render(
        request,
        "admin/runtime_diagnostics.html",
        _operator_context(
            title=f"Diagnostics · {runtime_id}",
            active_page="runtime",
            page_description="Summary-first observability view. Raw payloads are secondary; Grafana, Loki, Tempo and Mimir stay the source of truth.",
            runtime=runtime,
            diagnostics=diagnostics,
            runtime_subnav=_runtime_nav(runtime_id, "diagnostics"),
        ),
    )


def runtime_chat_view(request: HttpRequest, runtime_id: str) -> HttpResponse:
    runtime = _service().get_runtime(runtime_id)
    session_id = request.GET.get("session")
    if request.method == "POST" and request.POST.get("action") == "create":
        session = _service().create_chat_session(runtime_id, actor=request.user, title=request.POST.get("title", ""))
        return redirect(f"/admin/runtimes/{runtime_id}/chat/?session={session.pk}")
    if request.method == "POST" and request.POST.get("action") == "send" and session_id:
        try:
            result = _service().send_chat_message(runtime_id, int(session_id), request.POST["message"], actor=request.user)
            messages.success(request, f"Response received from {result['model']}.")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, str(exc))
        return redirect(f"/admin/runtimes/{runtime_id}/chat/?session={session_id}")
    if request.method == "POST" and request.POST.get("action") == "reset" and session_id:
        _service().reset_chat_session(runtime_id, int(session_id))
        messages.success(request, "Chat session reset.")
        return redirect(f"/admin/runtimes/{runtime_id}/chat/?session={session_id}")
    sessions = _service().list_chat_sessions(runtime_id)
    active_session = runtime.chat_sessions.filter(pk=session_id).first() if session_id else None
    diagnostics = _service().runtime_diagnostics_summary(runtime_id)
    return render(
        request,
        "admin/runtime_chat.html",
        _operator_context(
            title=f"Runtime Chat · {runtime_id}",
            active_page="runtime",
            page_description="Минимальный операторский чат для setup/debug задач. Полноценный playground остаётся отдельным контуром.",
            runtime=runtime,
            sessions=sessions,
            active_session=active_session,
            messages=[] if active_session is None else active_session.messages.all(),
            trace_links=diagnostics["traces"]["items"],
            runtime_subnav=_runtime_nav(runtime_id, "chat"),
        ),
    )


def providers_view(request: HttpRequest) -> HttpResponse:
    selected_provider = ProviderConnection.objects.filter(pk=_selected_int(request.GET.get("edit"))).first()
    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            if action == "save":
                editing_provider = ProviderConnection.objects.filter(pk=_selected_int(request.POST.get("provider_id"))).first()
                _service().upsert_provider_connection(
                    name=editing_provider.name if editing_provider else request.POST["name"],
                    display_name=request.POST.get("display_name", editing_provider.display_name if editing_provider else request.POST["name"]),
                    provider_kind=request.POST["provider_kind"],
                    scope=request.POST.get("scope", "platform"),
                    tenant_slug=request.POST.get("tenant") or None,
                    base_url=request.POST.get("base_url", ""),
                    api_key=request.POST.get("api_key", ""),
                    actor=request.user,
                )
                messages.success(request, "Provider updated." if editing_provider else "Provider created.")
            elif action == "delete":
                _service().delete_provider_connection_service(int(request.POST["connection_id"]), actor=request.user)
                messages.success(request, "Provider deleted.")
            elif action == "test":
                _service().test_provider_connection(int(request.POST["connection_id"]))
                messages.success(request, "Provider test finished.")
            elif action == "backfill":
                _service().backfill_runtime_related_records()
                messages.success(request, "Provider/model baseline rebuilt from current runtime state.")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, str(exc))
        return redirect("/admin/providers/")
    providers = _service().list_provider_connections()
    return render(
        request,
        "admin/providers.html",
        _operator_context(
            title="Providers",
            active_page="providers",
            page_description="Платформенные и tenant-scoped model providers, их ключи, base URL и статус проверки.",
            providers=providers,
            provider_form=_provider_form_state(selected_provider),
            selected_provider=selected_provider,
            tenants=Tenant.objects.all(),
            baseline_ready=bool(providers),
        ),
    )


def models_view(request: HttpRequest) -> HttpResponse:
    selected_model = ProviderModel.objects.filter(pk=_selected_int(request.GET.get("edit"))).first()
    if request.method == "POST":
        try:
            action = request.POST.get("action", "save")
            if action == "save":
                editing_model = ProviderModel.objects.filter(pk=_selected_int(request.POST.get("model_id"))).first()
                _service().upsert_provider_model(
                    alias=editing_model.alias if editing_model else request.POST["alias"],
                    display_name=request.POST.get("display_name", editing_model.display_name if editing_model else request.POST["alias"]),
                    provider_model=request.POST["provider_model"],
                    provider_connection_id=_int_from_post(request.POST.get("provider_connection_id")),
                    tenant_slug=request.POST.get("tenant") or None,
                    is_custom=True if editing_model is None else editing_model.is_custom,
                    is_platform_default=_bool_from_post(request.POST.get("is_platform_default")),
                )
                messages.success(request, "Model updated." if editing_model else "Model created.")
            elif action == "toggle":
                enabled = _bool_from_post(request.POST.get("enabled"))
                _service().set_provider_model_enabled(int(request.POST["model_id"]), enabled)
                messages.success(request, "Model state updated.")
            elif action == "delete":
                _service().delete_provider_model_service(int(request.POST["model_id"]))
                messages.success(request, "Model deleted.")
            elif action == "backfill":
                _service().backfill_runtime_related_records()
                messages.success(request, "Provider/model baseline rebuilt from current runtime state.")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, str(exc))
        return redirect("/admin/models/")
    models = _service().models_catalog()
    runtimes = _service().list_runtimes()
    model_dependencies = {
        model.pk: [
            runtime.runtime_id
            for runtime in runtimes
            if runtime.default_provider_model_id == model.pk or runtime.model == model.alias
        ]
        for model in models
    }
    return render(
        request,
        "admin/models.html",
        _operator_context(
            title="Models",
            active_page="models",
            page_description="Model aliases, provider mapping, platform defaults and runtime dependencies.",
            models=models,
            providers=_service().list_provider_connections(),
            runtimes=runtimes,
            model_dependencies=model_dependencies,
            model_form=_model_form_state(selected_model),
            selected_model=selected_model,
            tenants=Tenant.objects.all(),
            baseline_ready=bool(models),
        ),
    )


def integrations_view(request: HttpRequest) -> HttpResponse:
    selected_connection = IntegrationConnection.objects.filter(pk=_selected_int(request.GET.get("edit"))).first()
    if request.method == "POST":
        action = request.POST.get("action", "save")
        try:
            if action == "save":
                editing_connection = IntegrationConnection.objects.filter(pk=_selected_int(request.POST.get("connection_id"))).first()
                _service().upsert_integration_connection(
                    integration_type=editing_connection.integration_type if editing_connection else request.POST["integration_type"],
                    runtime_id=editing_connection.runtime.runtime_id if editing_connection and editing_connection.runtime else request.POST.get("runtime_id") or None,
                    tenant_slug=request.POST.get("tenant") or None,
                    display_name=request.POST.get("display_name") or (editing_connection.display_name if editing_connection else None),
                    enabled=_bool_from_post(request.POST.get("enabled")),
                    config={
                        "allow_from": request.POST.get("allow_from", ""),
                        "provider": request.POST.get("search_provider", ""),
                        "base_url": request.POST.get("search_base_url", ""),
                    },
                    actor=request.user,
                )
                messages.success(
                    request,
                    "Integration updated and runtime recreated." if editing_connection else "Integration created and runtime recreated.",
                )
            elif action == "delete":
                _service().delete_integration_connection_service(int(request.POST["connection_id"]), actor=request.user)
                messages.success(request, "Integration deleted.")
            elif action == "test":
                _service().test_integration_connection(int(request.POST["connection_id"]))
                messages.success(request, "Integration test finished.")
            elif action == "backfill":
                _service().backfill_runtime_related_records()
                messages.success(request, "Integration and secret references rebuilt from current runtime state.")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, str(exc))
        return redirect("/admin/integrations/")
    integrations = _service().integration_connections_payload()
    return render(
        request,
        "admin/integrations.html",
        _operator_context(
            title="Integrations",
            active_page="integrations",
            page_description="Runtime and tenant integrations with first-class Telegram flow and structured support for Slack, Mattermost and Search.",
            integrations=integrations,
            runtimes=_service().list_runtimes(),
            integration_form=_integration_form_state(selected_connection),
            selected_connection=selected_connection,
            tenants=Tenant.objects.all(),
            baseline_ready=bool(integrations),
        ),
    )


def secrets_view(request: HttpRequest) -> HttpResponse:
    selected_provider = ProviderConnection.objects.filter(pk=_selected_int(request.GET.get("provider"))).first()
    selected_integration = IntegrationConnection.objects.filter(pk=_selected_int(request.GET.get("integration"))).first()
    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            if action == "runtime_secret_save":
                _service().upsert_runtime_secret(
                    request.POST["runtime_id"],
                    request.POST["secret_kind"],
                    request.POST["secret_value"],
                    actor=request.user,
                )
                messages.success(request, "Runtime secret saved and runtime recreated.")
            elif action == "runtime_secret_test":
                _service().test_runtime_secret(request.POST["runtime_id"], int(request.POST["secret_ref_id"]))
                messages.success(request, "Runtime secret tested.")
            elif action == "provider_test":
                _service().test_provider_connection(int(request.POST["connection_id"]))
                messages.success(request, "Provider secret tested via provider connection.")
            elif action == "provider_secret_save":
                provider = ProviderConnection.objects.get(pk=int(request.POST["connection_id"]))
                _service().upsert_provider_connection(
                    name=provider.name,
                    display_name=provider.display_name,
                    provider_kind=provider.provider_kind,
                    scope=provider.scope,
                    tenant_slug=provider.tenant.slug if provider.tenant else None,
                    base_url=request.POST.get("base_url", provider.base_url),
                    api_key=request.POST.get("api_key", ""),
                    actor=request.user,
                )
                messages.success(request, "Provider secret settings saved.")
            elif action == "integration_secret_save":
                connection = IntegrationConnection.objects.select_related("runtime").get(pk=int(request.POST["connection_id"]))
                if connection.runtime is None:
                    raise ValueError("Only runtime-scoped integration secrets are supported in v1.")
                _service().upsert_runtime_secret(
                    connection.runtime.runtime_id,
                    request.POST["secret_kind"],
                    request.POST["secret_value"],
                    actor=request.user,
                )
                messages.success(request, "Integration secret saved and runtime recreated.")
            elif action == "integration_test":
                _service().test_integration_connection(int(request.POST["connection_id"]))
                messages.success(request, "Integration tested.")
            elif action == "backfill":
                _service().backfill_runtime_related_records()
                messages.success(request, "Runtime, provider and integration secret references rebuilt.")
        except Exception as exc:  # noqa: BLE001
            messages.error(request, str(exc))
        return redirect("/admin/secrets/")
    runtimes = _service().list_runtimes()
    providers = _service().list_provider_connections()
    integrations = _service().list_integration_connections()
    runtime_secrets = {runtime.runtime_id: _service().runtime_secret_payload(runtime.runtime_id) for runtime in runtimes}
    provider_secrets = _service().provider_connection_secret_payload()
    integration_secrets = _service().integration_secrets_payload()
    selected_provider = selected_provider or (providers[0] if providers else None)
    selected_integration = selected_integration or (integrations[0] if integrations else None)
    return render(
        request,
        "admin/secrets.html",
        _operator_context(
            title="Secrets",
            active_page="secrets",
            page_description="Write-only masked secret management for runtimes, integrations and provider credentials. Raw Infisical internals stay hidden.",
            runtimes=runtimes,
            runtime_secrets=runtime_secrets,
            provider_secrets=provider_secrets,
            integration_secrets=integration_secrets,
            providers=providers,
            integrations=integrations,
            selected_provider=selected_provider,
            selected_integration=selected_integration,
            baseline_ready=bool(runtime_secrets) or bool(provider_secrets) or bool(integration_secrets),
        ),
    )


def raw_runtime_admin_redirect_view(request: HttpRequest) -> HttpResponse:
    return redirect("/admin/")


def raw_provider_admin_redirect_view(request: HttpRequest) -> HttpResponse:
    return redirect("/admin/providers/")


def raw_model_admin_redirect_view(request: HttpRequest) -> HttpResponse:
    return redirect("/admin/models/")


def raw_integration_admin_redirect_view(request: HttpRequest) -> HttpResponse:
    return redirect("/admin/integrations/")


def raw_secret_admin_redirect_view(request: HttpRequest) -> HttpResponse:
    return redirect("/admin/secrets/")


def raw_action_log_admin_redirect_view(request: HttpRequest) -> HttpResponse:
    return redirect("/admin/")


def raw_diagnostic_snapshot_redirect_view(request: HttpRequest, snapshot_id: str | None = None) -> HttpResponse:
    if snapshot_id:
        snapshot = RuntimeDiagnosticSnapshot.objects.select_related("runtime").filter(pk=_selected_int(snapshot_id)).first()
        if snapshot:
            return redirect(reverse("controlplane-runtime-diagnostics", args=[snapshot.runtime.runtime_id]))
    return redirect("/admin/")


def raw_chat_session_redirect_view(request: HttpRequest, session_id: str | None = None) -> HttpResponse:
    if session_id:
        session = RuntimeChatSession.objects.select_related("runtime").filter(pk=_selected_int(session_id)).first()
        if session:
            return redirect(f"{reverse('controlplane-runtime-chat', args=[session.runtime.runtime_id])}?session={session.pk}")
    return redirect("/admin/")
