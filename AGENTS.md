# Repository Agent Instructions

All automated pipelines and AI directing clients operating in this repository must follow the permanent standards in:
- [`.agents/rules/editing-system.md`](.agents/rules/editing-system.md)
- [`DESIGN.md`](DESIGN.md) — Engine-wide composition, motion, and repository boundary rules. Brand craft lives under `profiles/brands/<brand_id>/`.
- [`profiles/README.md`](profiles/README.md) — `platforms/` vs `brands/` separation.
- [`docs/PROJECT_WORKSPACE.md`](docs/PROJECT_WORKSPACE.md) — External project directory contract (`VEDIT_PROJECTS_ROOT`). Never create active editing project directories inside this engine repository.
- [`docs/CLOUD_WORKFLOW.md`](docs/CLOUD_WORKFLOW.md) — End-to-end `EditPlan` -> compile -> Modal -> audit cloud production workflow.
- [`.agents/skills/brand-director/SKILL.md`](.agents/skills/brand-director/SKILL.md)
- [`.agents/skills/brand-profiling/SKILL.md`](.agents/skills/brand-profiling/SKILL.md)
- [`tools/geo-assets/README.md`](tools/geo-assets/README.md) — Offline geospatial tile grading and MapLibre basemap capture contract.

## Repository Engineering Standards

- **Timeless, neutral technical English**: Write all repository artifacts for an external engineer reading cold—use domain-based naming (`ref_<topic>`), neutral technical terms (keep open-data credits in provenance sections only), and zero local paths or session/batch counters.
- **Decoupled providers**: Route external providers strictly through `vedit.ports` and `ProviderRegistry`; core modules never import vendor modules directly.
- **Strict typing & modular code**: Keep modules small and strictly typed (Pydantic v2 + Draft 2020-12 JSON Schema in Python, strict ESM TypeScript, zero-unsafe pure Rust).
- **Pre-completion audit**: Audit modified files for leaked session history, third-party brand names, and local paths alongside the verification commands below.

## Autonomous Production Protocol (Zero-CLI User Experience)

When a user asks to produce, edit, or render a new video episode in natural language (supplying a topic, script, voiceover, or raw clips):
1. **Execute autonomously without handing off CLI commands**: Never instruct the user to run `vedit` terminal commands manually for routine production steps (`project init`, `clean-audio`, `transcribe`, `probe`, `director verify`, `compile --lint`, `project validate`, `cloud render`, `audit`). Run every command automatically on the user's behalf.
2. **Auto-initialize external workspaces**: Derive a concise domain-based `project_id` slug from the episode topic, select sensible defaults (`brand_id: geoverum`, `9:16 -> shorts_9x16_1080p`, `16:9 -> youtube_16x9_1080p`) unless specified otherwise, immediately run `packages/director-py/.venv/bin/vedit project init <slug> --brand <brand_id> --platform <platform_id> --json` outside the engine repository (`VEDIT_PROJECTS_ROOT`), stage raw inputs under `inputs/`, and record `brief.md`.
3. **Direct with or without a director**: Build `plan/storyboard.json` with `vedit storyboard auto` from the transcript (`--decision auto` automatically uses `DecisionPort` when configured, layering any direction the user gave via `--director-file`), refine it until `vedit storyboard check` passes, prepare full-zoom satellite tiles via `vedit geo prepare` (`GeoImageryPort` `google_tiles` primary with `open_imagery` fallback), generate standardized boxless bottom-band captions via `vedit geo build-captions` (never tiny top-aligned captions), mix voiceover + ducked documentary BGM + scene-synced kinetic SFX via `vedit geo mix-audio`, pass `vedit geo validate-scene` (rejecting plaques, black bar-chart screens, micro-text, and blurry close-ups), and inspect a 12-frame visual contact sheet via `read_file` alongside `vedit critique packet` → `vedit critique gate` before delivering the final render.
4. **Ask only for creative inputs or approvals**: Pause for user input only when required creative source material (topic/script/audio) or target aspect ratio is genuinely missing, or when presenting a storyboard/plan or visual preview for creative sign-off. Deliver final outputs directly (`output/master.mp4` and `output/audit.json`).

## Quick Verification Commands

- Rust probe: `cd packages/media-probe-rs && cargo test && cargo build --release`
- Python director & cloud workers: `packages/director-py/.venv/bin/ruff check packages/director-py packages/cloud-modal && packages/director-py/.venv/bin/pytest -v packages/director-py/tests`
- Contracts & presets: `packages/director-py/.venv/bin/vedit contracts validate --json`
- TypeScript compiler bridge: `cd packages/hf-compiler-ts && npm run typecheck && npm run build && npm test`
- Geo tile server: `node --test tools/geo-assets/serve_tiles.test.mjs`
