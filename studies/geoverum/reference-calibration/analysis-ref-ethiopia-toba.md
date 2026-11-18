# Analysis — `ref_ethiopia_toba`

| Field | Value |
| :--- | :--- |
| Source id | `ref_ethiopia_toba` |
| SHA-256 | `0719155d7f16d20cd16819b696657c022d0e2bb4c255fe5d8f6aadf64cbaa686` |
| Container | `854×480` landscape, ≈`29.97 fps`, `≈1587.09s`, **`47565` frames** |
| Probe | [`ref-ethiopia-toba/probe.json`](ref-ethiopia-toba/probe.json) — `269` shots |
| Full-frame | [`ref-ethiopia-toba/frames-full/`](ref-ethiopia-toba/frames-full/) + MAD ledgers |
| Frame ledger | [`frame-ledger-ref-ethiopia-toba.md`](frame-ledger-ref-ethiopia-toba.md) |
| Visual directing ledger | [`visual-directing-ledger-ref-ethiopia-toba.md`](visual-directing-ledger-ref-ethiopia-toba.md) — 1fps section grids + all map midpoints + OCR |
| Contacts | shot batches [`ref-ethiopia-toba/contact/`](ref-ethiopia-toba/contact/); full timeline [`ref-ethiopia-toba/contact-full/`](ref-ethiopia-toba/contact-full/) (`794` × `2s`) |
| Map subset | `76` `map_overlay` midpoints → [`ref-ethiopia-toba/contact-maps/`](ref-ethiopia-toba/contact-maps/) + `visual-pass/maps_all_*.jpg` |

Coverage is **frame-complete** in telemetry (every frame `1…47565` on disk + MAD/ledgers) and **continuous in visual directing** via 1fps section grids across the full runtime, all 76 map midpoints, 71 event peaks, and 188 OCR caption crops. Native-resolution eyeballing of all `47565` JPEGs is not claimed; the visual ledger replaces sparse sampling.

---

## 1. Telemetry

| Metric | Measured | Geoverum implication |
| :--- | :--- | :--- |
| Frames | `47565` | Full-frame ledger required for long-form grammar |
| Shots | `269` | Long-form cut grammar |
| ASL p50 | `3.804s` | Faster than short-form continuous map glides |
| ASL p25 / p75 | `2.37` / `6.94` | Dense `2–4s` live B-roll clusters |
| Cuts / min | `10.13` | Body prior admits ≈`10` cuts/min |
| MAD changes / events | `4284` / `373` | ≈`14` schema events/min; body densest (`155` events) |
| Palette | `#080907`, earth `#7F765F` | Compatible with abyssal ground |
| Audio | `−9.1 LUFS`, TP `+6.2 dBTP` | Source is hot; master to `−14.0` / `≤ −1.0` |
| Kind mix | map `76` / caption_heavy `81` / broll `112` | ≈`28%` map, ≈`42%` B-roll |

---

## 2. Directing table (section arc)

| Section | Time | Frame range | Shot kinds | Camera | Overlays | Caption / fact card | Audio energy | Geoverum mapping |
| :--- | ---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Hook | `0–30s` | `f1–f1221` | collage map → broll | Horn settle; hard cut to ridge road / extreme land | Purple rim + 3D highland/Dallol inserts; yellow `ETHIOPIA` chip; top-right bug | Minimal lower-third | Hot VO+BGM | Map dive → landscape; strip 3D collage props; crimson rim only |
| Setup | `0.5–3 min` | `f1222–f5586` | map↔aerial↔human | Continent purple wash (~`40.8s` E006); Simien cliffs; climbers | Solid purple fill; white rim; volcano 3D props on rift line | Early numbered yellow plates (`09. …`) | Continuous VO | Zoom chain wide→country; one crimson fill; no volcano props |
| Body wildlife/culture | `~3–12 min` | `f5587–f21628` | broll+cards+maps | Wildlife/ag clusters ASL≈`3–5s`; occasional map return | Purple regional fills; forest icons; yellow `NN.` bars | Dense numbered facts (e.g. teff `35.`) | Steady VO | Amber fact plates; B-roll clusters; map return with single signal |
| Escalation heritage/hydro | mid film | `f21629–f32454` | map-heavy | Bab el-Mandeb push; GERD aerials; lake labels | Dual fills (Eritrea green + Ethiopia purple); cargo ships; Nile path; lake name stack | Metric banners (`5.150 MEGAWATT`); calendar/`13 BULAN` map text | Peak VO density | Stagger dual fills; hydro cyan labels; tabular metrics; reject ships |
| Climax science/Toba | late body | `f32455–f43621` | broll-led | Lake/GERD/Awash/Hadar/Toba ash/Danakil evidence | Fewer solid fills; more ground evidence; occasional map pin | Source chips; sparse cards | Evidence VO | Map→evidence→B-roll loop; Sentinel/relief analogue |
| Outro geology | final `~2–4 min` | `f43622–f47565` | map+fissure | Afar fissure landscape; Ethiopia settle | Purple highlands + blue Afar dual wash; yellow chip | Short thesis cards | Soft close | Stagger Afar cobalt after crimson; fissure B-roll; clean settle |

**Recurring long-form grammar (confirmed frame-accurately)**

1. Purple country or region fill on satellite (often multi-neighbor simultaneous).
2. Yellow `#FFD60A` fact card of the form `NN. JUDUL FAKTA`.
3. Live B-roll cluster (`2–8` shots, ASL ≈ `3–5s`).
4. Optional document / UNESCO / paper screenshot insert.
5. Return to map or the next numbered fact.

**Branding.** Compact circular mark at top-right (landscape) for the entire runtime.

