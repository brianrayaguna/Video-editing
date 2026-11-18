"""Capability-driven provider configuration and registry."""

from vedit.providers.config import CapabilityProviderConfig, ProvidersConfig, load_providers_config
from vedit.providers.registry import (
    Capability,
    ProviderRegistry,
    ProviderSpec,
    build_default_registry,
)

__all__ = [
    "Capability",
    "CapabilityProviderConfig",
    "ProviderRegistry",
    "ProviderSpec",
    "ProvidersConfig",
    "build_default_registry",
    "load_providers_config",
]
