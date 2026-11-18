# Frame Ledger — `ref_ethiopia_toba`

Content-addressed source hash `0719155d7f16d20cd16819b696657c022d0e2bb4c255fe5d8f6aadf64cbaa686`.  
Format: `854×480` landscape, `≈29.97 fps` CFR, `bt709`, `≈1587.09s`, **`47565` frames**.

**Method.** Every frame under `ref-ethiopia-toba/frames-full/` (`f00001`–`f47565`). Mean-absolute-difference on `128×72` grayscale (`threshold≈9.0`, `merge_gap≈8`) → `frame-changes.json` (`4284` raw deltas) collapsed to `373` events in `change-events.json`. Contiguous hold/event coverage in `ledger-segments.json` (`747` segments, `47565/47565`). Shot-aligned coverage in `frame-ledger.json` (`269` probe shots, full coverage). Overview contacts every `2s` in `contact-full/` (`794` sheets). Peak / section-representative stills in `event-frames/` (`71` exports). Rebuild: `ref-ethiopia-toba/build_frame_ledger.py`.

**Probe.** `269` shots. Cuts/min `10.132`. ASL p25/p50/p75 `2.369` / `3.804` / `6.94`. Integrated loudness `-9.1 LUFS`, true peak `+6.2 dBTP` (hot; deliverables still master to `-14.0` / `≤ -1.0`).

**Craft kinds (midpoint classifier).** map_overlay `76` / caption_heavy `81` / broll `112`. Note: some long probe shots contain map→B-roll rewrites inside one shot index; MAD events capture those denser than scdet alone.

**Source channel mark.** Compact circular mark top-right (landscape). Empirical reference only; glyph is not copied.

**Legend.** *Hold* — schema stable while camera or subject moves. *Event* — cut, overlay rewrite, caption/fact plate, or map schema change.

---

## Section coverage (frame-accurate)

| Section | Time (s) | Frames | Shots | MAD events | Map-kind shots | Dominant grammar |
| :--- | ---: | :--- | ---: | ---: | ---: | :--- |
| Hook | `0–30` | `f00001–f01221` | 3 | 6 | 0† | Collage Horn map + extreme landscape handoff |
| Setup | `30–180` | `f01222–f05586` | 23 | 33 | 8 | Continent→country purple fill; aerial/human scale; early fact plates |
| Body wildlife/culture | `180–720` | `f05587–f21628` | 125 | 155 | 26 | Numbered yellow fact cards + ASL≈`2–5s` B-roll clusters + map returns |
| Escalation heritage / hydro | `720–1080` | `f21629–f32454` | 56 | 72 | 27 | Monument metrics; dual-fill neighbors; Nile/GERD; lake labels |
| Climax science / Toba | `1080–1450` | `f32455–f43621` | 42 | 78 | 10 | Evidence B-roll denser than map; ash/Danakil/Afar loops |
| Outro geology | `1450–1588` | `f43622–f47565` | 20 | 29 | 5 | Afar dual fill + fissure landscape + Ethiopia settle |

†Hook midpoints classify as caption/broll because the opening collage map uses thin purple rims and 3D inserts rather than a solid country wash; MAD still records the map→landscape rewrite.

---

## Representative events (not exhaustive)

| Event | Frame | Time (s) | Peak MAD | Observed rewrite |
| :--- | ---: | ---: | ---: | :--- |
| E006 | f01224 | 40.8 | ≈198.6 | Africa-wide settle → solid purple Ethiopia fill + yellow `ETHIOPIA` chip |
| E011 | f01933 | 64.5 | high | Map schema / regional push after first country fill |
| E059 | f07656 | 255.5 | ≈179.6 | Body map↔wildlife/culture hard rewrite |
| E077 | f09634 | 321.5 | ≈165.9 | Dense body cut cluster |
| E122 | f15057 | 502.4 | ≈209.8 | Film-max MAD; major body schema cut |
| E214 | f23237 | 775.3 | high | Escalation map/heritage rewrite |
| E224 | f26090 | 870.5 | ≈209.2 | Second film-max peak (escalation hydro/heritage) |
| E275 | f33314 | 1111.6 | high | Climax science/evidence entry |
| E326 | f39751 | 1326.4 | ≈143.9 | Late climax evidence cut |
| E355 | f45438 | 1516.1 | ≈149.9 | Outro geology / Afar rewrite |
| E372 | f47266 | 1577.1 | mid | Final Ethiopia purple settle |

Full event list: `ref-ethiopia-toba/change-events.json`. Contiguous segments: `ref-ethiopia-toba/ledger-segments.json`.

---

## Persistent map grammar (observed)

1. **Zoom chain:** continent / Horn wide → purple country fill → optional regional push (lakes, Bab el-Mandeb, Afar) before or after live B-roll.
2. **Primary fill:** semi-transparent violet/magenta wash + white exterior rim + yellow rectangular `ETHIOPIA` (or neighbor) chip. Geoverum remaps to crimson/cobalt single-signal.
3. **Simultaneous multi-fills appear** (Eritrea green + Ethiopia purple; Ethiopia purple + Afar blue). Rejected for Geoverum unless staggered ≥`0.6s`.
4. **Hydro:** cyan/light lake outlines and labels (`DANAU …`, Nile/`NIL BIRU` paths). Adopt via `hydro_accent` `#7CE0F9`.
5. **Thematic 3D props on maps:** erupting volcanoes, cargo ships, collage highland/Dallol inserts. Reject as default chrome.
6. **Infographic text on map:** calendar/`13 BULAN` style plates sitting on the fill. Adapt to amber fact plates off the landmass.
7. **Bug:** top-right circular mark for the full `16:9` duration; optional faint center watermark. Geoverum uses unboxed top-right mark only.
8. **Source chips:** tiny `Source: …` lower-left on many B-roll frames. Optional clean source card; never browser chrome.

## Persistent B-roll / card grammar (observed)

1. Numbered yellow bars (`NN. TITLE`) lower-third on live plates — adapt to amber `#F5C542` + `#03161F` ink.
2. Tabular metrics on subject (`1.500 M`, `KAPASITAS 5.150 MEGAWATT`) — adopt Archivo Black tabular numerals.
3. UNESCO / paper document full-frames — reject as subject-covering walls; optional HTML source card.
4. Warm earth grade + soft vignette on landscape/wildlife clusters (ASL often `2–5s`).
5. Recurring loop: **map → numbered fact → B-roll cluster → optional document → map return**.

## Artefacts

- `ref-ethiopia-toba/frames-full/` — 47565 JPEGs (complete; gitignored)
- `ref-ethiopia-toba/contact-full/sec_XXXX.jpg` — 794 two-second sheets
- `ref-ethiopia-toba/event-frames/` — 71 exported peaks
- `ref-ethiopia-toba/frame-changes.json`, `change-events.json`, `ledger-segments.json`, `frame-ledger.json`, `probe.json`
- `ref-ethiopia-toba/contact/`, `contact-maps/`, `keyframes/`, `shot-craft.json` — prior shot-midpoint pass
