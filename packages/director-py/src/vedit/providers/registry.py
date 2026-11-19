"""Capability-based provider registry (zero hardcoded vendor dependencies)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from vedit.providers.config import ProvidersConfig, load_providers_config

Capability = Literal[
    "transcription", "decision", "media_ops", "audio_catalog", "video_breakdown"
]
ProviderFactory = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    capability: Capability
    name: str
    factory: ProviderFactory
    implemented: bool = True
    description: str = ""
    extra_metadata: dict[str, Any] = field(default_factory=dict)


class ProviderNotFoundError(KeyError):
    """Raised when a requested provider or capability is not registered."""


class ProviderRegistry:
    """Resolves concrete capability providers purely from configuration and registration."""

    def __init__(self, config: ProvidersConfig | None = None) -> None:
        self._config = config or load_providers_config()
        self._specs: dict[tuple[Capability, str], ProviderSpec] = {}

    def register(self, spec: ProviderSpec) -> None:
        self._specs[(spec.capability, spec.name)] = spec

    def list_specs(self, capability: Capability | None = None) -> list[ProviderSpec]:
        items = [
            spec
            for (cap, _), spec in sorted(self._specs.items())
            if capability is None or cap == capability
        ]
        return items

    def active_provider_name(self, capability: Capability) -> str:
        cap_cfg = self._config.defaults.get(capability)
        if cap_cfg is None:
            raise ProviderNotFoundError(
                f"No default provider configured for capability '{capability}'."
            )
        return cap_cfg.primary

    def resolve(self, capability: Capability, provider_name: str | None = None) -> Any:
        target = provider_name or self.active_provider_name(capability)
        spec = self._specs.get((capability, target))
        if spec is None:
            available = [s.name for s in self.list_specs(capability)]
            raise ProviderNotFoundError(
                f"Provider '{target}' is not registered for '{capability}'. Available: {available}"
            )
        cap_cfg = self._config.defaults.get(capability)
        if cap_cfg is None:
            options: dict[str, Any] = {}
        elif cap_cfg.primary == target:
            options = dict(cap_cfg.options)
        else:
            fallback_opts = cap_cfg.options.get("fallback_options")
            if isinstance(fallback_opts, dict) and isinstance(fallback_opts.get(target), dict):
                options = dict(fallback_opts[target])
            else:
                options = {}
        return spec.factory(options)

    def status_report(self) -> dict[str, dict[str, Any]]:
        """Summarize configured vs registered capabilities without leaking credentials."""
        report: dict[str, dict[str, Any]] = {}
        for capability in (
            "transcription",
            "decision",
            "media_ops",
            "audio_catalog",
            "video_breakdown",
        ):
            cap_cfg = self._config.defaults.get(capability)
            specs = self.list_specs(capability)  # type: ignore[arg-type]
            report[capability] = {
                "configured_primary": cap_cfg.primary if cap_cfg else None,
                "auth_type": cap_cfg.auth_type if cap_cfg else None,
                "fallback": cap_cfg.fallback if cap_cfg else [],
                "credentials_present": cap_cfg.has_credentials() if cap_cfg else False,
                "registered": [
                    {
                        "name": s.name,
                        "implemented": s.implemented,
                        "description": s.description,
                    }
                    for s in specs
                ],
            }
        return report


def build_default_registry(config: ProvidersConfig | None = None) -> ProviderRegistry:
    """Create a registry populated with all configured built-in provider plugins."""
    from vedit.providers.builtins import register_builtin_providers

    registry = ProviderRegistry(config=config)
    register_builtin_providers(registry)
    return registry
