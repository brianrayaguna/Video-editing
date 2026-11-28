"""DecisionPort-backed semantic beat enrichment, tiered directing, and Gate 1 critique."""

from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from vedit.director.exemplar_retrieval import DirectingContext
from vedit.director.storyboard import (
    _device_lead_window,
    check_storyboard,
    validate_storyboard_contract,
)
from vedit.ports.decision import (
    DecisionAnswer,
    DecisionPort,
    DecisionQuestion,
    validate_decision_batch,
)

DirectingTier = Literal["draft", "standard", "flagship"]

_MAX_BEATS_PER_BATCH = 60  # 2 questions per beat = 120 <= 128 hard DecisionPort limit.


@dataclass(slots=True)
class SemanticDirectingResult:
    """Output of a semantic directing pass over a storyboard."""

    storyboard: dict[str, Any]
    tier: DirectingTier
    updated_beat_ids: list[str] = field(default_factory=list)
    rejected_suggestions: list[dict[str, Any]] = field(default_factory=list)
    batches_sent: int = 0


@dataclass(slots=True)
class PreRenderGateResult:
    """Output of Gate 1 pre-render deterministic + semantic storyboard critique."""

    passed: bool
    tier: DirectingTier
    deterministic_score: float
    semantic_score: float | None
    selected_hook_index: int | None
    hook_scores: list[dict[str, Any]] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _default_device_and_placeholders(idioms: dict[str, Any]) -> tuple[str, list[str]]:
    default_device = "camera_drift"
    placeholders: list[str] = ["todo", "tbd", "?"]
    for item in idioms.get("idioms") or []:
        iid = item.get("idiom_id")
        params = item.get("params") or {}
        if iid == "default_device_share" and params.get("default_device"):
            default_device = str(params["default_device"])
        elif iid == "story_need_stated" and params.get("placeholder_markers"):
            placeholders = [str(m).lower() for m in params["placeholder_markers"]]
    return default_device, placeholders


def _is_placeholder_need(story_need: str, placeholders: list[str]) -> bool:
    clean = story_need.strip().lower()
    if len(clean) < 3:
        return True
    return any(clean == m or clean.startswith(f"{m} ") for m in placeholders)


def _known_devices(idioms: dict[str, Any]) -> set[str]:
    return {
        str(dev)
        for cls in (idioms.get("device_classes") or {}).values()
        for dev in (cls.get("devices") or [])
    }


def _extract_choice(ans: DecisionAnswer | None) -> str:
    if ans is None:
        return ""
    val = ans.raw.get("choice")
    if val is None:
        val = ans.raw.get("value")
    return str(val or "").strip()


def _extract_text(ans: DecisionAnswer | None) -> str:
    if ans is None:
        return ""
    val = ans.raw.get("text")
    if val is None:
        val = ans.raw.get("value")
    return str(val or "").strip()


_HOOK_RUBRIC_LEVELS: list[str] = [
    "Generic or vague hook with weak visual specificity",
    "Basic hook with limited visual tension",
    "Clear hook with adequate visual anchor",
    "Strong visual hook with immediate narrative curiosity",
    "Broadcast-grade visual hook with unmistakable concrete imagery",
]

_COHERENCE_RUBRIC_LEVELS: list[str] = [
    "Disjointed beats with weak visual progression",
    "Uneven pacing or mostly generic visual devices",
    "Coherent narrative-to-visual alignment",
    "Tight pacing escalation and strong visual specificity",
    "Broadcast-grade visual storytelling with clear escalation",
]


def _extract_score(ans: DecisionAnswer | None, *, scale_levels: int | None = None) -> float | None:
    if ans is None:
        return None
    legend = ans.raw.get("legend")
    max_level = (
        max(1, len(legend) - 1)
        if isinstance(legend, dict) and len(legend) >= 2
        else (max(1, scale_levels - 1) if scale_levels and scale_levels >= 2 else None)
    )
    for key in ("score", "value"):
        if key in ans.raw and ans.raw[key] is not None:
            raw_val = ans.raw[key]
            if isinstance(raw_val, bool):
                return None
            try:
                num = float(raw_val)
            except (TypeError, ValueError):
                return None
            if not math.isfinite(num):
                return None
            if max_level is not None and 0.0 <= num <= float(max_level):
                return round((num / float(max_level)) * 100.0, 2)
            # Normalize 0..1 calibrated probabilities onto 0..100 scale.
            if 0.0 <= num <= 1.0:
                return round(num * 100.0, 2)
            return round(max(0.0, min(100.0, num)), 2)
    return None


