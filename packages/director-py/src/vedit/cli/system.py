"""Schema, platform preset, and provider registry inspection commands."""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
from typing import Annotated

import typer

from vedit.cli._app import JsonOption
from vedit.contracts import (
    find_repo_root,
    load_platform_targets,
    load_schema,
    validate_all_brand_trees,
)
from vedit.providers.config import load_providers_config
from vedit.providers.env import upsert_env_var
from vedit.providers.registry import build_default_registry
from vedit.providers.veed_oauth import has_openedit_oauth_login, resolve_openedit_token_path

contracts_app = typer.Typer(help="Validate JSON Schemas and platform mastering presets.")
platforms_app = typer.Typer(help="List validated platform mastering targets.")
providers_app = typer.Typer(help="Inspect and configure capability providers.")


@contracts_app.command("validate")
def contracts_validate(
    json_output: JsonOption = False,
    repo_root: Annotated[Path | None, typer.Option("--repo-root", hidden=True)] = None,
) -> None:
    """Validate contracts, platform presets, and brand trees under `profiles/`."""
    root = repo_root or find_repo_root()
    schema_files = sorted((root / "contracts").glob("*.schema.json"))
    loaded_schemas: list[str] = []
    for schema_path in schema_files:
        load_schema(schema_path.name, repo_root=root)
        loaded_schemas.append(schema_path.name)

    platforms = load_platform_targets(repo_root=root)
    brands = validate_all_brand_trees(repo_root=root)
    result = {
        "ok": True,
        "schemas": loaded_schemas,
        "platforms_validated": sorted(platforms.keys()),
        "brands_validated": [entry["brand_id"] for entry in brands],
        "brand_trees": brands,
    }
    if json_output:
        typer.echo(json.dumps(result, indent=2))
    else:
        typer.echo(
            f"Validated {len(loaded_schemas)} schemas, {len(platforms)} platform targets, "
            f"and {len(brands)} brand tree(s)."
        )


@platforms_app.command("list")
def platforms_list(json_output: JsonOption = False) -> None:
    """List available platform mastering presets."""
    platforms = load_platform_targets()
    if json_output:
        typer.echo(json.dumps(platforms, indent=2))
        return
    for pid, spec in platforms.items():
        typer.echo(
            f"{pid}: {spec['width']}x{spec['height']}@{spec['fps']}fps "
            f"({spec['aspect_ratio']}, {spec['audio']['target_lufs']} LUFS)"
        )


@providers_app.command("list")
def providers_list(json_output: JsonOption = False) -> None:
    """Inspect configured capability providers and credential readiness (no secrets shown)."""
    registry = build_default_registry()
    report = registry.status_report()
    if json_output:
        typer.echo(json.dumps(report, indent=2))
        return
    for capability, info in report.items():
        cred_state = "credentials=SET" if info["credentials_present"] else "credentials=MISSING"
        typer.echo(
            f"{capability}: primary={info['configured_primary']} "
            f"(auth={info['auth_type']}, {cred_state})"
        )


@providers_app.command("auth")
def providers_auth(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", help="Target .env path (defaults to repo root .env)."),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", help="Re-prompt even for keys already present."),
    ] = False,
) -> None:
    """Interactively configure missing API keys and report OpenEdit OAuth login state."""
    root = find_repo_root()
    cfg = load_providers_config(repo_root=root)
    target_env = env_file or (root / ".env")

    typer.echo(f"Credential store target: {target_env} (input is hidden; press Enter to skip)")
    seen_envs: set[str] = set()
    for capability, cap_cfg in cfg.defaults.items():
        if cap_cfg.auth_type == "openedit_oauth":
            token_path = resolve_openedit_token_path()
            if has_openedit_oauth_login():
                typer.echo(
                    f"  {capability} ({cap_cfg.primary}): OpenEdit OAuth READY ({token_path})"
                )
            else:
                typer.echo(
                    f"  {capability} ({cap_cfg.primary}): OpenEdit OAuth MISSING. "
                    "Run `npx @veedstudio/openedit-cli login` to authenticate in browser."
                )
            continue

        if cap_cfg.auth_type == "local":
            typer.echo(f"  {capability} ({cap_cfg.primary}): local binary (no credentials needed)")
            continue

        env_name = cap_cfg.options.get("api_key_env")
        if not isinstance(env_name, str) or not env_name or env_name in seen_envs:
            continue
        seen_envs.add(env_name)

        already_set = bool(os.environ.get(env_name))
        if already_set and not overwrite:
            typer.echo(f"  {env_name} ({capability}): already SET (skipped)")
            continue
        entered = getpass.getpass(f"  Enter {env_name} for {capability}: ")
        if entered.strip():
            upsert_env_var(target_env, env_name, entered)
            typer.echo(f"  {env_name}: SAVED (0600)")
        else:
            typer.echo(f"  {env_name}: SKIPPED")
