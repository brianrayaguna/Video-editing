# Engineering, Naming, and Documentation Standards

These standards apply permanently to all code, schemas, brand profiles, configuration, tests, and documentation in this repository.

## 1. Third-Party Readability & Zero Chat Leakage
- Write every source file, docstring, inline comment, error message, schema description, brand profile, and Markdown document for an external engineer reading the repository cold.
- Never include conversational history, session milestones, rollout stages, or batch/corpus progress counters (such as `Phase 1`, `Phase 2`, `Batch 1`, `Batches 1-2`, `v2`, `v3`, `N/20`, `50-video corpus`, `cumulatively calibrated`, `preserved baseline`, `fixed from earlier`, or reactive explanations defending prior choices).
- Name modules, test files, symbols, and reference exemplars strictly after their technical domain or geographic topic (e.g., `test_contracts.py`, `ref_gibraltar_strait`), never after rollout stages, sequential download indices, or source platform prefixes (never `yt_01`, `batch_01`, `phase2`).
- Keep craft documents (`CRAFT.md`, `README.md`) and advisory trigger rationales timeless and self-contained; do not embed parenthetical reference-ID citation lists inside general rules (concrete measured examples belong exclusively in `exemplar_bank`).

## 2. Neutrality, Third-Party Independence & Portability
- Write all repository artifacts—code, schemas, brand profiles, configuration comments, `.agents/` guidance, and `docs/`—in clear, objective **technical English**.
- Never leak third-party consumer brands, commercial map/editing software names, reference channel names, radar/app product names, or social platform brand names into permanent brand profiles, rules, or schemas. Describe visual and technical mechanics using neutral engineering terminology (e.g., `"dark-mode air-traffic radar visualization"`, `"third-party basemap attribution watermark"`, `"vertical platform bottom UI chrome"`, `"MapLibre and procedural HyperFrames HTML/SVG/GSAP"`). Keep open-data license attributions solely inside designated dataset provenance sections.
- Never embed user-specific absolute paths (e.g., `/Users/<username>/...`) or hardcode product-specific AI client names inside code, rules, or documentation. Refer generically to `"AI directing client"` or `"automated pipeline"`.
- Keep provider selection completely decoupled via `vedit.ports` and `ProviderRegistry`; core modules must never import vendor modules directly or imply that a single external API is mandatory.

## 3. Clean Code & Verification Discipline
- Keep modules small, single-purpose, and strictly typed (Pydantic v2 + Draft 2020-12 JSON Schema in Python, strict ESM TypeScript, zero-unsafe pure Rust where practical).
- Before completing any edit to permanent repository documents or brand profiles, audit modified files to verify zero chat/batch leakage, zero third-party brand leakage, and zero leaked local paths.
- Never claim checks pass without executing the full relevant test, lint, and build suite after the final edit.
