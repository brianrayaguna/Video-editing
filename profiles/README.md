# Profiles

Two distinct profile kinds live under `profiles/`. Do not mix them.

| Path | Kind | Role |
| :--- | :--- | :--- |
| [`platforms/`](platforms/) | Delivery presets | Resolution, codec, loudness, and safe-zone targets (`youtube_16x9_1080p`, `shorts_9x16_1080p`, …). Owned by the engine layer. |
| [`brands/<brand_id>/`](brands/) | Brand identity | Runtime `brand_style_policy.json` plus optional craft docs and advisory playbooks. Owned per brand, outside core packages. |

## Brand directory layout

```text
profiles/brands/<brand_id>/
  brand_style_policy.json   # Runtime: soft_priors, hard_guardrails, calibration, provenance
  editorial_playbook.json   # Optional advisory grammar/exemplars (not executed by vedit)
  CRAFT.md                  # Optional brand visual craft rules
  templates/catalog.json    # Optional typed brand templates (locked comps + variables)
  README.md                 # Brand overview and asset provenance
```

Runtime consumers (`vedit director`, verifier) read **`brand_style_policy.json`**, and optionally `templates/catalog.json` when `--brand-dir` / `--template-catalog` is passed.  
Advisory exemplars/grammar live in `editorial_playbook.json` (`vedit brand exemplars`).  
Validate trees with `vedit contracts validate` or `vedit brand validate`.  
Schemas: `brand_style_policy.schema.json`, `editorial_playbook.schema.json`, `brand_template.schema.json`.
