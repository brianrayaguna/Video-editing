# Analysis — `ref_png_border`

| Field | Value |
| :--- | :--- |
| Source id | `ref_png_border` |
| SHA-256 | `dd9ae48f8d67452d9bb1ca2aea367c5ed77b65c3e4efa1c876d7c49074d8c802` |
| Container | `720×1280`, `29.97 fps` CFR, `bt709`, `46.113s`, `1382` frames |
| Probe | [`ref-png-border/probe.json`](ref-png-border/probe.json) |
| Frame ledger | [`frame-ledger-ref-png-border.md`](frame-ledger-ref-png-border.md) |
| Visual ledger | [`visual-directing-ledger-ref-png-border.md`](visual-directing-ledger-ref-png-border.md) |
| Samples | [`ref-png-border/`](ref-png-border/) — craft-samples, event-frames, contact, visual-pass |

Source watermark reads GEOGRAFYI. Geoverum treats the clip as empirical reference only.

---

## 1. Telemetry

| Metric | Measured | Geoverum implication |
| :--- | :--- | :--- |
| Shot count | 2 (`0–29.062s`, `29.062–46.113s`) | Long cartographic act → archival/live handoff |
| ASL p50 | `23.056s` | Continuous border glide before B-roll |
| Cuts / min | `1.301` | Still map-led, not cut-heavy |
| Band luma | upper `100.2` / lower-third `91.8` | Brighter map; captions need stronger chip contrast |
| Audio | `−16.0 LUFS` | Near delivery target; still normalize to `−14.0` |

---

## 2. Craft inventory

| Beat | Mechanic |
| ---: | :--- |
| Establish | New Guinea outline over bathymetric satellite; vendor chrome credits |
| Asymmetric compare | West solid green + flag; east natural satellite; meridian + southern bite |
| Border stroke | Bright yellow vertical geopolitical line |
| Archive handoff | Hard cut to B&W colonial / river archival |
| Diagram | Red geometric meridian vs blue meandering Fly River labels over diplomatic still |
| Contemporary B-roll | Political balcony beat with double-exposure |
| Caption | Dark chip, sentence case, hard cuts |

---

## 3. Adopt / adapt / reject

### Adopt

1. Geometric-vs-natural border diagram as a single explanatory beat.
2. Asymmetric dual treatment (one side tinted, one side terrain-preserving) when narration contrasts sovereignty vs neighbor.
3. Map → archival / live B-roll handoff for historical causation.
4. Sentence-case caption rail.
5. Thin exterior island outline before fill.

### Adapt

| Source mechanic | Geoverum mapping |
| :--- | :--- |
| Neon yellow meridian | Amber `#F5C542` stroke, `1.5–2.5px`, no glow bloom |
| Solid green west fill | Crimson/cobalt multiply fill preserving terrain; never opaque pastel |
| Flag on green fill interior | Circular flag pin outside fill centroid when possible |
| Blue `Sungai Fly` labels | Hydro cyan `#7CE0F9` only over dark water / quiet margins |
| Double-exposure political B-roll | Clean single-exposure B-roll; optional amber light-leak transition |

### Reject

1. Vendor basemap chrome (Landsat / GEBCO / Google attribution stacks) inside the deliverable frame.
2. Double-exposure / ghost overlays on contemporary faces.
3. Source channel mark.
4. Treating archival grain as a substitute for Geoverum cartographic craft on map beats.

---

## 4. Gaps addressed in policy / playbook

| Area | Gap | Resolution |
| :--- | :--- | :--- |
| Asymmetric dual fill | Only staggered dual neon was specified | Trigger `asymmetric_dual_fill_compare` |
| Border diagram | Meridian vs river underspecified | Trigger `geometric_vs_natural_border_diagram` |
| Map → archival | Only map→live aerial covered | Extend handoff grammar to `archival_or_live_broll` |
| Vendor chrome | Not listed as banned pattern | Ban `vendor_basemap_chrome` |
