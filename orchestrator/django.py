from __future__ import annotations

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "controlplane.core.settings")
    import django

    django.setup()
