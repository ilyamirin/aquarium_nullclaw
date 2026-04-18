from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = os.environ.get("CONTROLPLANE_SECRET_KEY", "aquarium-controlplane-dev-secret-key")
DEBUG = os.environ.get("CONTROLPLANE_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "controlplane.domain",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "controlplane.core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "controlplane" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

WSGI_APPLICATION = "controlplane.core.wsgi.application"
ASGI_APPLICATION = "controlplane.core.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / ".aquarium" / "state" / "controlplane.sqlite3"),
        "OPTIONS": {
            "timeout": 20,
        },
    }
}

AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / ".aquarium" / "state" / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/admin/"
LOGOUT_REDIRECT_URL = "/admin/login/"

UNFOLD = {
    "SITE_TITLE": "Aquarium Control Plane",
    "SITE_HEADER": "Aquarium",
    "SITE_SYMBOL": "dashboard",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SIDEBAR": {
        "show_search": False,
        "command_search": False,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Operator Console",
                "items": [
                    {"title": "Home", "icon": "dashboard", "link": "/admin/"},
                    {"title": "Runtime Wizard", "icon": "build", "link": "/admin/runtime-wizard/"},
                ],
            },
            {
                "title": "Configuration",
                "items": [
                    {"title": "Providers", "icon": "hub", "link": "/admin/providers/"},
                    {"title": "Models", "icon": "tune", "link": "/admin/models/"},
                    {"title": "Integrations", "icon": "device_hub", "link": "/admin/integrations/"},
                    {"title": "Secrets", "icon": "key", "link": "/admin/secrets/"},
                ],
            },
        ],
    },
}
