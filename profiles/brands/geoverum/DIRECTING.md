# Geoverum Directing Method

How a Geoverum director turns one narration into one film. This file governs **story and storyboard decisions**; [`CRAFT.md`](CRAFT.md) governs how the chosen visuals look and move, and [`editorial_playbook.json`](editorial_playbook.json) holds measured exemplars.

The measurable parts of this method are executable: [`directing_idioms.json`](directing_idioms.json) encodes them as parameterised checks (hook timing, event cadence, sync leads, head arrival, regime-change leads, callout concurrency and size, caption band, obstacle variety, signature persistence, ending, variation) plus the defaults the automatic director uses and the rubric for rendered-output review. Direction therefore works in three layers:

| Layer | Source | Without a director | With a director |
| :--- | :--- | :--- | :--- |
| Brand defaults | `directing_idioms.json` | Decide every beat | Retuned per film through `overrides.idiom_params` |
| Automatic storyboard | `vedit storyboard auto` from the word-level transcript | Complete, contract-valid plan | Baseline that director beats replace |
| Director input | Partial storyboard (`--director-file`): story fields, locked beats, emphasis words, banned devices | Empty | Highest priority |

The prose below is how a director (human or AI) improves on the automatic plan; the idioms are the floor every plan must clear. Idiom parameters are measured, not guessed: reference videos are annotated as storyboards and fed to `vedit brand calibrate-idioms` (see the brand-profiling skill).

