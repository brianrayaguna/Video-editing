# Geoverum — Cartographic Documentary Brand Profile

**Geoverum** is a cartographic documentary brand profile for `vedit` across `9:16` portrait (`1080x1920` @ `30 fps`) and `16:9` landscape (`1920x1080` / `3840x2160` @ `30 fps`).

It follows a **Tight Rails, Open Canvas** three-layer architecture so every episode is unmistakably Geoverum in craft while remaining free to invent a fresh visual concept for each narration.

## Progressive Disclosure Map (Read Only What Your Stage Needs)

| Layer | File | Read When | Role |
| :--- | :--- | :--- | :--- |
| **Layer 1: Brand DNA (~20% locked)** | [`brand_style_policy.json`](brand_style_policy.json) | Always (runtime SSoT) | Single source of truth for palette roles, typography scale (`Montserrat` display/hero, `Inter` `46 px` / `42 px` captions), temporal priors, and hard guardrails. |
| **Layer 1: Visual Craft** | [`CRAFT.md`](CRAFT.md) | Visual styling & grading | Five surface registers, adaptive ink/glow rules, upper-center composition stage, motion feel, and rejected chrome. |
| **Layer 2: Creative Sandbox (~80% open)** | [`DIRECTING.md`](DIRECTING.md) | Concepting & storyboarding | Stage 0 Divergent Concept Pitch (*Verbalized Sampling*), 3 independent creative axes, Open Primitives authorization, sync, and variation. |
| **Layer 2: On-Demand Recipes** | [`editorial_playbook.json`](editorial_playbook.json) | Retrieved per storyboard | 20 curated visual recipes and 22 role-tagged exemplars queried via `vedit storyboard context` (`exemplar_retrieval.py`). |
| **Layer 3: Quality Floor & Wiring** | [`directing_idioms.json`](directing_idioms.json) | Automated gates & critique | Executable storyboard idioms, device-to-template wiring, bilingual `readiness_phrases`, and visual critique rubric. |
| **Layer 3: Audio & Templates** | [`audio_themes.json`](audio_themes.json), [`templates/`](templates/) | Scoring & overlay compile | Domain-matched studio BGM/ambience/foley queries and parameterized HyperFrames HTML components. |

Engine-wide motion and compositing boundaries live in [`../../../DESIGN.md`](../../../DESIGN.md). External per-brand episode history lives outside the repository at `$VEDIT_PROJECTS_ROOT/geoverum/brand_memory.json`.

## Geospatial Open-Data Provenance

Shared offline assets are fetched via [`../../../tools/geo-assets/fetch_assets.py`](../../../tools/geo-assets/fetch_assets.py) against [`../../../assets/geo/MANIFEST.json`](../../../assets/geo/MANIFEST.json):

- NASA Blue Marble NG (shaded relief & bathymetry) — Public Domain
- EOX Sentinel-2 cloudless — CC BY 4.0
- Natural Earth 1:10m — CC0
- Peter Bird `PB2002` plates — ODC-By 1.0; GEM active faults — CC BY-SA 4.0
