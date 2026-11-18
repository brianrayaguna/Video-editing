"""Safe `.env` loading and secret-masked file updates without echoing values."""

from __future__ import annotations

import os
from pathlib import Path


def _parse_dotenv_lines(content: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        if key:
            parsed[key] = val
    return parsed


def load_dotenv_safe(repo_root: Path | None = None) -> list[Path]:
    """Load missing environment variables from `<repo_root>/.env` and `~/.env`.

    Existing process environment variables take precedence and are never overwritten.
    """
    candidates: list[Path] = []
    if repo_root is not None:
        candidates.append(repo_root / ".env")
    candidates.append(Path.home() / ".env")

    loaded: list[Path] = []
    for path in candidates:
        if not path.is_file():
            continue
        entries = _parse_dotenv_lines(path.read_text(encoding="utf-8"))
        for key, val in entries.items():
            if val and key not in os.environ:
                os.environ[key] = val
        loaded.append(path)
    return loaded


def upsert_env_var(env_path: Path, key: str, value: str) -> None:
    """Insert or update a single variable in an env file with `0600` permissions."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"Cannot store an empty value for {key}.")

    lines: list[str] = []
    if env_path.is_file():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    replaced = False
    updated_lines: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith(f"{key}=") or stripped.startswith(f"export {key}="):
            updated_lines.append(f'{key}="{cleaned}"')
            replaced = True
        else:
            updated_lines.append(raw)

    if not replaced:
        updated_lines.append(f'{key}="{cleaned}"')

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)
    os.environ[key] = cleaned
