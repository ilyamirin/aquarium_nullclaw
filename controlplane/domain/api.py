from __future__ import annotations

import json
from typing import Any, Callable

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponseNotAllowed, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from controlplane.domain.models import IntegrationConnection, ProviderConnection, ProviderModel, RuntimeSecretRef


def _service():
    from orchestrator import service_layer

    return service_layer


def _operator_guard(view: Callable[..., JsonResponse]) -> Callable[..., JsonResponse]:
    @login_required
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        if not request.user.is_staff:
            return JsonResponse({"detail": "forbidden"}, status=403)
        return view(request, *args, **kwargs)

    return wrapped


def _json_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    return json.loads(request.body.decode("utf-8"))


def _runtime_payload(runtime: Any) -> dict[str, Any]:
    return {
        "runtime_id": runtime.runtime_id,
        "enabled": runtime.enabled,
        "tenant": runtime.tenant.slug if runtime.tenant else None,
        "plan": runtime.plan.slug if runtime.plan else None,
        "runtime_profile": runtime.runtime_profile.slug if runtime.runtime_profile else None,
        "gateway_port": runtime.gateway_port,
        "model": runtime.model,
        "telegram_enabled": runtime.telegram_enabled,
        "health_status": runtime.health_status,
        "lifecycle_status": runtime.lifecycle_status,
        "last_error": runtime.last_error,
        "generated_config_path": runtime.generated_config_path,
    }


@csrf_exempt
@_operator_guard
def runtimes_collection(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"items": [_runtime_payload(runtime) for runtime in _service().list_runtimes()]})
    if request.method == "POST":
        payload = _json_body(request)
        runtime = _service().create_or_update_runtime(
            _service().RuntimeCreateRequest(
                runtime_id=payload["runtime_id"],
                gateway_port=int(payload["gateway_port"]),
                model=payload.get("model") or "openai/qwen/qwen3.6-plus",
                telegram_enabled=bool(payload.get("telegram_enabled", False)),
                telegram_bot_token=payload.get("telegram_bot_token", ""),
                telegram_allow_from=payload.get("telegram_allow_from", "373793732"),
                runtime_role=payload.get("runtime_role"),
                budget_usd=payload.get("budget_usd"),
                rpm_limit=payload.get("rpm_limit"),
                tpm_limit=payload.get("tpm_limit"),
                tenant_slug=payload.get("tenant"),
                plan_slug=payload.get("plan"),
            ),
            actor=request.user,
        )
        return JsonResponse(_runtime_payload(runtime), status=201)
    return HttpResponseNotAllowed(["GET", "POST"])


@csrf_exempt
@_operator_guard
def runtime_detail(request: HttpRequest, runtime_id: str) -> JsonResponse:
    runtime = _service().get_runtime(runtime_id)
    if request.method == "GET":
        return JsonResponse(_service().runtime_detail_payload(runtime_id))
    if request.method == "PATCH":
        payload = _json_body(request)
        runtime = _service().create_or_update_runtime(
            _service().RuntimeCreateRequest(
                runtime_id=runtime.runtime_id,
                gateway_port=int(payload.get("gateway_port", runtime.gateway_port)),
                model=payload.get("model", runtime.model),
                telegram_enabled=bool(payload.get("telegram_enabled", runtime.telegram_enabled)),
                telegram_bot_token=payload.get("telegram_bot_token", ""),
                telegram_allow_from=payload.get("telegram_allow_from", "373793732"),
                runtime_role=payload.get("runtime_role", runtime.runtime_profile.slug if runtime.runtime_profile else None),
                budget_usd=payload.get("budget_usd", runtime.litellm_budget_usd),
                rpm_limit=payload.get("rpm_limit", runtime.litellm_rpm_limit),
                tpm_limit=payload.get("tpm_limit", runtime.litellm_tpm_limit),
                tenant_slug=payload.get("tenant", runtime.tenant.slug if runtime.tenant else None),
                plan_slug=payload.get("plan", runtime.plan.slug if runtime.plan else None),
            ),
            actor=request.user,
        )
        return JsonResponse(_runtime_payload(runtime))
    if request.method == "DELETE":
        _service().delete_runtime_service(runtime_id, keep_files=bool(_json_body(request).get("keep_files", False)), actor=request.user)
        return JsonResponse({"deleted": runtime_id})
    return HttpResponseNotAllowed(["GET", "PATCH", "DELETE"])


