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
