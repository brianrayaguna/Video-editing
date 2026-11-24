"""External per-brand episodic memory with strict repository isolation guards."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vedit.contracts import find_repo_root, validate_against_contract
from vedit.project_workspace import resolve_projects_root

BRAND_MEMORY_SCHEMA = "brand_memory.schema.json"
_BRAND_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _assert_external_path(path: Path, repo_root: Path | None = None) -> Path:
    engine_root = (repo_root or find_repo_root()).resolve()
    resolved = path.expanduser().resolve()
    if resolved.is_relative_to(engine_root):
        raise ValueError(
            f"Brand memory path {resolved} violates external workspace isolation inside "
            f"engine repository ({engine_root}). Store brand_memory.json under VEDIT_PROJECTS_ROOT."
        )
    return resolved


def resolve_brand_memory_path(
    brand_id: str,
    *,
    projects_root: Path | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Resolve `<VEDIT_PROJECTS_ROOT>/<brand_id>/brand_memory.json` outside the engine repo."""
    if not _BRAND_ID_RE.match(brand_id):
        raise ValueError(f"Invalid brand_id {brand_id!r}; must match {_BRAND_ID_RE.pattern}")
    engine_root = (repo_root or find_repo_root()).resolve()
    try:
        root_dir = resolve_projects_root(projects_root, repo_root=engine_root)
    except ValueError as exc:
        raise ValueError(f"Brand memory violates external workspace isolation: {exc}") from exc
    target = (root_dir / brand_id / "brand_memory.json").resolve()
    return _assert_external_path(target, repo_root=engine_root)


def empty_brand_memory(brand_id: str) -> dict[str, Any]:
    """Create a schema-valid empty BrandMemory structure for `brand_id`."""
    return {
        "schema_version": "1.0",
        "brand_id": brand_id,
        "updated_at": datetime.now(UTC).isoformat(),
        "recent_episodes": [],
        "winning_beats": [],
        "failure_patterns": [],
    }


def load_brand_memory(path: Path) -> dict[str, Any]:
    """Load and validate an external brand_memory.json file."""
    data = json.loads(path.expanduser().read_text(encoding="utf-8"))
    errors = validate_against_contract(data, BRAND_MEMORY_SCHEMA)
    if errors:
        raise ValueError(f"{path.name} failed contract check: {errors}")
    return data


