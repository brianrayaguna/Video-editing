"""Load capability-to-provider mappings from YAML without exposing secrets."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from vedit.contracts import find_repo_root
from vedit.providers.env import load_dotenv_safe


class CapabilityProviderConfig(BaseModel):
    primary: str
    fallback: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)

    @property
    def auth_type(self) -> str:
        return str(self.options.get("auth_type") or "api_key")

    def has_credentials(self) -> bool:
        kind = self.auth_type
        if kind == "local":
            if self.primary == "rea_video":
                configured_bin = str(self.options.get("binary") or "").strip()
                if configured_bin:
                    return Path(configured_bin).expanduser().is_file()
                env_bin = os.environ.get("VEDIT_REA_VIDEO_BIN", "").strip()
                if env_bin:
                    return Path(env_bin).expanduser().is_file()
                try:
                    repo_bin = (
                        find_repo_root() / "tools" / "rea-video" / ".venv" / "bin" / "rea-video"
                    )
                    if repo_bin.is_file():
                        return True
                except FileNotFoundError:
                    pass
                return shutil.which("rea-video") is not None
            return True
        env_name = self.options.get("api_key_env")
        if not env_name:
            return True
        return bool(os.environ.get(str(env_name)))

    def has_api_key(self) -> bool:
        return self.has_credentials()


class ProvidersConfig(BaseModel):
    defaults: dict[str, CapabilityProviderConfig] = Field(default_factory=dict)


def load_providers_config(
    config_path: Path | None = None,
    *,
    repo_root: Path | None = None,
) -> ProvidersConfig:
    """Read `config/providers.yaml`, falling back to `config/providers.example.yaml`."""
    root = repo_root or find_repo_root()
    load_dotenv_safe(repo_root=root)

    if config_path is not None:
        target = config_path
    else:
        local_cfg = root / "config" / "providers.yaml"
        target = local_cfg if local_cfg.is_file() else root / "config" / "providers.example.yaml"

    if not target.is_file():
        raise FileNotFoundError(f"Providers config not found: {target}")

    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return ProvidersConfig.model_validate(raw)