The profile is a **vocabulary, not a template**. Every narration is a new story with its own question, its own withheld answer, and its own ending note. The structure, the hook, the number of surfaces, the colours, the transitions, and the ending are all *derived from that story*. Two narrations directed with this method must not produce the same film shape; if they do, the direction failed (see [Variation contract](#9-variation-contract)).

---

## 1. The directing loop

Run these steps in order for every episode. Their output is the project's `plan/storyboard.json` ([`contracts/storyboard.schema.json`](../../../contracts/storyboard.schema.json), outside the engine repository), started from `vedit storyboard auto` and refined until `vedit storyboard check` passes, before any `EditPlan` or map scene is built.

1. **Read the story, not the topic.** From the narration alone, write the *story brief* (§2).
2. **Name the story shape** that the narration already implies (§3). Do not impose a shape; detect it from the hinge words and the order in which facts arrive.
3. **Choose the hook mechanism** that best performs *this* story's central tension in the first 1–3 seconds (§4).
4. **Pick the signature image**: the single on-screen object that carries the whole story (a road, a line, a shape, a building, a route, a number filling up). It appears in the hook, mutates through the body, and is still on screen, transformed, at the end.
5. **Cast the colours** for this story's entities and roles (§7).
6. **Storyboard clause by clause** (§5): for each spoken clause, write *story need → visual answer*. One visual idea per clause, one graphic event per stressed noun.
7. **Assign surfaces and transitions** from narrative mode changes, never from a quota (§6).
8. **Sync pass**: place each event against the word timestamps using the offsets in §8.
9. **Variation audit** (§9) against the brand's recent episodes and within the episode itself (list them in `recent_episodes`).
10. **Critique loop** (§5.5) on a low-resolution preview before the final render.

---

## 2. Story brief

Answer each line in one sentence before storyboarding:

| Field | Question to answer |
| :--- | :--- |
| Premise | What is true, in one sentence, that the viewer does not yet believe or know? |
| Central question | What will the viewer *want answered* after 3 seconds? Is it spoken, or only implied by the image? |
| Tension type | Paradox, anomaly, scale shock, misconception, impossibility, rule-vs-reality, journey, or mystery. |
| Withheld element | What is deliberately *not* shown or named yet (the name, the cause, the solution, the hook object's real meaning)? When is it paid off? |
| Signature image | The one object that carries the story from first to last frame. |
| Register | Documentary, investigative, wry, or comic (see §10). |
| Emotional curve | Where curiosity peaks, where the stakes turn human, where tension releases or deliberately does not. |
| Ending note | Irony, consequence, callback, open projection, reversal, or hard stop on the worst fact (§4.3). |

If a field cannot be answered from the narration, the narration is the problem: flag it rather than covering the gap with generic graphics.

---

## 3. Story shapes

Shapes are detected, not chosen from a menu. The narration's hinge words and fact order reveal which one is present; a single film may chain two shapes (for example a funnel that ends in stacked twists). Durations scale with the narration; there are no fixed beat timestamps.

| Shape | Narration signals | Spine | Why the order works |
| :--- | :--- | :--- | :--- |
| **Paradox → mechanism → consequence** | A surprising statistic or line, then "Why is that?", then physical causes | Statistic made visible → nested sharpening → hinge question → cause A → cause B → consequence chain → return to the opening variable | A demographic or physical puzzle needs the numbers felt first, then the geography that explains them. |
| **Impossibility → culprit → escalation** | "Impossible", "the only", "can't", then a named place, then "but what's the reason?" | The attempt drawn and broken → culprit named → menace → pause-and-ask → mechanism → verdict → human stakes → worst threat last | Scale must be seen before cause is meaningful; human danger is held for last because it reframes the problem. |
| **Journey chain** | Chronology: "in 1998", "then", "after", "finally" | Whole route previewed → rule or vow → obstacle chain, each obstacle a different *kind* → rule-preserving solution → totals → open end | Chronological equals spatial: the camera travels the plot, so time needs no explanation. |
| **Enumerated reasons** | "There are three main reasons", "Firstly / Secondly / Finally" | Anomaly → scale proof → evidence → name → promise N → deliver N (the strongest reason gets the most time and the richest surface) → most countable fact | The ordinal promise lets the viewer track progress; each ordinal word is a visual reset. |
| **Negation ladder → deferred reveal** | "Not X, not Y, but Z", then the story of why Z was needed | Hook object shown and its expected nature denied → baseline → disruption → mechanism → escalating catastrophe → hook object revealed as the cure → how it works → restored state | The hook object only makes sense after the problem it solves; the viewer is given permission to wait. |
| **Funnel → stacked twists** | Zoom-like narration from planet to place, then "and even more", "interestingly" | Wrong intuitive answer → true adjacency → closer proof at finer scales → human stakes → contrast → payoff → twist 1 → twist 2 → joke | A tiny distance is only astonishing after the viewer's mental map is overturned. |
| **Claim debunk → catalogue** | "You think there are only…", "another", "even more surprising", "and the third" | Misconception stated → counter breaks it → items catalogued in geographic order, each escalating in strangeness → superlative answered by a measurement | Each new item closes one loop and opens the next; ordering by geography keeps the camera path continuous. |
| **Rule vs reality** | "In theory", "if it were perfectly straight", "for this reason it was decided" | Anomaly → the ideal system → personal instance → counterfactual → failure at human scale → the compromise → opposite extremes → human cost irony | The viewer must know the ideal before its failure, and the compromise before the extremes. |
| **Mystery answered late** | A visual oddity, "what is going on here?", "there's actually a story behind it" | Oddity discovered by zoom → promise hinge → time rewind → cause chain → accident → non-escalation or resolution → return to the opening image, now explained → irony | The hook image *is* the answer; the story exists to make it legible. |
| **Shape origin (history + constraint)** | "Why is it shaped like this?", colonial or political history plus a physical barrier | Shape and its numbers first → rewind → political process → physical constraint → growth along the only free axis → twist epilogue → punchline | The shape is the surprise, so it comes first; history explains intent, geography explains inevitability. |

When none fits, write the shape in words ("anomaly → … → …") and justify the order from the topic, as the table does.

---

## 4. Openings, curiosity, and endings

### 4.1 Hook mechanisms

Choose the mechanism that *performs* the tension the story brief names. Frame 0 is always the story world (map, shape, or route) and never a title card or intro bumper.

| Mechanism | Use when the story… | Visual performance |
| :--- | :--- | :--- |
| Wrong answer first | Overturns a mental map | Animate the intuitive answer (a long way round), then physically overturn it with a camera whip to the true geometry. |
| Draw and break | Claims something is impossible | Draw the attempted thing (route, link, line) from frame 0 and break it visibly before naming the culprit. |
| Live misconception counter | Debunks a belief about a count | A counter shows the believed number, then keeps ticking as ghost shapes appear. |
| Whole-route preview | Follows a journey | Draw the entire promised route once while the camera pans its length, then restart at the origin. |
| Proportion fill | Hinges on a ratio | A pictogram row and counter fill to the value while the outline draws itself. |
| Ideal pattern → anomaly | Contrasts a rule with reality | Wipe the ideal pattern across the world, then hard cut to a desaturated close-up where one lassoed anomaly is the only colour. |
| Scale-ladder discovery | Hides its mystery in a tiny detail | Region → loupe → object, timed to "closer, even closer"; the viewer performs the discovery. |
| Negation ladder | Defines its subject by what it is not | Show the subject's expected materials and cross each out on its word, then flip to the real one. |
| Absence by behaviour | Is about something avoided or missing | Fill the unnamed zone, then show other things (aircraft, routes, people) steering around it. |
| Disambiguation gag | Has a confusable name | Drop the confusable object on the map, remove it on screen, fill the real place. |
| Face before name | Is about one person | Portrait marker first, name and superlative second; the portrait then travels as an avatar. |

Do not reuse the previous episode's hook mechanism unless the story offers no other honest fit.

### 4.2 Curiosity loops and hinges

Keep a loop ledger in the storyboard (`overrides.notes` or beat clauses with function `hinge`): every question the film opens, where it is paid off, and what holds the viewer in between.

- **Open at least one loop that outlives the hook.** A deferred payoff of 30–60 seconds works when an explicit *promise hinge* grants permission to wait ("there's actually a pretty interesting story", "the reason is surprising").
- **Close one loop and open the next in the same clause** for catalogue stories ("another", "even more", "and the third").
- **Callbacks pay off loops visually.** Return to the hook's framing, colour code, or pin when the answer lands.

Hinge words are chapter marks. Each one changes something visible:

| Hinge | Visual response |
| :--- | :--- |
| "Why?", "But what's the reason?" | Mood change for that phrase only (darken, vignette, slow push), then open the answer with a whip or dive. |
| "But", "However", "Turns out" | Contradiction staged in frame: the line, colour, or position that disproves the previous claim appears. |
| "Firstly / Secondly / Finally" | Clear prior graphics and reset the visual mode for each reason. |
| "In the early 1900s", "Back in…" | Time-register change (parchment, era stamp, page turn) before the year is read. |
| "Look,", "Now," | Clean frame: dissolve prior layers to a bare map. |
| "For this reason it was decided" | Execute the decision on screen as it is spoken (redraw, collapse, merge). |
| "Even more", "And that's not all" | Escalate scale or intensity of the same device rather than introducing a new one. |

### 4.3 Endings

The ending is chosen from the story's ending note, never a default pull-back. No subscribe prompts, outro plates, or logo stings unless the brief explicitly requests them.

| Ending | Use when |
| :--- | :--- |
| Hard stop on the worst fact | The story escalates to a danger; cut on the final word with no pull-back. |
| Consequence image | The last claim is a lived consequence; render it with grade (dim to dark, desaturate) or a single pin and time tag. |
| Callback framing | The hook's framing or colour code returns with the explanation layers still on. |
| Open projection | The story is unfinished; draw a dashed projection to the promised destination. |
| Reverse-motion callback | Earlier movement (people leaving, flows) reverses to show restoration, wordless. |
| Irony punchline | The narration's last line is a joke; land it on the final two words and end. |
| Real-world anchor | An abstract diagram resolves into a real aerial or photograph of the same place with the same overlay. |
| Measurement as answer | A superlative was promised; end on the measurement itself. |

---

## 5. Storyboard method

### 5.1 Clause-level derivation

Each clause is one storyboard beat with these fields (see the contract for the full list):

`start_s–end_s | clause | function | story_need | device (+ treatment) | uses_signature_image | surface | camera.regime | transition_in | sync_word + sync_word_s`

The *story need* column is mandatory. A visual answer without a stated need is decoration and is removed. Examples of the pattern:

- Need: make a ratio felt in one second → answer: the ratio fills as a counter and pictogram row on frame 0.
- Need: prove a place is tiny against something huge → answer: show the whole first, dive into the culprit, pull out again so it shrinks to a pinhead.
- Need: show a cause that has no geography (soil, pressure, roots) → answer: zoom through the last icon into a flat cross-section.
- Need: show that time passes with nothing changing → answer: one repeating mechanism (a beam, a clock) and a sliding year ticker; nothing else moves.
- Need: show alternating ownership → answer: lock the camera and flash a full-frame tint on each owning verb.

### 5.2 Storyboard principles

1. **One graphic event per stressed noun.** Dense narration (180–200 words per minute) carries roughly one visual event every 0.25–1.5 seconds; the camera rarely stops.
2. **Show before you name.** The phenomenon, contradiction, or hole appears 0.3–1.0 seconds before its term is spoken, so the word labels something already understood.
3. **The signature image persists and mutates.** A line drawn on "this line" stays for the whole film and is reused as the mechanism's edge. A focal shape survives surface cuts.
4. **Re-frame recurring places differently each time**: fill, title, threat icon, measurement, pins. Repetition builds ownership without repeating a shot.
5. **Contrasting entities get contrasting treatments**: a documentary dive for one, a satirical icon set for the other.
6. **Make invisible qualities literal on the map**: weather as particles, active corridors as physical `cable_3d` links and `model_3d` assets, capacity or spatial impossibility as true-scale `volume_3d` prisms or unpowered infrastructure (`powered: false`), reserving prohibition slashes strictly for literal legal bans, and sparseness as items placed one at a time on a wide shot.
7. **Bring abstraction to human scale** once per film: a pinned place the viewer knows, a street cut by a rule, two people disagreeing across a line.
8. **Mirror sentence grammar.** A causal chain of N links in one sentence pops N icons in spoken order; a list of causes uses a different icon family per cause, worst last.
9. **Counters land on the word.** Count-ups span the spoken phrase and reach the final value as the number is said; roll speed expresses escalation.
10. **Familiar anchors for scale**: tile a familiar silhouette across the zone, transplant the shape onto a familiar region, or overlay a translucent silhouette at true scale.
11. **Numbers on the geometry.** Distances are measurement lines with dual-unit labels rotated along the line, re-proven at each new zoom level.
12. **Park graphics above the protected caption band.** Keep active in-world labels and callouts above `y = 66%` (`y = 66–84%` protected caption clearance) and inside `6%–94%` horizontal margins, re-centering with camera moves so graphics never collide with captions or frame edges.
13. **Anti-stiffness & expressive visual metaphors.** Never default to monotonous stick-pin (`pin_label`) sequences or static grey 3D blobs across consecutive clauses. Translate concrete nouns and actions into lively visual staging: animated fleets or vehicle swarms with wakes along active corridors, 3D unfolding parchment sheets for diplomatic treaties or historical plans, full-bleed 2D cross-sections whenever vertical depth, subsurface clearance, or human-scale height is the proof, circular prohibition slashes on explicit negations or stalled projects, and bold tilted `map_plane` typography locked directly onto terrain. Pair every visual gesture with real recorded foley and studio instrumental scoring via `AudioCatalogPort`.
14. **Editorial matte typography & physical Z-depth.** Never paste shouting ALL-CAPS neon-glow stickers across the top of frames. Use the built-in matte `Montserrat` editorial presets (`editorial_title`, `clean_region`, `era_marquee`, `integrated_stat`, `map_integrated_number`, `dual_unit_stack`) with zero black outline and soft directional drop shadows; layer `integrated_stat` counters behind moving sprites (`z_layer: "under_sprites"`) for depth, sweep oversized `era_marquee` dates smoothly across the canvas, and render lower-band captions through the HTML/Chromium soft Gaussian-shadow overlay (`Inter` Bold `52 px`, `MarginV = 525 px`, no thick karaoke outline).

### 5.3 Device selection by story need

| Story need | Candidate devices (pick by fit, rotate across episodes) |
| :--- | :--- |
| Locate a place | Dive-zoom from a recognisable parent; fill in mention order; pin 0–0.25 s before the name |
| Introduce a territory or border | Trace the outline from the story anchor, then fill; one-headed north-to-south line for a border shared by two filled countries |
| Show nationality or ownership | Full-territory waving and glowing flag clipped to the coastline (`country_block_3d` or `polygon` with `flag_fill`, `flag_wave`, `flag_glow`, `flag_gloss`), revealed from an organic seed, bottom-up wipe, or 3D rise; never small floating rectangular flag pins |
| Show infrastructure, travel, or maritime links | Pitched 3D map geometry matched to the real subject (`model_3d` aircraft with parabolic contrails for air/visa corridors, detailed 3D vessels for fleets, `cable_3d` strictly for physical cables/pipelines, well-spaced `.glb` structures) fused cleanly into terrain without stacking |
| Prove scale or spatial impossibility | True-meter `volume_3d` prism on terrain; familiar silhouette tiling; shape transplant; pull-out until the subject is a pinhead |
| Show negation, bypass, or shortage | Spatial proof on the map (`powered: false` unlit grid, route bypassing an isolated hub, `volume_3d` exceeding landmass bounds); reserve prohibition slashes for literal legal bans |
| Prove distance | Measurement line with count-up and dual units; glowing travel line for non-contiguous links |
| Explain a physical process | Actors (clouds, wind, water) moving and being blocked; cross-section zoom-through; horizon-level terrain flight for vertical facts |
| Explain a historical process | Era register (parchment, serif stamp); entities popping in birth order; growth fill with the camera travelling in the growth direction |
| Show a decision or human action | A tool performing it (pencil redraws, stamp lands, cursor drags) on the spoken verb |
| Show people | Abstract markers that converge, change colour on loss, scatter, and return |
| Show confusion or conflict | Two small avatars with one-line speech bubbles on either side of a line, sides colour-coded |
| Show blocked versus open options | White bouncing arrows for blocked directions, bright green extending arrows for the open one |
| Show seasonal or state change | Edge-grown mask on the basemap itself while borders stay on top |
| Show credibility | Redraw the same focal outline on real data or real imagery |
| Show time of day or darkness | Grade and vignette as proof |
| Show a repeated bureaucratic loop | Repeating pulse rings at one spot, then pull out with a duration numeral |

### 5.4 Journey-chain storyboard

A route-driven film is storyboarded as a **head schedule**, not as a list of shots. The route is one continuous path; the storyboard decides where its drawn head is at each spoken beat.

1. **Name the path markers.** Split the route at every place, obstacle, or turn the narration mentions and give each split a named marker (`start`, `jungle_entry`, `jungle_exit`, `strait`, `shore`, `capital`).
2. **Bind markers to words.** For each clause write `t | clause | head marker | head motion (draw / hold / pause) | camera regime | callout in | callout out`. The head reaches a named place on (or up to `0.3 s` before) the word that names it; it holds while the narration explains an obstacle and resumes on the clause that resolves it.
3. **One map event per stressed phrase.** Dense narration lands a visual event every `0.25–1.5 s`: a draw segment, a fill, a label, an icon pop, a numeral, or a camera regime change. A clause with no event is a hold and must be justified by a pause in the voice.
4. **Obstacles alternate kinds.** Consecutive obstacles use different treatments (fill colour, texture, icon family, camera regime) so the chain reads as escalation rather than repetition.
5. **Camera rides the head.** Wide regime for long transits, regional for legs, close for obstacles; each regime change is one eased move that starts `~0.5 s` before the place is named. Recap and totals return to a whole-route view (globe or continental) before the open ending.
6. **Callouts trail the head.** Every callout is placed relative to the head (see `CRAFT.md` *Layout relative to the route head*) and retired when its leg is finished.

In the storyboard file this is `route.path` + `route.markers`, and per beat `head.marker`, `head.motion`, `head.arrive_s`, `camera.regime`, and `callouts`. `vedit storyboard journey` compiles it into the route-head schedule, camera keys (regime moves that start before the name, denoised), route-width keys, and callout positions that trail the head; the compiled storyboard is checked again with the resolved positions.

Validate the storyboard by reading only the `head marker` column aloud with the timings: it must tell the journey in order with no backtracking except where the narration describes a forced return.

### 5.5 Critique loop

Every film is reviewed on rendered frames, not only on the plan:

1. Render a low-resolution preview.
2. `vedit critique packet --storyboard … --camera-track … --video … -o …` runs the idiom check and the camera shake budget, and renders grid-anchored contact sheets at each beat's sync word (columns A–F, rows 1–10).
3. Alongside beat-level sheets, inspect an action-checkpoint and transition-window view covering exact action peaks (tool/stamp contact, border closure, odometer landing, callout lock-on) and transition boundaries (`t_cut - 2f`, `t_cut`, `t_cut + 2f`) so easing discontinuities, off-target pointers, or mistimed directional blurs are caught before final render.
4. The reviewer scores every rubric criterion in `directing_idioms.json` from 0 to 1, citing frame labels and grid cells, and lists fixes per beat.
5. `vedit critique gate` passes only when the deterministic checks pass, the weighted rubric score reaches `0.8`, and no criterion is below `0.5`. Otherwise apply the fixes and repeat (two or three rounds at most).


---

## 6. Surfaces, registers, and transitions

### 6.1 Surfaces follow narrative mode

The number of surfaces is an output of the story. Most stories run on one dominant surface for 70–90% of runtime and switch only when the narrative mode changes. A single continuous virtual-camera take with overlays is a valid and frequent film.

| Narrative mode | Surface |
| :--- | :--- |
| Where and how big | Graded satellite relief (default spine) |
| Counting, debunking, abstract systems | Dark vector map or pale high-key headline map |
| History, treaties, official plans | Parchment relief or archival plate |
| Mechanism with no map geography | Full-bleed flat cross-section |
| Vertical facts (altitude, depth) | Horizon-level 3D terrain view with screen-fixed altitude chips |
| Texture a map cannot show | Real footage bursts, about 1 second per noun, cut on the noun |
| Global totals or summaries | Globe |
| Ground-level atmosphere (storms, crowds) | Flat ground-level illustration |
| Evidence of reality | Real aerial photograph or real data visualization (rebuilt procedurally, never captured third-party interface) |

A change of register signals a change of narrative mode: stylized → realistic means "now evidence"; modern → parchment means "now history"; map → cross-section means "now mechanism".

### 6.2 One transition device per jump type

Within one film, each kind of jump keeps its own device so transitions read as grammar:

| Jump | Device |
| :--- | :--- |
| Contiguous map acts in the same world | Exact camera match-frame (`hard_cut` with identical end/start camera coordinates and framing) |
| Regional leap or scale change | Dive-zoom or whip-zoom with radial blur (0.25–1.0 s) |
| Map → diagram | Zoom through the last icon |
| Chapter reset | Dip to black (≈0.5 s) or full graphic clear by dissolve |
| Archive or history pivot | Page curl or page turn |
| Weather or atmosphere | Wash dissolve |
| Hook flip | Colour-flash cut |
| Surface swap at equal scale | White bar wipe (≈0.25 s) |
| Macro scale or map-mode jump | Feathered dark directional wipe (`feathered_dark_wipe`, 3–5 frames at 30 fps, default right-to-left) with captions kept above |
| Basemap register swap at equal framing | Feathered black-disc sweep (`disc_sweep`, 6 frames), match-framed, captions unmasked |
| Archive or treaty reveal | Upright `0°` parchment unfold (`page_unfold`, ≈0.35–0.47 s) |
| Flat map ↔ globe | Continue the zoom through a radial blur peaking on the cut frame (`cut_blur_out_s` / `cut_blur_in_s`) |
| Map level → character level | Lens or iris dissolve |
| Abstract → real place | Whip-zoom into a real aerial with the same overlay |

Hard cuts are rare (0–4 per minute in map-driven films). Spend a full transition only where the narrative mode changes.

---

## 7. Colour casting per story

Colours are cast per story, not fixed per role across all films.

1. **Assign one hue per entity at first mention and keep it for the whole film**, across every surface. National flags may serve as fills when nationality is the point.
2. **Code by role when roles matter more than entities**: problem versus cure, blocked versus permitted, ideal versus real, past owner versus present owner.
3. **Reserve one single-use colour for the key metric** so it appears exactly once.
4. **Desaturate everything except the anomaly** when the anomaly must be the only coloured thing.
5. **Use grade as an emotional channel**: brown during catastrophe, release to full colour on the human-stakes beat, progressive dimming for darkness or dread.
6. Brand accents in [`CRAFT.md`](CRAFT.md) are the default cast. Depart from them when the story's entities need it, and record the casting in `story.colour_cast`.

---

## 8. Sync and pacing

| Event | Offset relative to the spoken word |
| :--- | :--- |
| Fills, pins, labels, icons | Lead by 0–0.5 s (typically 0.2 s) |
| Large numerals, titles, measurement lines | Lead by 0.5–0.9 s to give reading time |
| Counters | Span the phrase and land exactly on the number |
| Dives toward a named place | Start about 0.5 s early to arrive with the name |
| Tint flashes, stamps, tool actions | On the action verb |
| Joke beats | May lag deliberately; let a visual gag fill the pause |

Camera moves follow the same sync table: a regime change (wide → regional → close) is one eased move that arrives with the place name, and between beats the camera keeps a slow drift rather than stopping dead. Each move arrives at its framing with zero velocity; a dive that ends on a cut keeps accelerating into the cut frame, and map frames stay sharp at every speed. Measured or hand-keyed camera tracks are denoised before baking (`CRAFT.md` *Core motion*); a visible back-and-forth wobble reads as an error, never as energy.

Pacing follows story pressure: fastest at the hook and the escalation, a near-still hold only on a structural promise ("three main reasons") or complex cutaway gauge reading, a palate-cleanser clean frame before a new "why". Maintain strict numeric parity between spoken narration and on-screen callouts (using paired metric/imperial units where helpful), keep all callouts and scale rulers inside safe frame margins (`8%–92%` horizontal, `>= 12%` top clearance), and preserve dark-halo caption legibility whenever pale terrain or snow passes through the caption band.

---

## 9. Variation contract

The profile must not collapse into one repeated film. Enforce these checks on the storyboard before drafting the `EditPlan` (the `variation_against_recent` idiom automates the cross-episode part):

1. **Derivation test.** Every storyboard row cites its clause and story need. If a row could be pasted into a different narration unchanged, rewrite it from this story's need.
2. **Episode fingerprint.** Record `story_shape`, `hook_mechanism`, `signature_image`, `dominant_surface`, `surface_count`, `colour_cast`, `transition_set`, and `ending_type`. Compare with the brand's recent episodes (recorded in their project workspaces): no two consecutive episodes may share the same hook mechanism *and* ending type, and none may reuse a signature image.
3. **Within-film rotation.** The same device may not answer two different story needs in one film, and a recurring place is re-framed with a different treatment each time it returns.
4. **No quota surfaces.** A surface, cross-section, or footage burst is added only when a narrative mode needs it. Adding one to "hit" a share is template behaviour.
5. **Series of episodes.** When several episodes are requested together, write all story briefs first, assign distinct hook mechanisms, signature images, and ending types across the set wherever the stories allow, and then storyboard each one independently.

---

## 10. Register and tone

- **Documentary and investigative** registers are the default.
- **Wry** register uses visual irony inside the documentary vocabulary: a cursor where a modern tool is absent, a stamp for a verdict, a thumbs-up burst for consensus.
- **Comic** register is part of the brand vocabulary and is chosen when the narration carries jokes, euphemisms, or deadpan irony: talking characters, flag avatars with faces, crowds of small flag figures, reaction faces, speech-bubble dialogue, cut-out stickers, and short visual gags that fill a narration pause.
- Comic elements obey the same directing rules as every other device:
  1. **Motivated**: each character, face, or bubble performs an action or reaction the narration states or implies (a loser asking where its coast went, two people disagreeing across a line, a gagged face on the worst threat).
  2. **Geography first**: characters stand on or beside the territory they represent and never cover the focal geography or the caption band.
  3. **Bounded**: a skit or gag runs for one beat, and the film returns to the map, often with an explicit verbal reset.
  4. **Consistent casting**: a character keeps its entity's colour or flag for the whole film.
  5. **Clean execution**: flat vector characters with crisp outlines and simple expressive faces; no low-resolution raster memes.
  6. **Varied**: a comic beat that worked in one episode is not repeated as a default in the next; it must arise from the new narration's own joke or irony.
