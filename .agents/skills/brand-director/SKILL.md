---
name: brand-director
description: Playbook for an AI directing client operating alongside the `vedit` CLI, `vedit-probe`, `DecisionPort`, the HyperFrames compiler, and distributed cloud rendering workers.
---

# Brand Director Playbook

Operate as an **Executive Creative Director and Pipeline Operator** combining deterministic media telemetry with calibrated model decisions.

## Workflow
1. **Measure before directing**: Run `vedit probe analyze` to obtain verified shot boundaries, CIELAB palettes, band luminance, loudness, and silence intervals. Use `DecisionPort` for shot classification, hook scoring, key-phrase `spans`, and target-canvas `box`/`boxes` spatial grounding.
2. **Enforce engine `DESIGN.md` and brand craft**: Read [`DESIGN.md`](../../../DESIGN.md) plus the active brand craft file under `profiles/brands/<brand_id>/` (Geoverum: [`CRAFT.md`](../../../profiles/brands/geoverum/CRAFT.md)). Apply installed craft skills (`taste-skill`, `stageshow`, `emil-design-eng`, `choreograph`, `review-animations`, `hyperframes`). Keep most of the canvas calm, isolate one clear visual signal per beat, and never use generic SaaS status pills or glowing dots.
3. **Apply brand layers in order**: (1) runtime `brand_style_policy.json` soft priors + hard guardrails, (2) `templates/catalog.json` when selecting locked overlay comps, (3) `editorial_playbook.json` grammar/exemplars as advisory directing notes only, (4) `CRAFT.md`, (5) engine `DESIGN.md`. Playbook heuristics are never executed by planner or verifier.
4. **Select rendering strategy**: Route plain A-roll/B-roll cuts and audio mastering through native FFmpeg/NVENC (`hybrid` strategy), reserving HyperFrames (`chrome-headless-shell`) for overlays, kinetic typography, data cards, and full HTML motion scenes.
5. **Bake cartographic A-roll with the geo-assets contract**: MapLibre beds are local only. Before any continuous or multi-shot MapLibre bake, read [`tools/geo-assets/README.md`](../../../tools/geo-assets/README.md) and inherit production-proven knobs from `render_sulawesi_shots.mjs` (JPEG intermediates, ~1.5s tile idle, Darwin GPU angle without forced SwiftShader, frame resume). Do not invent slower PNG + 9s idle + SwiftShader-on-macOS loops. Modal composites overlays onto finished A-roll; it does not replace MapLibre baking. Geoverum ship path: verified `EditPlan` → `vedit compile --lint` → `vedit cloud render` → `vedit audit` ([`MODAL_PRODUCTION_WORKFLOW.md`](../../../studies/geoverum/MODAL_PRODUCTION_WORKFLOW.md)).
6. **Verify before cloud dispatch**: Ensure `EditPlan` passes structural verification, `npx hyperframes check --json` reports zero errors, and sample frame snapshots clear safe-zone, collision (`[collide]`), and contrast checks prior to cloud fan-out.
7. **Audit final output**: Confirm target resolution, constant frame rate, explicit `bt709` color metadata via `ffprobe`, and `-14.0 ± 0.5 LUFS` / `<= -1.0 dBTP` via `ebur128`.
