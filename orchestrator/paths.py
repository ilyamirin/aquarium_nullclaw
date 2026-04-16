from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
LOCAL_STATE_DIR = ROOT_DIR / ".aquarium"
STATE_DIR = LOCAL_STATE_DIR / "state"
GENERATED_DIR = LOCAL_STATE_DIR / "generated"
RUNTIMES_DIR = LOCAL_STATE_DIR / "runtimes"
STATE_FILE = STATE_DIR / "runtimes.json"
COMPOSE_FILE = GENERATED_DIR / "aquarium-nullclaw-runtimes.compose.yml"
COMPOSE_PROJECT_NAME = "aquarium-nullclaw-runtimes"
INFISICAL_STACK_ENV_FILE = ROOT_DIR / "infisical-stack" / ".env"


def runtime_dir(runtime_id: str) -> Path:
    return RUNTIMES_DIR / runtime_id


def runtime_home(runtime_id: str) -> Path:
    return runtime_dir(runtime_id) / "home"


def workspace_dir(runtime_id: str) -> Path:
    return runtime_home(runtime_id) / "workspace"


def runtime_env_file(runtime_id: str) -> Path:
    return runtime_dir(runtime_id) / "runtime.env"
