from __future__ import annotations

from pathlib import Path
from typing import Dict

from pydantic import BaseModel, Field, field_validator


class RuntimeRecord(BaseModel):
    id: str
    enabled: bool = True
    gateway_port: int
    telegram_enabled: bool
    model: str
    runtime_role: str = "custom"
    tenant_id: str | None = None
    plan_id: str | None = None
    infisical_project_slug: str
    infisical_project_id: str
    infisical_env: str = "prod"
    infisical_path: str = "/runtime"
    litellm_key_name: str = ""
    litellm_budget_usd: float | None = None
    litellm_rpm_limit: int | None = None
    litellm_tpm_limit: int | None = None
    litellm_model_alias: str = "openai/qwen/qwen3.6-plus"
    litellm_price_input_per_million_usd: float | None = None
    litellm_price_output_per_million_usd: float | None = None
    runtime_env_file: str
    runtime_home: str
    workspace_dir: str
    generated_config_path: str

    @field_validator("id")
    @classmethod
    def validate_runtime_id(cls, value: str) -> str:
        if not value:
            raise ValueError("runtime id cannot be empty")
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
        if any(char not in allowed for char in value):
            raise ValueError("runtime id must contain only lowercase letters, digits, and hyphens")
        return value

    @field_validator("gateway_port")
    @classmethod
    def validate_gateway_port(cls, value: int) -> int:
        if value < 1 or value > 65535:
            raise ValueError("gateway port must be between 1 and 65535")
        return value

    @field_validator("runtime_role")
    @classmethod
    def validate_runtime_role(cls, value: str) -> str:
        allowed = {"live", "probe", "limit-probe", "custom"}
        if value not in allowed:
            raise ValueError(f"runtime role must be one of: {', '.join(sorted(allowed))}")
        return value

    @property
    def runtime_env_path(self) -> Path:
        return Path(self.runtime_env_file)

    @property
    def runtime_home_path(self) -> Path:
        return Path(self.runtime_home)

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace_dir)


class StateFile(BaseModel):
    runtimes: Dict[str, RuntimeRecord] = Field(default_factory=dict)