@csrf_exempt
@_operator_guard
def runtime_action(request: HttpRequest, runtime_id: str, action: str) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if action == "start":
        return JsonResponse(_runtime_payload(_service().start_runtime(runtime_id, actor=request.user)))
    if action == "stop":
        return JsonResponse(_runtime_payload(_service().stop_runtime(runtime_id, actor=request.user)))
    if action == "restart":
        return JsonResponse(_runtime_payload(_service().recreate_runtime(runtime_id, actor=request.user)))
    if action == "recreate":
        return JsonResponse(_runtime_payload(_service().recreate_runtime(runtime_id, actor=request.user)))
    if action == "smoke-test":
        return JsonResponse(_service().smoke_test_runtime(runtime_id, actor=request.user))
    return JsonResponse({"detail": "unknown action"}, status=404)


@csrf_exempt
@_operator_guard
def runtime_limits(request: HttpRequest, runtime_id: str) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse(_service().read_runtime_limits(runtime_id))
    if request.method == "PATCH":
        payload = _json_body(request)
        return JsonResponse(
            _service().update_runtime_limits(
                runtime_id,
                budget_usd=payload.get("budget_usd"),
                rpm_limit=payload.get("rpm_limit"),
                tpm_limit=payload.get("tpm_limit"),
                model=payload.get("model"),
                actor=request.user,
            )
        )
    return HttpResponseNotAllowed(["GET", "PATCH"])


@csrf_exempt
@_operator_guard
def runtime_sync_limits(request: HttpRequest, runtime_id: str) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    return JsonResponse(_service().sync_runtime_limits(runtime_id, actor=request.user))


@csrf_exempt
@_operator_guard
def runtime_key_action(request: HttpRequest, runtime_id: str, action: str) -> JsonResponse:
    if request.method == "GET" and action == "inspect":
        return JsonResponse(_service().inspect_runtime_key(runtime_id))
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if action == "rotate":
        return JsonResponse(_runtime_payload(_service().rotate_runtime_key(runtime_id, actor=request.user)))
    if action == "revoke":
        _service().revoke_runtime_key(runtime_id, actor=request.user)
        return JsonResponse({"revoked": runtime_id})
    return JsonResponse({"detail": "unknown action"}, status=404)


@csrf_exempt
@_operator_guard
def runtime_diagnostics(request: HttpRequest, runtime_id: str, kind: str) -> JsonResponse:
    if request.method == "POST" and kind == "probe":
        snapshot = _service().refresh_runtime_diagnostics(runtime_id)
        return JsonResponse({"summary": snapshot.summary, "logs": snapshot.logs, "traces": snapshot.traces, "metrics": snapshot.metrics})
    if request.method == "POST" and kind == "check-secrets":
        return JsonResponse(_service().runtime_secret_check(runtime_id))
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET", "POST"])
    if kind == "summary":
        return JsonResponse(_service().runtime_diagnostics_summary(runtime_id))
    if kind == "logs":
        return JsonResponse(_service().runtime_logs_view(runtime_id))
    if kind == "traces":
        return JsonResponse(_service().runtime_traces_view(runtime_id))
    if kind == "metrics":
        return JsonResponse(_service().runtime_metrics_view(runtime_id))
    if kind == "config":
        return JsonResponse(_service().runtime_config_view(runtime_id))
    return JsonResponse({"detail": "unknown diagnostics kind"}, status=404)


@csrf_exempt
@_operator_guard
def runtime_chat_sessions(request: HttpRequest, runtime_id: str) -> JsonResponse:
    if request.method == "GET":
        items = [{"id": session.pk, "title": session.title, "updated_at": session.updated_at.isoformat()} for session in _service().list_chat_sessions(runtime_id)]
        return JsonResponse({"items": items})
    if request.method == "POST":
        payload = _json_body(request)
        session = _service().create_chat_session(runtime_id, actor=request.user, title=payload.get("title", ""))
        return JsonResponse({"id": session.pk, "title": session.title}, status=201)
    return HttpResponseNotAllowed(["GET", "POST"])


