# Repository Agent Instructions

All automated pipelines and AI directing clients operating in this repository must follow the permanent standards in:
- [`.agents/rules/engineering-standards.md`](.agents/rules/engineering-standards.md)
- [`.agents/rules/editing-system.md`](.agents/rules/editing-system.md)
- [`DESIGN.md`](DESIGN.md) — Engine-wide composition, motion, and repository boundary rules. Brand craft lives under `profiles/brands/<brand_id>/`.
- [`profiles/README.md`](profiles/README.md) — `platforms/` vs `brands/` separation.
- [`docs/PROJECT_WORKSPACE.md`](docs/PROJECT_WORKSPACE.md) — External project directory contract (`VEDIT_PROJECTS_ROOT`). Never create active editing project directories inside this engine repository.
- [`docs/CLOUD_WORKFLOW.md`](docs/CLOUD_WORKFLOW.md) — End-to-end `EditPlan` -> compile -> Modal -> audit cloud production workflow.
- [`.agents/skills/brand-director/SKILL.md`](.agents/skills/brand-director/SKILL.md)
- [`.agents/skills/brand-profiling/SKILL.md`](.agents/skills/brand-profiling/SKILL.md)
- [`tools/geo-assets/README.md`](tools/geo-assets/README.md) — Offline geospatial tile grading and MapLibre basemap capture contract.

Quick verification commands after any change:
- Rust probe: `cd packages/media-probe-rs && cargo test && cargo build --release`
- Python director & cloud workers: `packages/director-py/.venv/bin/ruff check packages/director-py packages/cloud-modal && packages/director-py/.venv/bin/pytest -v packages/director-py/tests`
- Contracts & presets: `packages/director-py/.venv/bin/vedit contracts validate --json`
- TypeScript compiler bridge: `cd packages/hf-compiler-ts && npm run typecheck && npm run build && npm test`
