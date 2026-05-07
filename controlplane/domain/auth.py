from __future__ import annotations

from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


class AutheliaRemoteUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            return self.get_response(request)

        header_name = getattr(settings, "AUTHELIA_HEADER_USER", "HTTP_REMOTE_USER")
        subject = request.META.get(header_name, "").strip()
        if subject:
            user_model = get_user_model()
            username = subject[:150]
            user, _ = user_model.objects.get_or_create(
                username=username,
                defaults={
                    "is_staff": True,
                    "is_superuser": True,
                },
            )
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)


def authelia_login_view(request: HttpRequest) -> HttpResponse:
    next_url = request.GET.get("next") or getattr(settings, "AUTHELIA_DEFAULT_REDIRECT", "/admin/")
    target = getattr(settings, "AUTHELIA_LOGIN_URL", "/")
    encoded_next = quote(next_url, safe="")
    if "{next}" in target:
        return redirect(target.replace("{next}", encoded_next))
    if target.endswith("rd="):
        return redirect(f"{target}{encoded_next}")
    if target.startswith("/"):
        query = urlencode({"next": next_url})
        separator = "&" if "?" in target else "?"
        return redirect(f"{target}{separator}{query}")
    parsed = urlsplit(target)
    if not parsed.path:
        target = urlunsplit((parsed.scheme, parsed.netloc, "/", parsed.query, parsed.fragment))
    query = urlencode({"rd": next_url})
    separator = "&" if "?" in target else "?"
    return redirect(f"{target}{separator}{query}")


def authelia_logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    target = getattr(settings, "AUTHELIA_LOGOUT_URL", getattr(settings, "AUTHELIA_LOGIN_URL", "/"))
    if target.startswith("/"):
        return redirect(target)
    return redirect(target)