@_operator_guard
def runtime_chat_session_detail(request: HttpRequest, runtime_id: str, session_id: int) -> JsonResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    session = _service().get_runtime(runtime_id).chat_sessions.get(pk=session_id)
    items = [{"role": message.role, "content": message.content, "metadata": message.metadata} for message in session.messages.all()]
    return JsonResponse({"id": session.pk, "title": session.title, "messages": items})


@csrf_exempt
@_operator_guard
def runtime_chat_messages(request: HttpRequest, runtime_id: str, session_id: int) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    payload = _json_body(request)
    return JsonResponse(_service().send_chat_message(runtime_id, session_id, payload["message"], actor=request.user))


@csrf_exempt
@_operator_guard
def runtime_chat_reset(request: HttpRequest, runtime_id: str, session_id: int) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    return JsonResponse(_service().reset_chat_session(runtime_id, session_id))


@csrf_exempt
@_operator_guard
def runtime_secrets(request: HttpRequest, runtime_id: str) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"items": _service().runtime_secret_payload(runtime_id)})
    if request.method == "POST":
        payload = _json_body(request)
        secret_value = payload.get("value", payload.get("secret_value", ""))
        ref = _service().upsert_runtime_secret(runtime_id, payload["secret_kind"], secret_value, actor=request.user)
        return JsonResponse({"id": ref.pk, "name": ref.name, "secret_kind": ref.secret_kind}, status=201)
    return HttpResponseNotAllowed(["GET", "POST"])


@csrf_exempt
@_operator_guard
def runtime_secret_test(request: HttpRequest, runtime_id: str, secret_ref_id: int) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    return JsonResponse(_service().test_runtime_secret(runtime_id, secret_ref_id))


@_operator_guard
def providers_catalog(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return JsonResponse({"items": _service().provider_connections_catalog()})


@csrf_exempt
@_operator_guard
def provider_connections_collection(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        items = [
            {
                "id": conn.pk,
                "name": conn.name,
                "display_name": conn.display_name,
                "provider_kind": conn.provider_kind,
                "scope": conn.scope,
                "tenant": conn.tenant.slug if conn.tenant else None,
                "status": conn.status,
                "base_url": conn.base_url,
                "last_error": conn.last_error,
            }
            for conn in _service().list_provider_connections()
        ]
        return JsonResponse({"items": items})
    if request.method == "POST":
        payload = _json_body(request)
        conn = _service().upsert_provider_connection(
            name=payload["name"],
            display_name=payload.get("display_name", payload["name"]),
            provider_kind=payload["provider_kind"],
            scope=payload.get("scope", "platform"),
            tenant_slug=payload.get("tenant"),
            base_url=payload.get("base_url", ""),
            api_key=payload.get("api_key", ""),
            actor=request.user,
        )
        return JsonResponse({"id": conn.pk, "name": conn.name}, status=201)
    return HttpResponseNotAllowed(["GET", "POST"])


@csrf_exempt
@_operator_guard
def provider_connection_detail(request: HttpRequest, connection_id: int) -> JsonResponse:
    conn = ProviderConnection.objects.get(pk=connection_id)
    if request.method == "PATCH":
        payload = _json_body(request)
        conn = _service().upsert_provider_connection(
            name=conn.name,
            display_name=payload.get("display_name", conn.display_name),
            provider_kind=payload.get("provider_kind", conn.provider_kind),
            scope=payload.get("scope", conn.scope),
            tenant_slug=payload.get("tenant", conn.tenant.slug if conn.tenant else None),
            base_url=payload.get("base_url", conn.base_url),
            api_key=payload.get("api_key", ""),
            actor=request.user,
        )
        return JsonResponse({"id": conn.pk, "name": conn.name})
    if request.method == "DELETE":
        _service().delete_provider_connection_service(connection_id, actor=request.user)
        return JsonResponse({"deleted": connection_id})
    if request.method == "GET":
        return JsonResponse(
            {
                "id": conn.pk,
                "name": conn.name,
                "display_name": conn.display_name,
                "provider_kind": conn.provider_kind,
                "scope": conn.scope,
                "tenant": conn.tenant.slug if conn.tenant else None,
                "status": conn.status,
                "base_url": conn.base_url,
                "last_error": conn.last_error,
            }
        )
    return HttpResponseNotAllowed(["GET", "PATCH", "DELETE"])


@csrf_exempt
@_operator_guard
def provider_connection_test(request: HttpRequest, connection_id: int) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    return JsonResponse(_service().test_provider_connection(connection_id))


@csrf_exempt
@_operator_guard
def integrations_collection(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"items": _service().integration_connections_payload()})
    if request.method == "POST":
        payload = _json_body(request)
        conn = _service().upsert_integration_connection(
            integration_type=payload["integration_type"],
            runtime_id=payload.get("runtime_id"),
            tenant_slug=payload.get("tenant"),
            display_name=payload.get("display_name"),
            enabled=bool(payload.get("enabled", True)),
            config=payload.get("config", {}),
            actor=request.user,
        )
        return JsonResponse({"id": conn.pk, "name": conn.name}, status=201)
    return HttpResponseNotAllowed(["GET", "POST"])


@csrf_exempt
@_operator_guard
def integration_detail(request: HttpRequest, connection_id: int) -> JsonResponse:
    conn = IntegrationConnection.objects.get(pk=connection_id)
    if request.method == "GET":
        return JsonResponse(
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
                "last_error": conn.last_error,
            }
        )
    if request.method == "PATCH":
        payload = _json_body(request)
        conn = _service().upsert_integration_connection(
            integration_type=payload.get("integration_type", conn.integration_type),
            runtime_id=payload.get("runtime_id", conn.runtime.runtime_id if conn.runtime else None),
            tenant_slug=payload.get("tenant", conn.tenant.slug if conn.tenant else None),
            display_name=payload.get("display_name", conn.display_name),
            enabled=bool(payload.get("enabled", conn.status != "disabled")),
            config=payload.get("config", conn.config),
            actor=request.user,
        )
        return JsonResponse({"id": conn.pk, "name": conn.name})
    if request.method == "DELETE":
        _service().delete_integration_connection_service(connection_id, actor=request.user)
        return JsonResponse({"deleted": connection_id})
    return HttpResponseNotAllowed(["GET", "PATCH", "DELETE"])