def extract_narrative_signals(
    transcript: dict[str, Any] | str,
    decision_port: DecisionPort,
) -> dict[str, list[str]]:
    """Extract places, numeric claims, and narrative pivots in one `d1.2-ultra` spans call."""
    if isinstance(transcript, str):
        text = transcript.strip()
    else:
        raw_text = str(transcript.get("text") or "").strip()
        if not raw_text:
            segs = transcript.get("segments") or []
            raw_text = " ".join(str(s.get("text") or "") for s in segs).strip()
        if not raw_text:
            words = transcript.get("words") or []
            raw_text = " ".join(str(w.get("word") or w.get("text") or "") for w in words).strip()
        text = raw_text

    if not text:
        return {"places": [], "numeric_claims": [], "narrative_pivots": []}

    questions = [
        DecisionQuestion(
            name="places",
            question_type="spans",
            instructions=(
                "Extract every geographic place, country, city, waterway, or region "
                "named in the narration."
            ),
            max_items=24,
        ),
        DecisionQuestion(
            name="numeric_claims",
            question_type="spans",
            instructions=(
                "Extract every quantified statistic, measurement, distance, currency figure, "
                "or percentage."
            ),
            max_items=24,
        ),
        DecisionQuestion(
            name="narrative_pivots",
            question_type="spans",
            instructions=(
                "Extract every turning-point or contrast clause that shifts narrative tension "
                "or reveals a twist."
            ),
            max_items=12,
        ),
    ]
    validate_decision_batch(questions, [])
    res = decision_port.evaluate(state=text, questions=questions, images=None)

    def _collect(q_name: str) -> list[str]:
        ans = res.answers.get(q_name)
        if ans is None:
            return []
        seen: set[str] = set()
        out_items: list[str] = []
        for sp in ans.spans:
            found = sp.get("found")
            if found is not None and float(found) < 0.5:
                continue
            item = str(sp.get("text") or "").strip()
            if item and item.lower() not in seen:
                seen.add(item.lower())
                out_items.append(item)
        return out_items

    return {
        "places": _collect("places"),
        "numeric_claims": _collect("numeric_claims"),
        "narrative_pivots": _collect("narrative_pivots"),
    }


def _recompute_beat_timing(
    beat: dict[str, Any],
    idioms: dict[str, Any],
    *,
    is_opening: bool,
) -> None:
    if is_opening:
        beat["start_s"] = 0.0
    elif "sync_word_s" in beat:
        default_lead = float((idioms.get("auto_director") or {}).get("default_lead_s", 0.2))
        lead_info = _device_lead_window(idioms, beat["device"])
        if lead_info is not None:
            lo, hi = float(lead_info[1][0]), float(lead_info[1][1])
            lead = min(max(default_lead, lo), hi)
        else:
            lead = default_lead
        beat["start_s"] = round(max(0.0, float(beat["sync_word_s"]) - lead), 3)
    beat["end_s"] = round(max(float(beat["end_s"]), float(beat["start_s"]) + 0.25), 3)


