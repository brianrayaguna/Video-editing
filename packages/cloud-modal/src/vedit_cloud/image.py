"""Modal Linux x86_64 worker container definition compiling vedit-probe & HyperFrames 0.9.65."""

from __future__ import annotations

from pathlib import Path

import modal
from vedit.contracts import find_repo_root

WORKER_CHROMIUM_FLAGS = "--no-browser-gpu --use-gl=swiftshader"
PINNED_CHROME_HEADLESS_VERSION = "152.0.7977.30"

_DEBIAN_PACKAGES = [
    "ffmpeg",
    "ca-certificates",
    "curl",
    "gnupg",
    "unzip",
    "build-essential",
    "pkg-config",
    "libcairo2",
    "libpango-1.0-0",
    "libxshmfence1",
    "libnss3",
    "libatk1.0-0",
    "libatk-bridge2.0-0",
    "libcups2",
    "libdrm2",
    "libxkbcommon0",
    "libxcomposite1",
    "libxdamage1",
    "libxfixes3",
    "libxrandr2",
    "libgbm1",
    "libasound2",
    "fonts-liberation",
    "fonts-noto-color-emoji",
]


def build_worker_image(repo_root: Path | None = None) -> modal.Image:
    """Build the Linux x86_64 worker image without copying macOS host binaries.

    Compiles `vedit-probe` natively from source via Cargo inside the container, builds
    `@vedit/hf-compiler` (`0.9.65`), installs the pinned `chrome-headless-shell` build,
    and stages Python contracts, presets, and workspace packages cleanly.
    """
    root = repo_root or find_repo_root()
    ignore_build_dirs = [
        "target",
        "node_modules",
        "dist",
        ".venv",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "*.egg-info",
    ]

    return (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install(*_DEBIAN_PACKAGES)
        .run_commands(
            "curl -fsSL https://deb.nodesource.com/setup_22.x | bash - "
            "&& apt-get install -y nodejs "
            "&& rm -rf /var/lib/apt/lists/*",
            "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs "
            "| sh -s -- -y --profile minimal",
        )
        .add_local_dir(
            root / "packages" / "media-probe-rs",
            "/opt/vedit/packages/media-probe-rs",
            copy=True,
            ignore=ignore_build_dirs,
        )
        .run_commands(
            "/root/.cargo/bin/cargo build --release --locked "
            "--manifest-path /opt/vedit/packages/media-probe-rs/Cargo.toml",
            "install -m 0755 "
            "/opt/vedit/packages/media-probe-rs/target/release/vedit-probe "
            "/usr/local/bin/vedit-probe",
            "rm -rf /opt/vedit/packages/media-probe-rs/target",
        )
        .add_local_dir(
            root / "packages" / "hf-compiler-ts",
            "/opt/vedit/packages/hf-compiler-ts",
            copy=True,
            ignore=ignore_build_dirs,
        )
        .run_commands(
            "cd /opt/vedit/packages/hf-compiler-ts "
            "&& npm ci "
            "&& npx tsc "
            "&& npm prune --omit=dev "
            "&& npx puppeteer browsers install "
            f"chrome-headless-shell@{PINNED_CHROME_HEADLESS_VERSION} "
            "&& SHELL_BIN=$(find /root/.cache/puppeteer/chrome-headless-shell "
            "-name chrome-headless-shell -type f | head -n 1) "
            '&& test -x "$SHELL_BIN" '
            '&& ! ldd "$SHELL_BIN" | grep -q "not found"',
        )
        .add_local_dir(root / "contracts", "/opt/vedit/contracts", copy=True)
        .add_local_dir(root / "profiles", "/opt/vedit/profiles", copy=True)
        .add_local_dir(
            root / "config",
            "/opt/vedit/config",
            copy=True,
            ignore=["providers.yaml"],
        )
        .add_local_dir(
            root / "packages" / "director-py",
            "/opt/vedit/packages/director-py",
            copy=True,
            ignore=ignore_build_dirs,
        )
        .add_local_dir(
            root / "packages" / "cloud-modal",
            "/opt/vedit/packages/cloud-modal",
            copy=True,
            ignore=ignore_build_dirs,
        )
        .pip_install(
            "hatchling>=1.25.0",
            "pydantic>=2.9.0",
            "jsonschema>=4.23.0",
            "pyyaml>=6.0.2",
            "httpx>=0.27.2",
            "typer>=0.12.5",
        )
        .run_commands(
            "pip install --no-deps --no-build-isolation /opt/vedit/packages/director-py",
            "pip install --no-deps --no-build-isolation /opt/vedit/packages/cloud-modal",
        )
        .env(
            {
                "VEDIT_REPO_ROOT": "/opt/vedit",
                "VEDIT_PROBE_BIN": "/usr/local/bin/vedit-probe",
                "VEDIT_HF_COMPILER_CLI": "/opt/vedit/packages/hf-compiler-ts/dist/cli.js",
                "HYPERFRAMES_CHROMIUM_FLAGS": WORKER_CHROMIUM_FLAGS,
                "HYPERFRAMES_CHROME_SANDBOX": "0",
            }
        )
    )
