"""Smart `auto|on|off` resolution for configured DecisionPort providers."""

from __future__ import annotations

from typing import Literal

from vedit.ports.decision import DecisionPort
from vedit.providers.registry import ProviderRegistry, build_default_registry

DecisionMode = Literal["auto", "on", "off"]


def resolve_decision_port(
    mode: DecisionMode = "auto",
    *,
    use_decision: bool | None = None,
    registry: ProviderRegistry | None = None,
) -> DecisionPort | None:
    """Resolve `DecisionPort` according to `auto|on|off` mode and optional legacy boolean flag."""
    if use_decision is True:
        effective_mode: DecisionMode = "on"
    elif use_decision is False:
        effective_mode = "off"
    else:
        effective_mode = mode

    if effective_mode == "off":
        return None

    reg = registry or build_default_registry()
    if effective_mode == "on":
        return reg.resolve("decision")

    cap_cfg = reg._config.defaults.get("decision")
    if cap_cfg is None:
        return None
    if cap_cfg.options.get("auto_enable", True) is False:
        return None
    if not cap_cfg.has_credentials():
        return None
    return reg.resolve("decision")


def resolve_decision_confidence_threshold(
    registry: ProviderRegistry | None = None,
    *,
    default: float = 0.75,
) -> float:
    """Return configured confidence threshold for auto-accepting calibrated decision scores."""
    reg = registry or build_default_registry()
    cap_cfg = reg._config.defaults.get("decision")
    if cap_cfg is None:
        return default
    raw = cap_cfg.options.get("confidence_threshold")
    if raw is None:
        return default
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return default