def enrich_storyboard_semantically(
    storyboard: dict[str, Any],
    idioms: dict[str, Any],
    *,
    decision_port: DecisionPort | None = None,
    context: DirectingContext | None = None,
    tier: DirectingTier = "standard",
) -> SemanticDirectingResult:
    """Enrich fallback or all beats using an injected DecisionPort while enforcing constraints."""
    out = copy.deepcopy(storyboard)
    if tier == "draft" or decision_port is None:
        return SemanticDirectingResult(storyboard=out, tier=tier)

    known = _known_devices(idioms)
    overrides = out.get("overrides") or {}
    banned = {str(d) for d in (overrides.get("banned_devices") or [])}
    locked = {str(b) for b in (overrides.get("locked_beat_ids") or [])}
    allowed = sorted(known - banned)
    if not allowed:
        return SemanticDirectingResult(storyboard=out, tier=tier)

    default_device, placeholders = _default_device_and_placeholders(idioms)
    beats = list(out.get("beats") or [])
    if tier == "flagship":
        candidates = [(idx, b) for idx, b in enumerate(beats)]
    else:
        candidates = [
            (idx, b)
            for idx, b in enumerate(beats)
            if b["device"] == default_device
            or _is_placeholder_need(str(b.get("story_need") or ""), placeholders)
        ]

    if not candidates:
        return SemanticDirectingResult(storyboard=out, tier=tier)

    criteria = {dev: f"Select {dev} visual device" for dev in allowed}
    updated_beat_ids: list[str] = []
    rejected_suggestions: list[dict[str, Any]] = []
    batches_sent = 0

    for offset in range(0, len(candidates), _MAX_BEATS_PER_BATCH):
        chunk = candidates[offset : offset + _MAX_BEATS_PER_BATCH]
        questions: list[DecisionQuestion] = []
        beat_summaries: list[dict[str, Any]] = []
        for _idx, beat in chunk:
            bid = str(beat["beat_id"])
            hints = [h.summary for h in (context.beat_hints.get(bid, []) if context else [])]
            beat_summaries.append(
                {
                    "beat_id": bid,
                    "clause": beat.get("clause"),
                    "function": beat.get("function"),
                    "current_device": beat.get("device"),
                    "hints": hints,
                }
            )
            questions.append(
                DecisionQuestion(
                    name=f"{bid}__device",
                    question_type="choice",
                    instructions=(
                        f"Choose the clearest concrete visual device for beat {bid}: "
                        f"{beat.get('clause', '')!r}"
                    ),
                    criteria=criteria,
                )
            )
            questions.append(
                DecisionQuestion(
                    name=f"{bid}__story_need",
                    question_type="text",
                    instructions=(
                        f"State the concrete visual story_need for beat {bid} "
                        "in one short imperative phrase."
                    ),
                )
            )

        validate_decision_batch(questions, [])
        state = {
            "brand_id": out.get("brand_id"),
            "story_shape": (out.get("story") or {}).get("shape"),
            "tier": tier,
            "allowed_devices": allowed,
            "global_triggers": (
                [h.item_id for h in context.global_triggers] if context else []
            ),
            "beats": beat_summaries,
        }
        batch_res = decision_port.evaluate(state=state, questions=questions, images=None)
        batches_sent += 1

        for idx, beat in chunk:
            bid = str(beat["beat_id"])
            suggested_dev = _extract_choice(batch_res.answers.get(f"{bid}__device"))
            suggested_need = _extract_text(batch_res.answers.get(f"{bid}__story_need"))

            if bid in locked:
                if suggested_dev or suggested_need:
                    rejected_suggestions.append(
                        {
                            "beat_id": bid,
                            "suggested_device": suggested_dev,
                            "reason": "locked_beat",
                        }
                    )
                continue

            changed = False
            if suggested_dev:
                if suggested_dev in banned:
                    rejected_suggestions.append(
                        {
                            "beat_id": bid,
                            "suggested_device": suggested_dev,
                            "reason": "banned_device",
                        }
                    )
                    continue
                if suggested_dev not in known:
                    rejected_suggestions.append(
                        {
                            "beat_id": bid,
                            "suggested_device": suggested_dev,
                            "reason": "unknown_device",
                        }
                    )
                    continue
                if beat["device"] != suggested_dev:
                    beat["device"] = suggested_dev
                    _recompute_beat_timing(beat, idioms, is_opening=(idx == 0))
                    changed = True
            if (
                len(suggested_need) >= 3
                and not _is_placeholder_need(suggested_need, placeholders)
                and beat.get("story_need") != suggested_need
            ):
                beat["story_need"] = suggested_need
                changed = True
            if changed:
                updated_beat_ids.append(bid)

    if updated_beat_ids and out.get("directing_source") == "auto":
        out["directing_source"] = "mixed"

    contract_errors = validate_storyboard_contract(out)
    if contract_errors:
        raise ValueError(f"Semantic directing broke storyboard contract: {contract_errors}")

    return SemanticDirectingResult(
        storyboard=out,
        tier=tier,
        updated_beat_ids=updated_beat_ids,
        rejected_suggestions=rejected_suggestions,
        batches_sent=batches_sent,
    )


