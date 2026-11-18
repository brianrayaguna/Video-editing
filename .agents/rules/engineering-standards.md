# Engineering, Naming, and Documentation Standards

These standards apply permanently to all code, schemas, configuration, tests, and documentation in this repository.

## 1. Third-Party Readability & Zero Chat Leakage
- Write every source file, docstring, inline comment, error message, schema description, and Markdown document for an external engineer reading the repository cold.
- Never include conversational history, iteration counters, or chat-session milestones (such as `Phase 1`, `Phase 2`, `v2`, `v3`, `fixed from earlier`, or reactive explanations defending prior choices).
- Name modules, test files, and symbols strictly after their technical domain and responsibility (e.g., `test_contracts.py`, `test_media_probe.py`), never after rollout stages.

## 2. Neutrality & Portability
- Write all repository artifacts—code, schemas, configuration comments, `.agents/` guidance, and `docs/`—in clear, objective **technical English**.
- Never embed user-specific absolute paths (e.g., `/Users/<username>/...`) or hardcode product-specific AI client names inside code, rules, or documentation. Refer generically to `"AI directing client"` or `"automated pipeline"`.
- Keep provider selection completely decoupled via `vedit.ports` and `ProviderRegistry`; core modules must never import vendor modules directly or imply that a single external API is mandatory.

## 3. Clean Code & Verification Discipline
- Keep modules small, single-purpose, and strictly typed (Pydantic v2 + Draft 2020-12 JSON Schema in Python, strict ESM TypeScript, zero-unsafe pure Rust where practical).
- Never claim checks pass without executing the full relevant test, lint, and build suite after the final edit.
