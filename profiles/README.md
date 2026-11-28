# Profiles

Two distinct profile kinds live under `profiles/`. Do not mix them.

| Path | Kind | Role |
| :--- | :--- | :--- |
| [`platforms/`](platforms/) | Delivery presets | Resolution, codec, loudness, and safe-zone targets (`youtube_16x9_1080p`, `shorts_9x16_1080p`, …). Owned by the engine layer. |
| [`brands/<brand_id>/`](brands/) | Brand identity | Three-layer **Tight Rails, Open Canvas** brand profile outside core packages. |

## Three-Layer Brand Directory Layout

```text
profiles/brands/<brand_id>/
  README.md                 # Progressive-disclosure index map (<1K tokens) & open-data provenance
  brand_style_policy.json   # Layer 1 (Brand DNA SSoT): tokens, typography scale, priors, hard guardrails
  CRAFT.md                  # Layer 1 (Visual Craft): surface registers, adaptive ink, layout, audio craft
  DIRECTING.md              # Layer 2 (Creative Sandbox): Stage 0 concept divergence, 3 axes, open primitives
  editorial_playbook.json   # Layer 2 (On-Demand Recipes): curated visual recipes & role-balanced exemplars
  directing_idioms.json     # Layer 3 (Quality Floor): executable idioms, device wiring, readiness, rubric
  audio_themes.json         # Layer 3 (Optional): domain studio BGM, ambience, and foley theme overrides
  templates/catalog.json    # Layer 3 (Optional): typed HyperFrames overlay components synced to policy tokens
```

Runtime consumers (`vedit director`, `vedit storyboard`, `vedit critique`, `vedit geo build-captions --brand`, `vedit geo auto-audio --brand`, verifier) read **`brand_style_policy.json`**, **`directing_idioms.json`**, and optionally `templates/catalog.json` and `audio_themes.json`.  
Advisory recipes and exemplars in `editorial_playbook.json` are queried on demand (`vedit storyboard context`, `vedit brand exemplars`) and never executed as rigid templates.  
Validate all platform and brand trees with `vedit contracts validate --json` or `vedit brand validate --brand-dir <dir> --json`.  
Schemas: `brand_style_policy.schema.json`, `directing_idioms.schema.json`, `editorial_playbook.schema.json`, `brand_template.schema.json`.
