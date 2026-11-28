"""JSON Schema loading and Draft 2020-12 contract validation utilities."""

from __future__ import annotations

import functools
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


@functools.lru_cache(maxsize=64)
def _load_cached_schema_and_validator(
    schema_path_str: str,
    mtime_ns: int,
) -> tuple[dict[str, Any], Draft202012Validator]:
    del mtime_ns
    schema = json.loads(Path(schema_path_str).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema, Draft202012Validator(schema)


def _schema_entry(
    schema_filename: str,
    repo_root: Path | None = None,
) -> tuple[dict[str, Any], Draft202012Validator]:
    root = repo_root or find_repo_root()
    schema_path = (root / "contracts" / schema_filename).resolve()
    if not schema_path.is_file():
        raise FileNotFoundError(f"Missing contract schema: {schema_path}")
    return _load_cached_schema_and_validator(str(schema_path), schema_path.stat().st_mtime_ns)


def load_schema(schema_filename: str, repo_root: Path | None = None) -> dict[str, Any]:
    schema, _ = _schema_entry(schema_filename, repo_root=repo_root)
    return schema


def list_contract_schemas(repo_root: Path | None = None) -> list[str]:
    """Discover and validate all Draft 2020-12 schema files under `contracts/*.schema.json`."""
    root = repo_root or find_repo_root()
    names = [p.name for p in sorted((root / "contracts").glob("*.schema.json"))]
    for name in names:
        load_schema(name, repo_root=root)
    return names


def validate_against_contract(
    payload: dict[str, Any],
    schema_filename: str,
    repo_root: Path | None = None,
) -> list[str]:
    """Validate a JSON-compatible payload against a contract schema. Returns error messages."""
    _, validator = _schema_entry(schema_filename, repo_root=repo_root)
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
        return None
    for base in (repo_root, brand_dir, brand_dir / "templates"):
        base_resolved = base.resolve()
        cand = (base_resolved / raw).resolve()
        if cand.is_relative_to(base_resolved) and cand.is_file():
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
        str(policy_path.relative_to(root)) if policy_path.is_relative_to(root) else str(policy_path)
    )
    validated: dict[str, Any] = {
        "brand_id": brand_id,
        "policy": policy_rel,
        "playbook": None,
        "directing_idioms": None,
        "templates": None,
        "audio_themes": None,
    }

    idioms_path = brand_dir / "directing_idioms.json"
    idioms: dict[str, Any] | None = None
    if idioms_path.is_file():
        idioms = json.loads(idioms_path.read_text(encoding="utf-8"))
        idiom_errors = validate_against_contract(
            idioms, "directing_idioms.schema.json", repo_root=root
        )
        if idiom_errors:
            raise ValueError(f"{idioms_path.name} failed contract check: {idiom_errors}")
        if idioms.get("brand_id") != brand_id:
            raise ValueError(
                f"Directing idioms brand_id {idioms.get('brand_id')!r} "
                f"!= policy brand_id {brand_id!r}"
            )
        validated["directing_idioms"] = (
            str(idioms_path.relative_to(root))
            if idioms_path.is_relative_to(root)
            else str(idioms_path)
        )

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
        if idioms is not None:
            from vedit.director.storyboard_plan import check_realization_catalog
            from vedit.models import BrandTemplateCatalog

            realization_errors = check_realization_catalog(
                idioms,
                BrandTemplateCatalog.model_validate(catalog),
            )
            if realization_errors:
                raise ValueError(f"directing_idioms.json device_realization: {realization_errors}")
        validated["templates"] = (
            str(catalog_path.relative_to(root))
            if catalog_path.is_relative_to(root)
            else str(catalog_path)
        )

    audio_themes_path = brand_dir / "audio_themes.json"
    if audio_themes_path.is_file():
        try:
            raw_themes = json.loads(audio_themes_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"audio_themes.json invalid JSON: {exc}") from exc
        if not isinstance(raw_themes, dict) or not raw_themes:
            raise ValueError("audio_themes.json must be a non-empty JSON object of theme profiles")
        for theme_name, cfg in raw_themes.items():
            if not isinstance(cfg, dict):
                raise ValueError(f"audio_themes.json theme {theme_name!r} must be a JSON object")
            kws = cfg.get("keywords")
            valid_kws = (
                isinstance(kws, list)
                and bool(kws)
                and all(isinstance(k, str) and k.strip() for k in kws)
            )
            if not valid_kws:
                raise ValueError(
                    f"audio_themes.json theme {theme_name!r} requires non-empty keywords"
                )
            for req_field in ("curious_query", "tension_query", "ambience_query"):
                val = cfg.get(req_field)
                if not isinstance(val, str) or not val.strip():
                    raise ValueError(
                        f"audio_themes.json theme {theme_name!r} missing non-empty {req_field!r}"
                    )
            if "ambience_gain_db" in cfg:
                gain = cfg["ambience_gain_db"]
                is_finite_num = (
                    isinstance(gain, (int, float))
                    and not isinstance(gain, bool)
                    and float("-inf") < float(gain) < float("inf")
                )
                if not is_finite_num:
                    raise ValueError(
                        f"audio_themes.json theme {theme_name!r} has invalid ambience_gain_db"
                    )
            if "foley" in cfg:
                foley = cfg["foley"]
                if not isinstance(foley, dict):
                    raise ValueError(
                        f"audio_themes.json theme {theme_name!r} foley must be a JSON object"
                    )
                for foley_key, foley_spec in foley.items():
                    valid_entry = (
                        isinstance(foley_spec, list)
                        and len(foley_spec) == 4
                        and isinstance(foley_spec[0], str)
                        and bool(foley_spec[0].strip())
                        and all(
                            isinstance(x, (int, float))
                            and not isinstance(x, bool)
                            and float("-inf") < float(x) < float("inf")
                            for x in foley_spec[1:]
                        )
                    )
                    if not valid_entry:
                        raise ValueError(
                            f"audio_themes.json theme {theme_name!r} foley[{foley_key!r}] "
                            "must be [query, gain_db, trim_s, fade_out_s]"
                        )
        validated["audio_themes"] = (
            str(audio_themes_path.relative_to(root))
            if audio_themes_path.is_relative_to(root)
            else str(audio_themes_path)
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
