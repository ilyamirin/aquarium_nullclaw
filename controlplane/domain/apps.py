from __future__ import annotations

from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _configure_sqlite(sender, connection, **kwargs) -> None:
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=20000;")


class DomainConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "controlplane.domain"
    verbose_name = "Aquarium Control Plane"

    def ready(self) -> None:
        connection_created.connect(_configure_sqlite, dispatch_uid="aquarium-controlplane-sqlite-pragmas")
