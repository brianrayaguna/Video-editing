---
name: brand-director
description: Playbook for an AI directing client operating alongside the `vedit` CLI, `vedit-probe`, `DecisionPort`, the HyperFrames compiler, and distributed cloud rendering workers.
---

# Brand Director Playbook

Operate as an **Executive Creative Director and Pipeline Operator** combining deterministic media telemetry, structured concept divergence, and calibrated model decisions under each brand's **Tight Rails, Open Canvas** profile.

## Workflow

0. **Auto-initialize the external project**: Follow the Autonomous Production Protocol in [`AGENTS.md`](../../../AGENTS.md): derive a topic-based `project_id`, run `vedit project init` under `VEDIT_PROJECTS_ROOT`, stage inputs, write `brief.md`, and execute every downstream stage on the user's behalf. Ask only for missing creative inputs or creative sign-off.
1. **Measure before directing**: Run `vedit probe analyze` on source media to obtain verified shot boundaries, CIELAB palettes, band luminance, loudness, and silence intervals. Use `DecisionPort` for shot classification, hook scoring, key-phrase `spans`, and target-canvas `box`/`boxes` spatial grounding. *(Use [`.agents/skills/brand-profiling/SKILL.md`](../brand-profiling/SKILL.md) **only** when calibrating a brand profile offline from raw reference videos—never during episode production.)*
2. **Stage 0 — Divergent Concept Pitch (*Verbalized Sampling*, before storyboarding)**:
   - Load the brand's progressive-disclosure index (`profiles/brands/<brand_id>/README.md`) and `DIRECTING.md`.
   - Generate **4–5 structurally different episode concepts** for the narration with estimated typicality scores (`p` in `0.0–1.0`), forcing **at least two low-typicality tail concepts (`p < 0.15`)**.
   - Factor each concept independently across **Narrative Strategy × Tone/Register × Episode Visual Anchor & Surface Mix**.
   - Check external `$VEDIT_PROJECTS_ROOT/<brand_id>/brand_memory.json` (`recent_episodes`) so consecutive episodes never repeat hook mechanism + ending type or reuse a signature visual anchor.
   - Commit the single sharpest concept into the Story Brief and authorize **Open Primitives** (episode-scoped custom SVG `map_sprites`, custom full-bleed `cutaway_2d` HTML, or bespoke 2D editorial diagrams) wherever built-in templates would feel stiff—bound strictly by Layer 1 Brand DNA.
3. **Direct the story & clear Gate 1 (`plan/storyboard.json`)**:
   - **Pre-VO readiness**: Run `vedit storyboard readiness <transcript.json> --brand <brand_id> [--strict]` (uses bilingual `readiness_phrases` from `directing_idioms.json`) to catch abstract streaks, filler openings, and compressed beats before locking narration audio.
   - **Draft & retrieve**: Build the baseline via `vedit storyboard auto <transcript.json> -o plan/storyboard.json --project-id <id> --brand <brand_id> [--pacing dense] [--tier standard|flagship] [--decision auto|on|off] [--memory-file <brand_memory.json>] [--director-file director.json]`, and query curated on-demand recipes via `vedit storyboard context plan/storyboard.json --brand <brand_id> -o plan/directing_context.json`.
   - **Refine & verify**: Replace generic fallback beats with concrete `story_need -> visual_answer` rows aligned to the winning Stage 0 concept, then pass `vedit storyboard check` and `vedit storyboard gate-prerender` before spending render compute. For route-driven journeys, compile keys via `vedit storyboard journey`.
4. **Apply brand layers cleanly**:
   - **Layer 1 (Locked Brand DNA)**: `brand_style_policy.json` (single source of truth for palette, typography scale, caption geometry, guardrails) + `CRAFT.md` (surface registers, adaptive ink/glow, upper-center action stage).
   - **Layer 2 (Open Creative Sandbox)**: `DIRECTING.md` + on-demand `editorial_playbook.json` recipes + episode Open Primitives.
   - **Layer 3 (Quality Floor & Assets)**: `directing_idioms.json`, `audio_themes.json`, `templates/catalog.json`, and engine [`DESIGN.md`](../../../DESIGN.md).
