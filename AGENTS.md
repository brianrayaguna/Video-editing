# Repository Agent Instructions

All automated pipelines and AI directing clients operating in this repository must follow the permanent standards in:
- [`.agents/rules/engineering-standards.md`](.agents/rules/engineering-standards.md)
- [`.agents/rules/editing-system.md`](.agents/rules/editing-system.md) — includes MapLibre A-roll bake contract (§4b)
- [`DESIGN.md`](DESIGN.md) — Engine-wide composition and motion rules. Brand craft lives under `profiles/brands/<brand_id>/` (Geoverum: `CRAFT.md`).
- [`profiles/README.md`](profiles/README.md) — `platforms/` vs `brands/` separation.
- [`.agents/skills/brand-director/SKILL.md`](.agents/skills/brand-director/SKILL.md)
- [`tools/geo-assets/README.md`](tools/geo-assets/README.md) — Before any MapLibre / basemap / shot-bed bake, read this. Prefer production-proven knobs from `render_sulawesi_shots.mjs`; Modal does not bake satellite A-roll.
- [`studies/geoverum/MODAL_PRODUCTION_WORKFLOW.md`](studies/geoverum/MODAL_PRODUCTION_WORKFLOW.md) — EditPlan → compile → Modal → audit spine for Geoverum shippable masters.

Quick verification commands after any change:
- Rust probe: `cd packages/media-probe-rs && cargo test && cargo build --release`
- Python director: `packages/director-py/.venv/bin/ruff check packages/director-py && packages/director-py/.venv/bin/pytest -v packages/director-py/tests`
- Contracts & presets: `packages/director-py/.venv/bin/vedit contracts validate --json`
- TypeScript compiler bridge: `cd packages/hf-compiler-ts && npm run typecheck && npm run build`
