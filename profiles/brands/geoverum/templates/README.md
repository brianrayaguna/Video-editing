# Geoverum Brand Templates

Approved HyperFrames compositions with **typed variables**. Layout, motion, and craft stay locked in the composition file; automation may only change declared variables.

| File | Role |
| :--- | :--- |
| [`catalog.json`](catalog.json) | Template registry validated by `contracts/brand_template.schema.json` |
| Composition paths | Existing studies under `studies/geoverum/*/compositions/` |

This is the operational counterpart to:

- Runtime policy: `../brand_style_policy.json`
- Advisory playbook: `../editorial_playbook.json`
- Craft prose: `../CRAFT.md`

Do not add free-form grammar DSLs here. If a value cannot be expressed as a typed variable, it belongs in a new composition revision—not in a render request.
