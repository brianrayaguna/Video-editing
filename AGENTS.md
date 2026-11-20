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

## Permanent Writing & Neutrality Rules (Always On)

Apply these rules unconditionally to every code file, brand profile (`profiles/brands/<brand_id>/*`), schema, test, and Markdown document committed in this repository:
1. **Objective Technical English & Zero Chat Leakage**: Write every repository artifact for an external engineer reading cold. Never include session history, rollout/batch/corpus counters (`Batch 1`, `Batches 1-2`, `Phase 1`, `v2`, `N/20`, `50-video corpus`, `preserved baseline`, `fixed from earlier`), or reactive/defensive wording.
2. **Domain-Based Naming Only**: Name modules, tests, and exemplar IDs strictly after their technical domain or topic (`ref_<topic>`, e.g., `ref_gibraltar_strait`), never sequential download numbers or platform prefixes (`yt_01`). Keep `CRAFT.md`, `README.md`, and `grammar_triggers` standalone without parenthetical video-ID lists.
3. **Zero Third-Party Brand Leakage**: Never embed third-party product/app names, commercial software names, reference channel names, consumer brands, or social platform brand names into permanent brand profiles, rules, or schemas—use neutral technical terminology instead (keep open-data license credits only in designated provenance sections). Never embed user-specific local paths (`/Users/...`).
4. **Mandatory Pre-Completion Audit**: Before claiming work is done, run a hygiene check over modified repository files for leaked batch/chat history, third-party names, and local paths alongside the verification commands below.

## Quick Verification Commands

- Rust probe: `cd packages/media-probe-rs && cargo test && cargo build --release`
- Python director & cloud workers: `packages/director-py/.venv/bin/ruff check packages/director-py packages/cloud-modal && packages/director-py/.venv/bin/pytest -v packages/director-py/tests`
- Contracts & presets: `packages/director-py/.venv/bin/vedit contracts validate --json`
- TypeScript compiler bridge: `cd packages/hf-compiler-ts && npm run typecheck && npm run build && npm test`
