# Repository Agent Instructions

All automated pipelines and AI directing clients operating in this repository must follow the permanent standards in:
- [`.agents/rules/engineering-standards.md`](.agents/rules/engineering-standards.md)
- [`.agents/rules/editing-system.md`](.agents/rules/editing-system.md)
- [`.agents/skills/brand-director/SKILL.md`](.agents/skills/brand-director/SKILL.md)

Quick verification commands after any change:
- Rust probe: `cd packages/media-probe-rs && cargo test && cargo build --release`
- Python director: `packages/director-py/.venv/bin/ruff check packages/director-py && packages/director-py/.venv/bin/pytest -v packages/director-py/tests`
- Contracts & presets: `packages/director-py/.venv/bin/vedit contracts validate --json`
- TypeScript compiler bridge: `cd packages/hf-compiler-ts && npm run typecheck && npm run build`
