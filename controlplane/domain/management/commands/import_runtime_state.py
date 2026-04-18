from __future__ import annotations

from django.core.management.base import BaseCommand

from orchestrator.service_layer import backfill_runtime_related_records, import_json_state_if_empty


class Command(BaseCommand):
    help = "Import existing .aquarium/state/runtimes.json into the Django control-plane database."

    def handle(self, *args, **options):
        import_json_state_if_empty()
        backfill_runtime_related_records()
        self.stdout.write(self.style.SUCCESS("Imported runtime state into control plane DB."))
