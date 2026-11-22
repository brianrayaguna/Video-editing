"""External project workspace lifecycle, validation, and relative asset resolution."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vedit.contracts import (
    find_repo_root,
    load_platform_targets,
    validate_against_contract,
    validate_brand_tree,
)
from vedit.models import (
    EditPlan,
    ProjectArtifacts,
    ProjectDirectories,
    ProjectManifest,
)

PROJECTS_ROOT_ENV = "VEDIT_PROJECTS_ROOT"
MANIFEST_FILENAME = "project.json"

_ABSOLUTE_PATH_RE = re.compile(
    r"^(?:/Users/|/home/|/var/|/private/|/opt/|/mnt/|/tmp/|/Volumes/|/etc/|/usr/|/root/|/data/|/app/|~/|[A-Za-z]:[/\\])"
)
_SLUG_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


@dataclass(slots=True)
class ProjectWorkspaceInfo:
    project_dir: Path
    manifest_path: Path
    brief_path: Path
    manifest: ProjectManifest
    created_directories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_dir": str(self.project_dir),
            "manifest_path": str(self.manifest_path),
            "brief_path": str(self.brief_path),
            "manifest": self.manifest.model_dump(exclude_none=True),
            "created_directories": list(self.created_directories),
        }


@dataclass(slots=True)
class ProjectStatusReport:
    project_dir: Path
    project_id: str
    brand_id: str
    platform_target_id: str
    stages: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_dir": str(self.project_dir),
            "project_id": self.project_id,
            "brand_id": self.brand_id,
            "platform_target_id": self.platform_target_id,
            "stages": dict(self.stages),
        }


@dataclass(slots=True)
class ProjectValidationIssue:
    severity: str
    code: str
    message: str
    path: str | None = None


@dataclass(slots=True)
class ProjectValidationReport:
    passed: bool
    project_dir: Path
    errors: list[ProjectValidationIssue] = field(default_factory=list)
    warnings: list[ProjectValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "project_dir": str(self.project_dir),
            "errors": [asdict(err) for err in self.errors],
            "warnings": [asdict(warn) for warn in self.warnings],
        }


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve_projects_root(
    projects_root: Path | None = None,
    *,
    repo_root: Path | None = None,
    allow_in_repo: bool = False,
) -> Path:
    """Resolve the external root directory where editing projects live.

    Resolution order:
    1. Explicit `projects_root` argument
    2. `VEDIT_PROJECTS_ROOT` environment variable
    3. Sibling directory outside the engine repository (`<repo_root.parent>/<repo_name>-Projects`)
    """
    engine_root = (repo_root or find_repo_root()).resolve()
    if projects_root is not None:
        resolved = projects_root.expanduser().resolve()
    else:
        env_val = os.environ.get(PROJECTS_ROOT_ENV, "").strip()
        if env_val:
            resolved = Path(env_val).expanduser().resolve()
        else:
            resolved = (engine_root.parent / f"{engine_root.name}-Projects").resolve()

    if not allow_in_repo and _is_within(resolved, engine_root):
        raise ValueError(
            f"External projects root must reside outside the engine repository "
            f"({engine_root}); received {resolved}. Set {PROJECTS_ROOT_ENV} or pass "
            "--projects-root pointing to an external directory."
        )
    return resolved


def find_project_root(start: Path | None = None) -> Path | None:
    """Locate an enclosing project directory containing `project.json`."""
    cursor = (start or Path.cwd()).resolve()
    if cursor.is_file():
        cursor = cursor.parent
    for candidate in (cursor, *cursor.parents):
        if (candidate / MANIFEST_FILENAME).is_file():
            return candidate
    return None


def _default_brief_markdown(manifest: ProjectManifest) -> str:
    heading = manifest.title or manifest.project_id
    return (
        f"# {heading}\n\n"
        f"- **Project ID**: `{manifest.project_id}`\n"
        f"- **Brand**: `{manifest.brand_id}`\n"
        f"- **Platform Target**: `{manifest.platform_target_id}`\n"
        f"- **Created**: `{manifest.created_at}`\n\n"
        "## Editorial Objective\n\n"
        "Describe the narrative thesis, target runtime, and visual signal per beat.\n\n"
        "## Narration & Beat Outline\n\n"
        "1. Hook\n"
        "2. Setup\n"
        "3. Body\n"
        "4. Escalation & Climax\n"
        "5. Outro\n"
    )


def init_project_workspace(
    project_id: str,
    brand_id: str,
    platform_target_id: str,
    *,
    projects_root: Path | None = None,
    project_dir: Path | None = None,
    title: str | None = None,
    notes: str | None = None,
    repo_root: Path | None = None,
    allow_in_repo: bool = False,
    overwrite: bool = False,
) -> ProjectWorkspaceInfo:
    """Create a structured, self-contained editing project outside the engine repository."""
    engine_root = (repo_root or find_repo_root()).resolve()

    if not _SLUG_ID_RE.match(project_id):
        raise ValueError(f"Invalid project_id {project_id!r}; must match {_SLUG_ID_RE.pattern}")
    if not _SLUG_ID_RE.match(brand_id):
        raise ValueError(f"Invalid brand_id {brand_id!r}; must match {_SLUG_ID_RE.pattern}")

    platforms = load_platform_targets(repo_root=engine_root)
    if platform_target_id not in platforms:
        raise ValueError(
            f"Unknown platform_target_id {platform_target_id!r}. "
            f"Available: {sorted(platforms.keys())}"
        )

    brand_dir = engine_root / "profiles" / "brands" / brand_id
    if brand_dir.is_dir():
        validate_brand_tree(brand_dir, repo_root=engine_root)

    if project_dir is not None:
        target_dir = project_dir.expanduser().resolve()
        if not allow_in_repo and _is_within(target_dir, engine_root):
            raise ValueError(
                f"Project directory must reside outside the engine repository ({engine_root}); "
                f"received {target_dir}."
            )
    else:
        root_dir = resolve_projects_root(
            projects_root,
            repo_root=engine_root,
            allow_in_repo=allow_in_repo,
        )
        target_dir = root_dir / brand_id / project_id

    manifest_path = target_dir / MANIFEST_FILENAME
    if manifest_path.exists() and not overwrite:
        raise FileExistsError(
            f"Project manifest already exists: {manifest_path}. Pass overwrite=True to replace."
        )

    dirs = ProjectDirectories()
    artifacts = ProjectArtifacts()
    manifest = ProjectManifest(
        project_id=project_id,
        brand_id=brand_id,
        platform_target_id=platform_target_id,
        title=title,
        created_at=datetime.now(UTC).isoformat(),
        directories=dirs,
        artifacts=artifacts,
        notes=notes,
    )

    payload = manifest.model_dump(exclude_none=True)
    schema_errors = validate_against_contract(
        payload,
        "project_manifest.schema.json",
        repo_root=engine_root,
    )
    if schema_errors:
        raise ValueError(f"ProjectManifest failed contract validation: {schema_errors}")

    subdirs = [
        dirs.inputs,
        dirs.probes,
        dirs.breakdowns,
        dirs.transcripts,
        dirs.decisions,
        dirs.maps,
        dirs.broll,
        dirs.audio,
        dirs.plan,
        dirs.build,
        f"{dirs.build}/hf_project",
        f"{dirs.build}/hf_sparse_windows",
        f"{dirs.build}/subtitles",
        dirs.output,
    ]
    created: list[str] = []
    target_dir.mkdir(parents=True, exist_ok=True)
    for rel in subdirs:
        (target_dir / rel).mkdir(parents=True, exist_ok=True)
        created.append(rel)

    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    brief_path = target_dir / artifacts.brief
    if not brief_path.exists() or overwrite:
        brief_path.write_text(_default_brief_markdown(manifest), encoding="utf-8")

    return ProjectWorkspaceInfo(
        project_dir=target_dir,
        manifest_path=manifest_path,
        brief_path=brief_path,
        manifest=manifest,
        created_directories=created,
    )


def load_project_manifest(project_dir: Path) -> ProjectManifest:
    """Load and parse `project.json` from a project directory."""
    manifest_path = project_dir.expanduser().resolve() / MANIFEST_FILENAME
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing project manifest: {manifest_path}")
    return ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def _count_files(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(
        1
        for item in directory.rglob("*")
        if item.is_file() and not item.name.startswith(".")
    )


def inspect_project_status(project_dir: Path) -> ProjectStatusReport:
    """Inspect deterministic stage readiness for a structured project directory."""
    resolved_dir = project_dir.expanduser().resolve()
    manifest = load_project_manifest(resolved_dir)
    dirs = manifest.directories
    arts = manifest.artifacts

    edit_plan_path = resolved_dir / arts.edit_plan
    verifier_passed: bool | None = None
    if edit_plan_path.is_file():
        try:
            plan_data = json.loads(edit_plan_path.read_text(encoding="utf-8"))
            verifier_passed = bool(plan_data.get("verifier_passed", False))
        except json.JSONDecodeError:
            verifier_passed = False

    audit_path = resolved_dir / arts.audit
    audit_passed: bool | None = None
    if audit_path.is_file():
        try:
            audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
            audit_passed = bool(audit_data.get("passed", False))
        except json.JSONDecodeError:
            audit_passed = False

    stages: dict[str, dict[str, Any]] = {
        "inputs": {
            "ready": _count_files(resolved_dir / dirs.inputs) > 0,
            "file_count": _count_files(resolved_dir / dirs.inputs),
            "path": dirs.inputs,
        },
        "probes": {
            "ready": _count_files(resolved_dir / dirs.probes) > 0,
            "file_count": _count_files(resolved_dir / dirs.probes),
            "path": dirs.probes,
        },
        "transcripts": {
            "ready": _count_files(resolved_dir / dirs.transcripts) > 0,
            "file_count": _count_files(resolved_dir / dirs.transcripts),
            "path": dirs.transcripts,
        },
        "edit_plan": {
            "ready": edit_plan_path.is_file(),
            "verifier_passed": verifier_passed,
            "path": arts.edit_plan,
        },
        "master": {
            "ready": (resolved_dir / arts.master).is_file(),
            "path": arts.master,
        },
        "audit": {
            "ready": audit_path.is_file(),
            "passed": audit_passed,
            "path": arts.audit,
        },
        "otio": {
            "ready": (resolved_dir / arts.otio).is_file(),
            "path": arts.otio,
        },
    }
    return ProjectStatusReport(
        project_dir=resolved_dir,
        project_id=manifest.project_id,
        brand_id=manifest.brand_id,
        platform_target_id=manifest.platform_target_id,
        stages=stages,
    )


def _scan_json_for_absolute_paths(
    obj: Any,
    *,
    json_path: str = "$",
) -> list[tuple[str, str]]:
    """Return `(json_path, value)` pairs for any leaked local absolute filesystem paths."""
    leaks: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            leaks.extend(_scan_json_for_absolute_paths(val, json_path=f"{json_path}.{key}"))
    elif isinstance(obj, list):
        for idx, val in enumerate(obj):
            leaks.extend(_scan_json_for_absolute_paths(val, json_path=f"{json_path}[{idx}]"))
    elif isinstance(obj, str) and _ABSOLUTE_PATH_RE.match(obj.strip()):
        leaks.append((json_path, obj.strip()))
    return leaks


def validate_project_workspace(
    project_dir: Path,
    *,
    repo_root: Path | None = None,
    allow_in_repo: bool = False,
) -> ProjectValidationReport:
    """Validate project manifest contract, brand/platform references, and relative path hygiene."""
    resolved_dir = project_dir.expanduser().resolve()
    engine_root = (repo_root or find_repo_root()).resolve()
    errors: list[ProjectValidationIssue] = []
    warnings: list[ProjectValidationIssue] = []

    if not allow_in_repo and _is_within(resolved_dir, engine_root):
        errors.append(
            ProjectValidationIssue(
                severity="error",
                code="PROJECT_INSIDE_ENGINE_REPO",
                message=(
                    f"Project directory {resolved_dir} resides inside the engine repository "
                    f"({engine_root}). Store projects under {PROJECTS_ROOT_ENV}."
                ),
            )
        )

    manifest_path = resolved_dir / MANIFEST_FILENAME
    if not manifest_path.is_file():
        errors.append(
            ProjectValidationIssue(
                severity="error",
                code="MISSING_PROJECT_MANIFEST",
                message=f"Missing {MANIFEST_FILENAME} in {resolved_dir}.",
                path=MANIFEST_FILENAME,
            )
        )
        return ProjectValidationReport(passed=False, project_dir=resolved_dir, errors=errors)

    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(
            ProjectValidationIssue(
                severity="error",
                code="INVALID_MANIFEST_JSON",
                message=f"Failed to parse {MANIFEST_FILENAME}: {exc}",
                path=MANIFEST_FILENAME,
            )
        )
        return ProjectValidationReport(passed=False, project_dir=resolved_dir, errors=errors)

    schema_errs = validate_against_contract(
        raw_manifest,
        "project_manifest.schema.json",
        repo_root=engine_root,
    )
    for err in schema_errs:
        errors.append(
            ProjectValidationIssue(
                severity="error",
                code="MANIFEST_SCHEMA_INVALID",
                message=err,
                path=MANIFEST_FILENAME,
            )
        )
    if schema_errs:
        return ProjectValidationReport(passed=False, project_dir=resolved_dir, errors=errors)

    manifest = ProjectManifest.model_validate(raw_manifest)
    platforms = load_platform_targets(repo_root=engine_root)
    if manifest.platform_target_id not in platforms:
        errors.append(
            ProjectValidationIssue(
                severity="error",
                code="UNKNOWN_PLATFORM_TARGET",
                message=f"Platform target {manifest.platform_target_id!r} not found in profiles.",
                path=MANIFEST_FILENAME,
            )
        )

    brand_dir = engine_root / "profiles" / "brands" / manifest.brand_id
    if brand_dir.is_dir():
        try:
            validate_brand_tree(brand_dir, repo_root=engine_root)
        except Exception as exc:
            errors.append(
                ProjectValidationIssue(
                    severity="error",
                    code="INVALID_BRAND_PROFILE",
                    message=str(exc),
                    path=f"profiles/brands/{manifest.brand_id}",
                )
            )
    else:
        warnings.append(
            ProjectValidationIssue(
                severity="warning",
                code="BRAND_PROFILE_EXTERNAL",
                message=(
                    f"Brand {manifest.brand_id!r} is not under engine profiles/brands/; "
                    "pass --brand-dir explicitly when planning or verifying."
                ),
            )
        )

    for rel_dir in manifest.directories.model_dump().values():
        if not (resolved_dir / rel_dir).is_dir():
            warnings.append(
                ProjectValidationIssue(
                    severity="warning",
                    code="MISSING_STANDARD_DIRECTORY",
                    message=f"Expected project directory missing: {rel_dir}",
                    path=rel_dir,
                )
            )

    for rel_json in (
        MANIFEST_FILENAME,
        manifest.artifacts.edit_plan,
        manifest.artifacts.benchmark,
    ):
        target_json = resolved_dir / rel_json
        if not target_json.is_file():
            continue
        try:
            data = json.loads(target_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(
                ProjectValidationIssue(
                    severity="error",
                    code="INVALID_ARTIFACT_JSON",
                    message=f"Failed to parse {rel_json}: {exc}",
                    path=rel_json,
                )
            )
            continue
        for jpath, leaked in _scan_json_for_absolute_paths(data):
            errors.append(
                ProjectValidationIssue(
                    severity="error",
                    code="ABSOLUTE_PATH_LEAK",
                    message=f"{rel_json} ({jpath}) embeds local absolute path: {leaked}",
                    path=rel_json,
                )
            )

    return ProjectValidationReport(
        passed=len(errors) == 0,
        project_dir=resolved_dir,
        errors=errors,
        warnings=warnings,
    )


def resolve_plan_asset_paths(
    plan: EditPlan,
    *,
    base_dir: Path,
    repo_root: Path | None = None,
) -> EditPlan:
    """Resolve relative `AssetRef.path` entries against project, plan, or engine root.

    Preserves URLs (`http://`, `https://`), already-absolute existing paths, and unresolved paths
    so downstream validators produce clear diagnostics.
    """
    resolved_base = base_dir.expanduser().resolve()
    if resolved_base.is_file():
        resolved_base = resolved_base.parent

    project_root = find_project_root(resolved_base)
    engine_root: Path | None = None
    try:
        engine_root = (repo_root or find_repo_root()).resolve()
    except FileNotFoundError:
        engine_root = None

    search_roots: list[Path] = []
    for candidate in (project_root, resolved_base, engine_root):
        if candidate is not None and candidate not in search_roots:
            search_roots.append(candidate)

    rewritten = []
    for asset in plan.assets:
        raw_path = asset.path.strip()
        if not raw_path or _URL_SCHEME_RE.match(raw_path):
            rewritten.append(asset)
            continue

        p = Path(raw_path)
        if p.is_absolute():
            rewritten.append(asset)
            continue

        resolved_hit: Path | None = None
        for root in search_roots:
            root_resolved = root.resolve()
            cand = (root_resolved / p).resolve()
            if _is_within(cand, root_resolved) and cand.exists():
                resolved_hit = cand
                break

        if resolved_hit is not None:
            rewritten.append(asset.model_copy(update={"path": str(resolved_hit)}))
        else:
            rewritten.append(asset)

    return plan.model_copy(update={"assets": rewritten})
