"""JSON Schema loading and Draft 2020-12 contract validation utilities."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def find_repo_root(start: Path | None = None) -> Path:
    """Locate repository root containing `contracts/` via start path, ancestors, or env."""
    if start is not None:
        cursor = start.resolve()
        for candidate in [cursor, *cursor.parents]:
            if (candidate / "contracts").is_dir():
                return candidate

    env_root = os.environ.get("VEDIT_REPO_ROOT", "").strip()
    if env_root:
        candidate = Path(env_root).expanduser().resolve()
        if (candidate / "contracts").is_dir():
            return candidate

    cursor = Path(__file__).resolve()
    for candidate in [cursor, *cursor.parents, Path.cwd().resolve(), Path("/opt/vedit")]:
        if (candidate / "contracts").is_dir():
            return candidate
    raise FileNotFoundError("Could not locate `contracts/` directory in parent hierarchy.")


def load_schema(schema_filename: str, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or find_repo_root()
    schema_path = root / "contracts" / schema_filename
    if not schema_path.is_file():
        raise FileNotFoundError(f"Missing contract schema: {schema_path}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def validate_against_contract(
    payload: dict[str, Any],
    schema_filename: str,
    repo_root: Path | None = None,
) -> list[str]:
    """Validate a JSON-compatible payload against a contract schema. Returns error messages."""
    schema = load_schema(schema_filename, repo_root=repo_root)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    return [f"{list(err.path)}: {err.message}" for err in validator.iter_errors(payload)]


def load_platform_targets(repo_root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load and validate all platform presets under `profiles/platforms/*.json`."""
    root = repo_root or find_repo_root()
    plat_dir = root / "profiles" / "platforms"
    results: dict[str, dict[str, Any]] = {}
    for file_path in sorted(plat_dir.glob("*.json")):
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        errors = validate_against_contract(payload, "platform_target.schema.json", repo_root=root)
        if errors:
            raise ValueError(f"Platform preset {file_path.name} failed contract check: {errors}")
        results[payload["platform_id"]] = payload
    return results


def load_brand_template_catalog(
    path: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Load and validate a brand template catalog JSON file."""
    root = repo_root or find_repo_root()
    payload = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_against_contract(payload, "brand_template.schema.json", repo_root=root)
    if errors:
        raise ValueError(f"Brand template catalog {path} failed contract check: {errors}")
    return payload


def _resolve_policy_token(policy: dict[str, Any], token_ref: str) -> Any | None:
    """Resolve a dotted token path against a raw BrandStylePolicy dictionary."""
    parts = [p for p in token_ref.split(".") if p]
    if not parts:
        return None
    soft = policy.get("soft_priors") or {}
    visual = soft.get("visual_tokens") or {}
    roots: dict[str, Any] = {
        "palette_roles": visual.get("palette_roles") or {},
        "typography": visual.get("typography") or {},
        "motion_style": visual.get("motion_style") or {},
        "audio_style": soft.get("audio_style") or {},
    }
    cursor: Any = roots
    for part in parts:
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    return cursor


def _resolve_template_composition_path(
    comp_path: str,
    *,
    brand_dir: Path,
    repo_root: Path,
) -> Path | None:
    raw = Path(comp_path)
    if raw.is_absolute():
        return raw if raw.is_file() else None
    for base in (repo_root, brand_dir, brand_dir / "templates"):
        cand = (base / raw).resolve()
        if cand.is_file():
            return cand
    return None


def validate_brand_tree(
    brand_dir: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Validate runtime policy plus optional playbook/catalog under one brand directory."""
    root = repo_root or find_repo_root()
    brand_dir = brand_dir.resolve()
    if not brand_dir.is_dir():
        raise FileNotFoundError(f"Brand directory not found: {brand_dir}")

    policy_path = brand_dir / "brand_style_policy.json"
    if not policy_path.is_file():
        raise FileNotFoundError(f"Missing runtime policy: {policy_path}")

    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    errors = validate_against_contract(policy, "brand_style_policy.schema.json", repo_root=root)
    if errors:
        raise ValueError(f"{policy_path.name} failed contract check: {errors}")
    if "grammar_triggers" in policy or "exemplar_bank" in policy:
        raise ValueError(
            f"{policy_path.name} must not include advisory grammar_triggers/exemplar_bank; "
            "store those in editorial_playbook.json"
        )

    brand_id = str(policy["brand_id"])
    policy_rel = (
        str(policy_path.relative_to(root))
        if policy_path.is_relative_to(root)
        else str(policy_path)
    )
    validated: dict[str, Any] = {
        "brand_id": brand_id,
        "policy": policy_rel,
        "playbook": None,
        "templates": None,
    }

    playbook_path = brand_dir / "editorial_playbook.json"
    if playbook_path.is_file():
        playbook = json.loads(playbook_path.read_text(encoding="utf-8"))
        playbook_errors = validate_against_contract(
            playbook, "editorial_playbook.schema.json", repo_root=root
        )
        if playbook_errors:
            raise ValueError(f"{playbook_path.name} failed contract check: {playbook_errors}")
        if playbook.get("brand_id") != brand_id:
            raise ValueError(
                f"Playbook brand_id {playbook.get('brand_id')!r} != policy brand_id {brand_id!r}"
            )
        validated["playbook"] = (
            str(playbook_path.relative_to(root))
            if playbook_path.is_relative_to(root)
            else str(playbook_path)
        )

    catalog_path = brand_dir / "templates" / "catalog.json"
    if catalog_path.is_file():
        catalog = load_brand_template_catalog(catalog_path, repo_root=root)
        if catalog.get("brand_id") != brand_id:
            raise ValueError(
                f"Template catalog brand_id {catalog.get('brand_id')!r} "
                f"!= policy brand_id {brand_id!r}"
            )
        for entry in catalog.get("templates") or []:
            tid = str(entry.get("template_id") or "")
            comp_path = str(entry.get("composition_path") or "")
            if not _resolve_template_composition_path(
                comp_path,
                brand_dir=brand_dir,
                repo_root=root,
            ):
                raise ValueError(
                    f"Template {tid!r} references missing composition_path: {comp_path!r}"
                )
            for var in entry.get("variables") or []:
                token_ref = var.get("token_ref")
                if isinstance(token_ref, str) and token_ref.strip():
                    if _resolve_policy_token(policy, token_ref.strip()) is None:
                        raise ValueError(
                            f"Template {tid!r} variable {var.get('id')!r} references "
                            f"unresolved policy token_ref: {token_ref!r}"
                        )
        validated["templates"] = (
            str(catalog_path.relative_to(root))
            if catalog_path.is_relative_to(root)
            else str(catalog_path)
        )

    return validated


def validate_all_brand_trees(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Validate every brand directory under `profiles/brands/`."""
    root = repo_root or find_repo_root()
    brands_root = root / "profiles" / "brands"
    if not brands_root.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for brand_dir in sorted(p for p in brands_root.iterdir() if p.is_dir()):
        if not (brand_dir / "brand_style_policy.json").is_file():
            continue
        results.append(validate_brand_tree(brand_dir, repo_root=root))
    return results
