from __future__ import annotations

from django.core.management.base import BaseCommand

from orchestrator.service_layer import backfill_runtime_related_records


class Command(BaseCommand):
    help = "Backfill integration, secret, diagnostics, and action-log records for existing runtimes."

    def add_arguments(self, parser):
        parser.add_argument("--runtime-id", default="")

    def handle(self, *args, **options):
        count = backfill_runtime_related_records(runtime_id=options["runtime_id"] or None)
        self.stdout.write(self.style.SUCCESS(f"Backfilled runtime related records for {count} runtime(s)."))
