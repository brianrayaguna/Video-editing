"""Schema, platform preset, and provider registry inspection commands."""

from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from vedit.cli._app import JsonOption, app
from vedit.contracts import (
    find_repo_root,
    load_platform_targets,
    load_schema,
    validate_all_brand_trees,
)
from vedit.providers.config import load_providers_config
from vedit.providers.env import upsert_env_var
from vedit.providers.registry import build_default_registry

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
            token_path = cap_cfg.oauth_token_path()
            if cap_cfg.has_credentials():
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


def _find_executable_chrome() -> str | None:
    env_chrome = os.environ.get("CHROME", "").strip()
    if env_chrome and os.access(env_chrome, os.X_OK):
        return env_chrome
    cache_root = Path.home() / ".cache" / "puppeteer" / "chrome-headless-shell"
    try:
        if cache_root.is_dir():
            for cand in sorted(cache_root.rglob("chrome-headless-shell"), reverse=True):
                if cand.is_file() and os.access(cand, os.X_OK):
                    return str(cand)
    except OSError:
        pass
    for system_cand in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
    ):
        if Path(system_cand).is_file() and os.access(system_cand, os.X_OK):
            return system_cand
    return None


@app.command("doctor", rich_help_panel="System & registry")
def doctor_cmd(json_output: JsonOption = False) -> None:
    """Verify local runtime dependencies, FFmpeg filters, Chrome, probe binary, and providers."""
    root = find_repo_root()
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    node_bin = shutil.which("node")
    probe_bin = root / "packages" / "media-probe-rs" / "target" / "release" / "vedit-probe"
    hf_cli = root / "packages" / "hf-compiler-ts" / "dist" / "cli.js"
    rea_bin = root / "tools" / "rea-video" / ".venv" / "bin" / "rea-video"
    chrome_bin = _find_executable_chrome()

    filters_out = ""
    if ffmpeg_bin:
        proc = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-filters"],
            capture_output=True,
            text=True,
            check=False,
        )
        filters_out = proc.stdout or ""

    required_filters = ("scdet", "ebur128", "silencedetect", "blackdetect", "freezedetect", "xfade")
    filter_status = {name: (name in filters_out) for name in required_filters}
    filter_status["libvmaf"] = "libvmaf" in filters_out
    filter_status["ssim"] = "ssim" in filters_out
    filter_status["psnr"] = "psnr" in filters_out

    registry = build_default_registry()
    providers_report = registry.status_report()

    checks = {
        "ffmpeg": bool(ffmpeg_bin),
        "ffprobe": bool(ffprobe_bin),
        "node": bool(node_bin),
        "vedit_probe_release": probe_bin.is_file() and os.access(probe_bin, os.X_OK),
        "hf_compiler_built": hf_cli.is_file(),
        "chrome_executable": chrome_bin is not None,
        "rea_video_installed": rea_bin.is_file() or shutil.which("rea-video") is not None,
    }
    report = {
        "ok": all(
            checks[k]
            for k in ("ffmpeg", "ffprobe", "node", "vedit_probe_release", "hf_compiler_built")
        )
        and all(filter_status[f] for f in required_filters),
        "checks": checks,
        "chrome_path": chrome_bin,
        "ffmpeg_filters": filter_status,
        "providers": providers_report,
    }
    if json_output:
        typer.echo(json.dumps(report, indent=2))
        return
    status = "OK" if report["ok"] else "DEGRADED"
    typer.echo(f"vedit doctor: {status}")
    for key, val in checks.items():
        typer.echo(f"  {key:<22} {'READY' if val else 'MISSING'}")
    missing_filters = [k for k in required_filters if not filter_status[k]]
    if missing_filters:
        typer.echo(f"  missing FFmpeg filters: {', '.join(missing_filters)}")
    typer.echo(
        f"  reference metrics:     libvmaf={'yes' if filter_status['libvmaf'] else 'no'}, "
        f"ssim={'yes' if filter_status['ssim'] else 'no'}, "
        f"psnr={'yes' if filter_status['psnr'] else 'no'}"
    )