5. **Use cloud-first execution (thin local control plane)**: Never install local ASR/STT packages. Route neural speech denoising and reframing through `MediaOpsPort` (`--provider modal_cloud`), and distributed HyperFrames rendering + EBU R128 mastering through `vedit cloud render`.
6. **Isolate active projects outside the engine repository**: Store strictly project-relative paths in `project.json` and `plan/edit_plan.json`, validate with `vedit project validate`, and follow `verified EditPlan -> vedit compile --lint -> vedit cloud render (or vedit master) -> vedit audit` ([`docs/CLOUD_WORKFLOW.md`](../../../docs/CLOUD_WORKFLOW.md)).
7. **Gate 2 Surgical Critique before final render**: On a low-resolution preview, run `vedit critique packet` (idioms, camera shake budget, temporal sync, grid-anchored contact sheets), visually inspect action peaks and transitions via `read_file`, apply typed fixes with `vedit critique apply-fixes`, and pass `vedit critique gate` (`<= 3` rounds).
8. **Audit final master & record external Brand Memory**: Run `vedit audit` (`bt709`, CFR, `-14.0 ± 0.5 LUFS`, `<= -1.0 dBTP`, zero black/frozen frames), then record outcomes into `$VEDIT_PROJECTS_ROOT/<brand_id>/brand_memory.json` via `vedit brand memory record`.

## Cartographic Production Standard (Audio-Only / Map-Driven Episodes)

When producing a `9:16` Geoverum cartographic documentary from narration audio:

1. **Audio & Verbatim Transcription**: If a playback speedup is requested, render sped-up audio first (`ffmpeg -af "atempo=..."`). Use configured cloud `TranscriptionPort` (or inspect a `16 kHz` mono WAV directly via `read_file` when cloud STT is unavailable).
2. **Single-Source Policy Captions (`vedit geo build-captions --brand geoverum`)**:
   - Always generate `build/subtitles/captions.ass` via `vedit geo build-captions <transcript.json> -o build/subtitles/captions.ass --brand geoverum [--speed 1.0]`.
   - Reads single-source tokens from `brand_style_policy.json`: `Inter` Bold **`46 px`** (`9:16`) / **`42 px`** (`16:9`), `#F5F7FA`, `MarginV = 525` (`y ≈ 72.7%` inside `y = 66%–84%`), `110 ms` fade-in, `0 ms` hard cut out, `67 ms` gap, 2–4 words per cue. Composite via the HTML/Chromium strip renderer (`render_captions_overlay.mjs`) with its 4-layer snow-safe soft Gaussian drop shadow—never boxed captions, never top-aligned captions, never ad-hoc `drawtext`.
3. **Full-Zoom Satellite Imagery (`vedit geo prepare`)**:
   - Prepare project AOI tiles via `vedit geo prepare --bbox "W,S,E,N:..." -o media/maps/vectors.json` (`google_tiles` primary with `open_imagery` fallback) and bake with `vedit geo bake-scene --fill-tiles` so zero frames capture upscaled tiles.
4. **Calibrated Surface Registers, Adaptive Ink & Expressive Primitives**:
   - Use rest-to-rest C² camera moves (`glide`, `snap_dive`, `hyperbolic_fly`, `orbit_cruise`), keeping map frames crisp (`optical_shutter_blur: false`) and reserving blur for radial zoom cuts or 6-frame `disc_sweep` register swaps.
   - Choose surface registers per narrative mode (`bathymetric satellite` spine `#0E4352`, `cobalt` blueprint `#2059DC`, matte slate radar, `surface_register: "daylight_terrain"` sunlit 3D mountains, or deep tactical 2D/parchment), adaptive `CARTO_TYPO_PRESETS` (`editorial_title`, `dark_on_fill`, `acronym_hero`, `velocity_cyan`, `underlined_city`, `water_subtle`), full-territory animated waving `flag_fill` (never small floating rectangular flag pins), custom SVG `map_sprites`, full-bleed `cutaway_2d`, and 3D `cable_3d` / `model_3d` / `volume_3d` / `country_block_3d` geometry.
   - Pass `vedit geo validate-scene --scene-file plan/map_scene.json` (rejects HUD plaques, black bar-chart screens, micro-typography, and label collisions).
5. **Domain-Matched Studio Scoring & Foley (`vedit geo auto-audio` + `mix-audio`)**:
   - Resolve real instrumental BGM (curious + tension pivot), ambience, and recorded foley via `vedit geo auto-audio --scene-file plan/map_scene.json --transcript <transcript.json> --brand geoverum -o media/audio/thematic`, then mix via `vedit geo mix-audio` (`-14.0 LUFS / -1.4 dBTP`, zero synthetic oscillator audio).
6. **Mandatory Visual Contact-Sheet Sign-Off**: Inspect a 12-frame contact sheet of `output/master.mp4` via `read_file` before delivery and fix any contrast, tile, label, or caption defects immediately.