def _score_candidate_hooks(
    storyboard: dict[str, Any],
    idioms: dict[str, Any],
    candidate_hooks: list[dict[str, Any]],
    *,
    decision_port: DecisionPort | None,
    tier: DirectingTier,
) -> tuple[int | None, list[dict[str, Any]]]:
    if not candidate_hooks:
        return None, []

    known = _known_devices(idioms)
    banned = {str(d) for d in ((storyboard.get("overrides") or {}).get("banned_devices") or [])}
    default_device, placeholders = _default_device_and_placeholders(idioms)
    recent_eps = list(storyboard.get("recent_episodes") or [])
    recent_hooks = {
        str(ep.get("hook_mechanism")) for ep in recent_eps if ep.get("hook_mechanism")
    }
    recent_sigs = {
        str(ep.get("signature_image")) for ep in recent_eps if ep.get("signature_image")
    }

    model_scores: dict[int, float] = {}
    if decision_port is not None and tier != "draft":
        for offset in range(0, len(candidate_hooks), 120):
            chunk = candidate_hooks[offset : offset + 120]
            questions = [
                DecisionQuestion(
                    name=f"hook_{offset + k}__score",
                    question_type="score",
                    instructions=(
                        f"Rate hook candidate {offset + k} for visual specificity and retention."
                    ),
                    criteria=list(_HOOK_RUBRIC_LEVELS),
                )
                for k in range(len(chunk))
            ]
            validate_decision_batch(questions, [])
            res = decision_port.evaluate(
                state={
                    "brand_id": storyboard.get("brand_id"),
                    "recent_hooks": sorted(recent_hooks),
                    "candidates": chunk,
                },
                questions=questions,
                images=None,
            )
            for k in range(len(chunk)):
                idx = offset + k
                sc = _extract_score(res.answers.get(f"hook_{idx}__score"))
                if sc is not None:
                    model_scores[idx] = sc

    hook_scores: list[dict[str, Any]] = []
    for idx, cand in enumerate(candidate_hooks):
        det_score = 70.0
        dev = str(cand.get("device") or "")
        if dev in known and dev not in banned and dev != default_device:
            det_score += 15.0
        elif dev == default_device or dev in banned:
            det_score -= 10.0

        need = str(cand.get("story_need") or "")
        if not _is_placeholder_need(need, placeholders) and len(need.strip()) >= 10:
            det_score += 10.0

        mech = str(cand.get("hook_mechanism") or "")
        sig = str(cand.get("signature_image") or "")
        duplicate_penalty = 0.0
        if mech and mech in recent_hooks:
            duplicate_penalty += 35.0
        if sig and sig in recent_sigs:
            duplicate_penalty += 25.0

        det_clamped = max(0.0, min(100.0, det_score))
        if idx in model_scores:
            combined = 0.6 * det_clamped + 0.4 * model_scores[idx] - duplicate_penalty
        else:
            combined = det_clamped - duplicate_penalty
        final_score = round(max(0.0, min(100.0, combined)), 2)

        hook_scores.append(
            {
                "index": idx,
                "hook_mechanism": mech or None,
                "device": dev or None,
                "score": final_score,
                "duplicate_penalty": duplicate_penalty,
            }
        )

    best = max(hook_scores, key=lambda item: (item["score"], -item["index"]))
    return int(best["index"]), hook_scores


def critique_storyboard_prerender(
    storyboard: dict[str, Any],
    idioms: dict[str, Any],
    *,
    decision_port: DecisionPort | None = None,
    context: DirectingContext | None = None,
    tier: DirectingTier = "standard",
    candidate_hooks: list[dict[str, Any]] | None = None,
    min_score: float = 75.0,
) -> PreRenderGateResult:
    """Run Gate 1 pre-render critique combining idiom checks and optional DecisionPort scoring."""
    report = check_storyboard(storyboard, idioms)
    issues = [asdict(i) for i in report.issues]

    selected_hook_index, hook_scores = _score_candidate_hooks(
        storyboard,
        idioms,
        candidate_hooks or [],
        decision_port=decision_port,
        tier=tier,
    )

    semantic_score: float | None = None
    if decision_port is not None and tier != "draft":
        q = DecisionQuestion(
            name="prerender_coherence",
            question_type="score",
            instructions=(
                "Rate overall narrative-visual coherence, pacing escalation, and concrete "
                "visual specificity of this storyboard."
            ),
            criteria=list(_COHERENCE_RUBRIC_LEVELS),
        )
        validate_decision_batch([q], [])
        res = decision_port.evaluate(
            state={
                "brand_id": storyboard.get("brand_id"),
                "story": storyboard.get("story"),
                "beats": storyboard.get("beats"),
                "global_triggers": (
                    [h.item_id for h in context.global_triggers] if context else []
                ),
            },
            questions=[q],
            images=None,
        )
        semantic_score = _extract_score(res.answers.get("prerender_coherence"))

    passed = (
        report.passed
        and report.score >= min_score
        and (semantic_score is None or semantic_score >= min_score)
    )
    return PreRenderGateResult(
        passed=passed,
        tier=tier,
        deterministic_score=report.score,
        semantic_score=semantic_score,
        selected_hook_index=selected_hook_index,
        hook_scores=hook_scores,
        issues=issues,
    )
