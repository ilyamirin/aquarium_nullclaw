from __future__ import annotations

import json

from orchestrator.models import RuntimeRecord, StateFile
from orchestrator.paths import GENERATED_DIR, RUNTIMES_DIR, STATE_DIR, STATE_FILE


def ensure_local_layout() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIMES_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        save_state(StateFile())


def load_state() -> StateFile:
    ensure_local_layout()
    return StateFile.model_validate_json(STATE_FILE.read_text())


def save_state(state: StateFile) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = state.model_dump(mode="json")
    STATE_FILE.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n")


def upsert_runtime(state: StateFile, runtime: RuntimeRecord) -> StateFile:
    state.runtimes[runtime.id] = runtime
    return state


def delete_runtime(state: StateFile, runtime_id: str) -> StateFile:
    state.runtimes.pop(runtime_id, None)
    return state