---

## 3. Map grammar detail

| Mechanic | Observation | Geoverum |
| :--- | :--- | :--- |
| Fill color | Violet/magenta wash, white rim | Crimson `#C2412D` or cobalt `#2E74E6` — **one** per beat |
| Simultaneous fills | Eritrea green + Ethiopia purple; Ethiopia + Afar blue | Stagger ≥`0.6s`; never simultaneous neon |
| Labels | Yellow rect chips on land | One primary label in open water / quiet margin |
| Routes | Nile/`NIL BIRU` path; Bab el-Mandeb shipping | One amber stroke-dash corridor; no cargo-ship props |
| Pins | Yellow circle on strait coast | Single amber pulse node after fill hold |
| Hydro | Lake name stack + cyan outlines | `hydro_accent` `#7CE0F9` curved labels when clearance allows |
| Chrome | 3D volcanoes, collage inserts, film-like vignette | Reject thematic 3D/map props; keep terrain-preserving fill |
| Bug | Top-right circular mark | Unboxed meridian mark top-right on `16:9` |

---

## 4. Directing research

Compared against geographic-documentary practice (Umbrella Creators “How to Edit Geography and Map Videos”; Johnny Harris / Vox map-explainer craft notes; general map-animation pacing guides):

| Practice | Source film | Geoverum stance |
| :--- | :--- | :--- |
| House map style + zoom chain (wide → region → detail) before close-ups | Strong: Africa-wide → Ethiopia fill → regional lakes/strait/Afar | **Adopt** |
| Alternate map / ground; avoid map-only screensaver and B-roll-only tourism | Strong loop across `26+` min | **Adopt** as long-form spine |
| Routes/draws timed to spoken clauses | Nile path, shipping beat, calendar plate on map | **Adopt** timing; **reject** cargo-ship metaphors |
| One primary map signal per beat | Often violated (dual fills, 3D props + fill + chip) | **Enforce** single-signal hard prior |
| Long-form 15–30+ min with many map moments | `76` map midpoints + MAD map rewrites throughout | **Adopt** denser body cuts/min ≈`10` |
| Grain / paper / collage evidence (Harris-style) | UNESCO document walls; mixed collage map inserts | **Adapt** to clean source cards; **reject** document walls and 3D collage props |
| Short-form fly-not-cut surprise hooks (contrast) | Not the house style here | Keep short-form continuous glides in Sulawesi/tectonics exemplars |

Industry mistakes called out in the Umbrella guide (close-ups with no context; inconsistent map style; routes off VO) are largely avoided by this film’s zoom chains and map↔ground rhythm—the failures for Geoverum are chroma, simultaneous multi-signal, and prop chrome, not pacing structure.

---

## 5. Adopt / adapt / reject

### Adopt

1. Map ↔ aerial relief ↔ evidence handoff (parallel to Sentinel-2 climax grammar).
2. Numbered fact card as a long-form chapter beat.
3. Metric callouts on B-roll (`1.500 M`, `33 METERS`, `5.150 MEGAWATT`) via Archivo Black tabular type.
4. Hydro cyan lake outlines / lake-name stacks via `hydro_accent` `#7CE0F9`.
5. Triple-junction / plate vectors (Afar) via flow arrows and labels-lines — staggered, not dual neon washes.
6. Landscape vignette + warm earth grade on live B-roll (soft long-form prior only).
7. Aspect-aware bug: top-right mark on `16:9`.
8. Continent→country zoom chain before detail B-roll.
9. Body pacing ≈`10` cuts/min with ASL p50 ≈`3.8s`.

### Adapt

| Source mechanic | Geoverum mapping |
| :--- | :--- |
| Default purple Ethiopia fill | Crimson `#C2412D` or cobalt `#2E74E6` — one per beat |
| Yellow ALL-CAPS fact bar | Amber `#F5C542` + ink `#03161F`; compact title, not a shouty wall |
| Raw browser / paper / UNESCO screenshots | Optional HTML source card without browser chrome |
| Film-strip / viewfinder borders | Rejected as default UI noise |
| Multi-label map clutter / on-map essay text | One primary label; chapter text on amber plate off landmass |
| Simultaneous neighbor fills | Stagger ≥`0.6s`; asymmetric tint vs terrain hold when comparing |

### Reject

1. Violet / magenta default country paint.
2. Corner political stickers.
3. Document walls that cover the focal subject.
4. Source true-peak as a deliverable target.
5. Film-strip / viewfinder chrome (`film_strip_viewfinder_chrome`).
6. Thematic 3D map props (erupting volcanoes, cargo ships, collage highland inserts) — `thematic_3d_map_props`.
7. Simultaneous multi-neon fills (`simultaneous_multi_neon_fills`).
8. Shouty full-width yellow fact bars (`shouty_yellow_fact_bar`).
9. On-map calendar furniture, rain-cloud icons, equator gimmick strokes, and false-color “thermal” grades as default chrome.
10. Film-reel / rounded archival frames and red-circle sticker highlights on evidence stills.

---

## 6. Coverage notes

- Full dump `47565/47565` verified; MAD + ledgers + `794` two-second contact sheets written under `ref-ethiopia-toba/`.
- Semi-manual visual pass: `visual-pass/section-grids/` (1fps × full film), all map keyframes, event peaks, Tesseract OCR on lower-thirds — see [`visual-directing-ledger-ref-ethiopia-toba.md`](visual-directing-ledger-ref-ethiopia-toba.md).
- All `269` shot midpoints remain in contact batches `00–13`; `76` map midpoints in `contact-maps/`.
- Automatic speech transcription was unavailable; captions/fact cards come from OCR + readable plates on grids.
