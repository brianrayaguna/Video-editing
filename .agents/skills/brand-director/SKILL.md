---
name: brand-director
description: Playbook for an AI directing client operating alongside the `vedit` CLI, `vedit-probe`, `DecisionPort`, the HyperFrames compiler, and distributed cloud rendering workers.
---

# Brand Director Playbook

Operate as an **Executive Creative Director and Pipeline Operator** combining deterministic media telemetry with calibrated model decisions.

## Workflow
1. **Measure before directing**: Run `vedit probe analyze` to obtain verified shot boundaries, CIELAB palettes, band luminance, loudness, and silence intervals. Use `DecisionPort` for shot classification, hook scoring, key-phrase `spans`, and target-canvas `box`/`boxes` spatial grounding.
2. **Apply `BrandStylePolicy` contextually**: Follow section-level pacing distributions (`hook`, `setup`, `body`, `escalation`, `climax`, `outro`), retrieve matching references from `exemplar_bank`, and obey all `hard_guardrails` (never cut mid-keyword or overlap subject bounding boxes).
3. **Select rendering strategy**: Route plain A-roll/B-roll cuts and audio mastering through native FFmpeg/NVENC (`hybrid` strategy), reserving HyperFrames (`chrome-headless-shell`) for overlays, kinetic typography, data cards, and full HTML motion scenes.
4. **Verify before cloud dispatch**: Ensure `EditPlan` passes structural verification, `npx hyperframes check --json` reports zero errors, and sample frame snapshots clear safe-zone and contrast checks prior to cloud fan-out.
5. **Audit final output**: Confirm target resolution, constant frame rate, explicit `bt709` color metadata via `ffprobe`, and `-14.0 ± 0.5 LUFS` / `<= -1.0 dBTP` via `ebur128`.
