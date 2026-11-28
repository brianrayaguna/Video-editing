"""Cartography and journey-route directing idioms registered as a domain plugin."""

from __future__ import annotations

from typing import Any

from vedit.director.idiom_registry import IdiomRegistry, _issue, _sorted_beats


def _check_head_on_place_name(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    p = idiom["params"]
    out: list[Any] = []
    for b in _sorted_beats(sb):
        head = b.get("head")
        if not head or head.get("motion", "draw") != "draw" or "sync_word_s" not in b:
            continue
        arrive = head.get("arrive_s")
        if arrive is None:
            out.append(_issue(idiom, "drawing beat has no head arrival time", b))
            continue
        delta = b["sync_word_s"] - arrive
        if delta > p["max_early_s"] + 1e-6 or delta < -p["max_late_s"] - 1e-6:
            out.append(
                _issue(
                    idiom,
                    f"head arrives {delta:+.2f}s relative to the place name "
                    f"(allowed -{p['max_late_s']}..+{p['max_early_s']}s early)",
                    b,
                )
            )
    return out


def _check_regime_change_lead(
    idiom: dict[str, Any], sb: dict[str, Any], _: dict[str, Any]
) -> list[Any]:
    lo, hi = idiom["params"]["lead_s"]
    prev: str | None = None
    out: list[Any] = []
    for b in _sorted_beats(sb):
        regime = (b.get("camera") or {}).get("regime")
        if not regime or regime == "hold":
            continue
        if prev is not None and regime != prev and "sync_word_s" in b:
            start = b["camera"].get("move_start_s", b["start_s"])
            lead = b["sync_word_s"] - start
            if not lo - 1e-6 <= lead <= hi + 1e-6:
                out.append(
                    _issue(
                        idiom,
                        f"camera {prev}->{regime} starts {lead:.2f}s before the word "
                        f"(window {lo}..{hi}s)",
                        b,
                    )
                )
        prev = regime
    return out


def register_geo_idioms(registry: IdiomRegistry) -> None:
    """Register geospatial/journey-specific idioms under domain='geo'."""
    registry.register("head_on_place_name", _check_head_on_place_name, domain="geo")
    registry.register("regime_change_lead", _check_regime_change_lead, domain="geo")