@csrf_exempt
@_operator_guard
def integration_test(request: HttpRequest, connection_id: int) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    return JsonResponse(_service().test_integration_connection(connection_id))


@_operator_guard
def models_catalog(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    items = [
        {
            "id": model.pk,
            "alias": model.alias,
            "display_name": model.display_name,
            "provider_model": model.provider_model,
            "provider_connection": model.provider_connection.name if model.provider_connection else None,
            "tenant": model.tenant.slug if model.tenant else None,
            "is_custom": model.is_custom,
            "is_platform_default": model.is_platform_default,
            "is_enabled": model.is_enabled,
        }
        for model in _service().models_catalog()
    ]
    return JsonResponse({"items": items})


@csrf_exempt
@_operator_guard
def custom_models_collection(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    payload = _json_body(request)
    model = _service().upsert_provider_model(
        alias=payload["alias"],
        display_name=payload.get("display_name", payload["alias"]),
        provider_model=payload["provider_model"],
        provider_connection_id=payload.get("provider_connection_id"),
        tenant_slug=payload.get("tenant"),
        is_custom=True,
        is_platform_default=bool(payload.get("is_platform_default", False)),
    )
    return JsonResponse({"id": model.pk, "alias": model.alias}, status=201)


@csrf_exempt
@_operator_guard
def custom_model_detail(request: HttpRequest, model_id: int) -> JsonResponse:
    model = ProviderModel.objects.get(pk=model_id)
    if request.method == "PATCH":
        payload = _json_body(request)
        model = _service().upsert_provider_model(
            alias=model.alias,
            display_name=payload.get("display_name", model.display_name),
            provider_model=payload.get("provider_model", model.provider_model),
            provider_connection_id=payload.get("provider_connection_id", model.provider_connection_id),
            tenant_slug=payload.get("tenant", model.tenant.slug if model.tenant else None),
            is_custom=True,
            is_platform_default=bool(payload.get("is_platform_default", model.is_platform_default)),
        )
        return JsonResponse({"id": model.pk, "alias": model.alias})
    if request.method == "DELETE":
        _service().delete_provider_model_service(model_id)
        return JsonResponse({"deleted": model_id})
    return HttpResponseNotAllowed(["PATCH", "DELETE"])


@_operator_guard
def runtime_wizard_options(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return JsonResponse(
        {
            "profiles": ["live", "probe", "limit-probe", "playground", "custom"],
            "providers": _service().provider_connections_catalog(),
            "models": [{"alias": model.alias, "display_name": model.display_name} for model in _service().models_catalog()],
        }
    )


@csrf_exempt
@_operator_guard
def runtime_wizard_validate(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    payload = _json_body(request)
    errors: dict[str, str] = {}
    if not payload.get("runtime_id"):
        errors["runtime_id"] = "runtime_id is required"
    if not payload.get("gateway_port"):
        errors["gateway_port"] = "gateway_port is required"
    if payload.get("telegram_enabled") and not payload.get("telegram_bot_token"):
        errors["telegram_bot_token"] = "telegram_bot_token is required when telegram is enabled"
    return JsonResponse({"valid": not errors, "errors": errors})


@csrf_exempt
@_operator_guard
def runtime_wizard_create(request: HttpRequest) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    payload = _json_body(request)
    runtime = _service().create_or_update_runtime(
        _service().RuntimeCreateRequest(
            runtime_id=payload["runtime_id"],
            gateway_port=int(payload["gateway_port"]),
            model=payload.get("model") or "openai/qwen/qwen3.6-plus",
            telegram_enabled=bool(payload.get("telegram_enabled", False)),
            telegram_bot_token=payload.get("telegram_bot_token", ""),
            telegram_allow_from=payload.get("telegram_allow_from", "373793732"),
            runtime_role=payload.get("runtime_role"),
            budget_usd=payload.get("budget_usd"),
            rpm_limit=payload.get("rpm_limit"),
            tpm_limit=payload.get("tpm_limit"),
            tenant_slug=payload.get("tenant"),
            plan_slug=payload.get("plan"),
        ),
        actor=request.user,
    )
    return JsonResponse({"runtime": _runtime_payload(runtime), "next_steps": ["chat", "diagnostics", "secrets"]}, status=201)


@_operator_guard
def integration_secrets(request: HttpRequest) -> JsonResponse:
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return JsonResponse({"items": _service().integration_secrets_payload()})


@csrf_exempt
@_operator_guard
def provider_connection_secrets(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"items": _service().provider_connection_secret_payload()})
    if request.method == "POST":
        payload = _json_body(request)
        conn = _service().upsert_provider_connection(
            name=payload["name"],
            display_name=payload.get("display_name", payload["name"]),
            provider_kind=payload["provider_kind"],
            scope=payload.get("scope", "platform"),
            tenant_slug=payload.get("tenant"),
            base_url=payload.get("base_url", ""),
            api_key=payload.get("api_key", ""),
            actor=request.user,
        )
        return JsonResponse({"id": conn.pk, "name": conn.name}, status=201)
    return HttpResponseNotAllowed(["GET", "POST"])


@csrf_exempt
@_operator_guard
def provider_connection_secret_detail(request: HttpRequest, connection_id: int) -> JsonResponse:
    if request.method == "PATCH":
        conn = ProviderConnection.objects.get(pk=connection_id)
        payload = _json_body(request)
        conn = _service().upsert_provider_connection(
            name=conn.name,
            display_name=payload.get("display_name", conn.display_name),
            provider_kind=payload.get("provider_kind", conn.provider_kind),
            scope=payload.get("scope", conn.scope),
            tenant_slug=payload.get("tenant", conn.tenant.slug if conn.tenant else None),
            base_url=payload.get("base_url", conn.base_url),
            api_key=payload.get("api_key", ""),
            actor=request.user,
        )
        return JsonResponse({"id": conn.pk, "name": conn.name})
    if request.method == "DELETE":
        _service().delete_provider_connection_service(connection_id, actor=request.user)
        return JsonResponse({"deleted": connection_id})
    return HttpResponseNotAllowed(["PATCH", "DELETE"])


@csrf_exempt
@_operator_guard
def provider_connection_secret_test(request: HttpRequest, connection_id: int) -> JsonResponse:
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    return JsonResponse(_service().test_provider_connection(connection_id))
