# Geoverum Directing Method (Layer 2 — Open Creative Sandbox)

How a Geoverum director turns one narration into a **conceptually distinct** cartographic documentary. Brand visual DNA lives in [`brand_style_policy.json`](brand_style_policy.json) and [`CRAFT.md`](CRAFT.md); executable quality checks live in [`directing_idioms.json`](directing_idioms.json); curated recipes live in [`editorial_playbook.json`](editorial_playbook.json).

Geoverum is a **creative sandbox inside tight visual rails**. Every narration must earn its own concept, visual anchor, and surface combination. Two episodes directed under this profile must never look like clones of the same template.

---

## Stage 0: Divergent Concept Pitch (Anti-Mode-Collapse Gate)

Before drafting `plan/storyboard.json`, run one lightweight **Verbalized Sampling** pass to defeat typicality bias:

1. **Generate 4–5 distinct episode concepts** for the narration, assigning each an estimated typicality score (`p` in `0.0–1.0`). At least **two concepts must be non-obvious tail ideas (`p < 0.15`)**—for example, tiling familiar silhouettes inside a plateau, cutting to a split-street comic dialogue, punching a circular zoom loupe into radar traffic, or ending on a minimalist tactical 2D board.
2. **Factor each concept across 3 independent creative axes**:
   - **Axis 1 — Narrative Strategy**: The structural logic implied by the script's hinges (*Rule vs Reality*, *Enumerated Physical Proof*, *Mystery → Mechanism → Human System*, *Paradox → Cause → Consequence*, *Impossibility → Culprit → Escalation*, *Journey Chain*, *Claim Debunk → Catalogue*, or custom).
   - **Axis 2 — Tone / Register**: `documentary`, `investigative`, `wry`, or `comic` (or a deliberate shift mid-story).
   - **Axis 3 — Episode Visual Anchor & Surface Mix**: One concrete, evolving object unique to this story (a dashed line, a glowing zone, a radar void, a travelling marker, a ticking counter) paired with only the surface registers its narrative modes demand.
3. **Check `brand_memory.json` (`recent_episodes`)**: Reject any candidate that repeats the prior episode's `hook_mechanism` + `ending_type` pair or reuses a `signature_image`.
4. **Commit one winning concept** into the Story Brief before touching beat rows.

---

## 1. Story Brief (1 Sentence per Field)

| Field | Answer from the narration |
| :--- | :--- |
| Premise | What surprising truth does the viewer not yet believe or know? |
| Central question | What will the viewer want answered by `t = 3 s` (spoken or shown)? |
| Withheld element | What stays unresolved past the hook, and where does it pay off? |
| Visual anchor | The single evolving image that appears early, mutates, and lands transformed at the end. |
| Creative axes | `Narrative Strategy` × `Tone/Register` × `Surface Mix` + `Per-Story Colour Cast`. |
| Ending note | Irony, consequence, callback, open projection, reversal, measurement, or hard stop on the sharpest fact. |

---

## 2. Open Primitives Authorization (Never Trapped by Templates)

Catalog templates (`templates/catalog.json`) and built-in map layers are **accelerators, not a cage**. Whenever the winning concept calls for a metaphor no built-in template expresses—such as custom top-down vehicles, hand silhouettes on an ATC board, tiled country shapes, split-street comic avatars, or bespoke 2D cross-sections—author an episode-scoped **Open Primitive**:
- Custom vector `map_sprites` (`svg_url`) pinned or animated along map coordinates.
- Custom full-bleed `cutaway_2d` (`html_file`) or tactical 2D scenes.
- Custom `polygon` / `route` / `horizon_3d` staging inside `render_map_scene.mjs`.

Every open primitive inherits **Layer 1 Brand DNA** (calibrated palettes, adaptive ink rules, `Montserrat`/`Inter` typography, upper-center focal stage, zero HUD chrome, and WCAG contrast).

---

## 3. Openings, Hinges, and Endings

- **Frame `0` is always the story world** (map, shape, route, or anomaly)—never an intro bumper, logo sting, or title card.
- **Pick the hook mechanism that performs the central tension**: *Wrong answer first*, *Draw and break*, *Ideal pattern → desaturated anomaly lasso*, *Live misconception counter*, *Whole-route preview*, *Absence on radar*, *Scale-ladder discovery*, *Negation ladder*, or *Disambiguation gag*.
- **Hinge words trigger visible state changes**:
  - `"Why?"` / `"But what's the reason?"` → brief vignette/mood dip, then whip-zoom or dive into cause.
  - `"Firstly / Secondly / Finally"` → clean visual reset; strongest reason gets the richest surface (e.g., daylight 3D terrain or full-bleed cutaway).
  - `"But" / "However" / "Turns out"` → stage the contradiction physically in frame.
  - Historical year / era pivot → shift to parchment or archival register before the year is spoken.
- **Endings derive strictly from the story's ending note**: never append subscribe prompts, generic outro plates, or artificial pull-backs unless explicitly requested.

---

## 4. Clause-Level Storyboarding & Sync

Start from `vedit storyboard auto` (which enforces `directing_idioms.json` floor checks) and refine clause by clause:

1. **Mandatory `story_need -> visual_answer`**: Every beat names what the viewer must grasp. If a visual row could be pasted unchanged into a different episode, replace it with something specific to this story.
2. **One graphic event per stressed noun**: Dense `9:16` narration (`180–200 wpm`) lands a concrete visual beat every `0.25–1.5 s` while keeping `camera_drift` fallback share `<= 35%`.
3. **Show before you name (Sync Lead Table)**:

| Device Class | Lead Before Spoken Word |
| :--- | :--- |
| Markers, fills, pins, icons, flags, radar overlays | `0.0–0.5 s` (typical `0.2 s`) |
| Numerals, acronyms, measurement lines, cutaways | `0.3–1.0 s` (reading clearance) |
| Camera dives, whip-pans, loupes, regime shifts | `0.3–0.9 s` (arrive with place name) |
| Action verbs (stamps, tint flashes, tool actions) | `-0.1–0.15 s` (on the verb) |
| Animated counters | Span the clause and land exact on the number |
| Comic beats / punchlines | May lag slightly to fill a vocal beat |

4. **Per-story colour casting**: Assign one distinct hue per entity or role (*blocked vs open*, *westbound vs eastbound*, *problem vs cure*) at first mention and keep it consistent across every surface switch. Record it in `story.colour_cast`.
5. **Journey-chain exception**: Route-driven films are directed as a continuous **head schedule** (`vedit storyboard journey`): the drawn route tip reaches each named place `0–0.3 s` early, pauses on obstacles (alternating treatment per obstacle), and trails callouts behind travel direction.

---

## 5. Quality Gates & Variation Contract

- **Gate 1 (Pre-render)**: `vedit storyboard readiness` (catch abstract streaks and filler openings) -> `vedit storyboard check` -> `vedit storyboard gate-prerender`.
- **Gate 2 (Visual Critique)**: Render a preview, build grid-anchored contact sheets via `vedit critique packet`, inspect action peaks and transitions directly, and pass `vedit critique gate` (`>= 0.80` weighted rubric, no criterion `< 0.50`, `<= 3` surgical fix rounds).
- **Cross-episode memory**: Record every finished episode to `$VEDIT_PROJECTS_ROOT/geoverum/brand_memory.json` via `vedit brand memory record` so `variation_against_recent` keeps consecutive episodes distinct.