def save_brand_memory(
    path: Path,
    memory: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> Path:
    """Validate and persist brand_memory.json strictly outside the engine repository."""
    target = _assert_external_path(path, repo_root=repo_root)
    errors = validate_against_contract(memory, BRAND_MEMORY_SCHEMA, repo_root=repo_root)
    if errors:
        raise ValueError(f"Brand memory failed contract check: {errors}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(memory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def _pattern_id(device: str | None, kind: str, description: str) -> str:
    norm = " ".join(description.lower().split())
    digest = hashlib.sha256(f"{device or ''}|{kind}|{norm}".encode()).hexdigest()[:12]
    return f"fp_{digest}"


def record_episode_outcome(
    memory: dict[str, Any],
    storyboard: dict[str, Any],
    *,
    critique_packet: dict[str, Any] | None = None,
    gate_result: dict[str, Any] | None = None,
    max_episodes: int = 50,
    max_beats: int = 200,
) -> dict[str, Any]:
    """Record episode story metadata, deduplicated failures, and high-scoring winning beats."""
    out = copy.deepcopy(memory)
    now = datetime.now(UTC).isoformat()
    out["updated_at"] = now

    project_id = str(storyboard["project_id"])
    story = storyboard.get("story") or {}
    beats = list(storyboard.get("beats") or [])
    by_id = {str(b["beat_id"]): b for b in beats if b.get("beat_id")}

    episode_entry: dict[str, Any] = {
        "project_id": project_id,
        "recorded_at": now,
        "story_shape": str(story.get("shape") or "free_form"),
    }
    for key in ("hook_mechanism", "ending_type", "signature_image"):
        val = story.get(key)
        if isinstance(val, str) and val.strip():
            episode_entry[key] = val.strip()

    rubric_score: float | None = None
    gate_passed: bool | None = None
    if gate_result is not None:
        if gate_result.get("rubric_score") is not None:
            rubric_score = float(gate_result["rubric_score"])
            episode_entry["rubric_score"] = rubric_score
        if "passed" in gate_result:
            gate_passed = bool(gate_result["passed"])
            episode_entry["passed"] = gate_passed

    recent = [ep for ep in (out.get("recent_episodes") or []) if ep.get("project_id") != project_id]
    recent.append(episode_entry)
    out["recent_episodes"] = recent[-max(1, max_episodes) :]

    dirty_beats: set[str] = set()
    failure_events: list[tuple[str | None, str, str]] = []
    if critique_packet is not None:
        det_sb = (critique_packet.get("deterministic") or {}).get("storyboard") or {}
        for issue in det_sb.get("issues") or []:
            bid = issue.get("beat_id")
            if bid:
                dirty_beats.add(str(bid))
            b_dev = str(by_id[str(bid)]["device"]) if bid and str(bid) in by_id else None
            msg = str(issue.get("message") or "").strip()
            kind = str(issue.get("idiom_id") or "storyboard_issue")
            if msg:
                failure_events.append((b_dev, kind, msg))

        for fix in ((critique_packet.get("review") or {}).get("fixes")) or []:
            if isinstance(fix, dict):
                bid = fix.get("beat_id")
                if bid:
                    dirty_beats.add(str(bid))
                b_dev = str(by_id[str(bid)]["device"]) if bid and str(bid) in by_id else None
                kind = str(fix.get("kind") or "review_fix")
                desc = str(
                    fix.get("message") or fix.get("action") or f"{kind} fix required"
                ).strip()
                failure_events.append((b_dev, kind, desc))
            elif isinstance(fix, str) and fix.strip():
                failure_events.append((None, "review_fix", fix.strip()))

    patterns = list(out.get("failure_patterns") or [])
    patterns_by_id = {str(p["pattern_id"]): p for p in patterns if p.get("pattern_id")}
    for dev, kind, desc in failure_events:
        pid = _pattern_id(dev, kind, desc)
        existing = patterns_by_id.get(pid)
        if existing is not None:
            proj_ids = list(existing.get("project_ids") or [])
            if project_id not in proj_ids:
                proj_ids.append(project_id)
                existing["project_ids"] = proj_ids
                existing["occurrences"] = int(existing.get("occurrences", 1)) + 1
                existing["last_project_id"] = project_id
        else:
            entry: dict[str, Any] = {
                "pattern_id": pid,
                "kind": kind,
                "description": desc,
                "occurrences": 1,
                "last_project_id": project_id,
                "project_ids": [project_id],
            }
            if dev:
                entry["device"] = dev
            patterns.append(entry)
            patterns_by_id[pid] = entry
    out["failure_patterns"] = patterns

    if gate_passed is True and rubric_score is not None and rubric_score >= 0.85:
        existing_winning = [
            wb for wb in (out.get("winning_beats") or []) if wb.get("project_id") != project_id
        ]
        for beat in beats:
            bid = str(beat.get("beat_id") or "")
            dev = str(beat.get("device") or "")
            if not bid or not dev or dev == "camera_drift" or bid in dirty_beats:
                continue
            wb_entry: dict[str, Any] = {
                "project_id": project_id,
                "beat_id": bid,
                "function": str(beat.get("function") or "proof"),
                "device": dev,
                "clause": str(beat.get("clause") or ""),
                "story_need": str(beat.get("story_need") or ""),
                "rubric_score": round(rubric_score, 3),
            }
            if isinstance(beat.get("treatment"), str) and beat["treatment"].strip():
                wb_entry["treatment"] = beat["treatment"].strip()
            existing_winning.append(wb_entry)
        out["winning_beats"] = existing_winning[-max(1, max_beats) :]

    errors = validate_against_contract(out, BRAND_MEMORY_SCHEMA)
    if errors:
        raise ValueError(f"Updated brand memory failed contract check: {errors}")
    return out


def export_recent_episodes(memory: dict[str, Any], *, limit: int = 5) -> list[dict[str, Any]]:
    """Export recent_episodes entries formatted strictly for storyboard.schema.json."""
    episodes = list(memory.get("recent_episodes") or [])
    sliced = episodes[-max(0, limit) :] if limit > 0 else []
    exported: list[dict[str, Any]] = []
    for ep in sliced:
        item: dict[str, Any] = {"project_id": str(ep["project_id"])}
        for key in ("hook_mechanism", "ending_type", "signature_image"):
            val = ep.get(key)
            if isinstance(val, str) and val.strip():
                item[key] = val.strip()
        exported.append(item)
    return exported
