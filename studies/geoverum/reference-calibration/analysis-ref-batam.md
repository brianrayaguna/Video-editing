# Analysis — `ref_batam`

| Field | Value |
| :--- | :--- |
| Source id | `ref_batam` |
| SHA-256 | `f0d083936286f88bf0db36580e8cebe3bba4aa51f33df07dc45968674adc3530` |
| Container | `720×1280`, `60 fps` CFR, `bt709`, `51.950s`, `3117` frames |
| Probe | [`ref-batam/probe.json`](ref-batam/probe.json) |
| Frame ledger | [`frame-ledger-ref-batam.md`](frame-ledger-ref-batam.md) |
| Visual ledger | [`visual-directing-ledger-ref-batam.md`](visual-directing-ledger-ref-batam.md) |
| Samples | [`ref-batam/`](ref-batam/) — craft-samples, event-frames, contact, visual-pass |

Source watermark reads GEOGRAFYI. Geoverum treats the clip as empirical reference only.

---

## 1. Telemetry

| Metric | Measured | Geoverum implication |
| :--- | :--- | :--- |
| Shot count | 2 (`0–11.2s`, `11.2–51.95s`) | Continuous short-form glide with one hard rewrite |
| ASL p50 | `25.975s` | Proof-like cartographic holds remain valid for short explainers |
| Cuts / min | `1.155` | Aligns with continuous-map prior (~1 cut/min) |
| Ground palette | `#06262F` dominant | Compatible with abyssal `#03161F` |
| Band luma | upper `75.2` / lower-third `48.9` | Captions safer over darker water |
| Audio | `−9.1 LUFS`, silence `0` | Hot source; master still `−14.0 LUFS` |

---

## 2. Craft inventory

| Beat | Mechanic |
| ---: | :--- |
| Hook | Globe / Atlantic settle → dive to Batam |
| Sovereignty | Crimson island fill + flag pin + yellow ALL-CAPS land label |
| Dual compare | Singapore lime + Batam crimson simultaneous + `±20 KM` bracket |
| Economy metaphors | Circular raster icons (money, regulation), isometric factory callout |
| Flow | Dashed Malacca corridor with red glow |
| Emphasis chrome | Dual yellow light-beam spears toward urban core |
| Caption | Dark chip, sentence case, hard phrase cuts |
| Bug | Unboxed top-center wordmark |

---

## 3. Adopt / adapt / reject

### Adopt

1. Continuous cartographic glide with long ASL for short-form sovereignty/economy explainers.
2. Sentence-case caption rail with hard phrase cuts.
3. Distance metric between two territories as a primary callout.
4. Dashed maritime corridor as a single-signal flow device.
5. Unboxed top watermark mapped to Geoverum meridian lockup.
6. Terrain-visible island fill with exterior rim (remap chroma).

### Adapt

| Source mechanic | Geoverum mapping |
| :--- | :--- |
| Simultaneous Singapore lime + Batam crimson | Stagger fills (`>= 0.6s`); cobalt then crimson (or reverse by mention order) |
| Yellow `BATAM` chip on land | Amber `#F5C542` + ink `#03161F` in open water / margin + leader |
| Flag planted on landmass interior | Circular flag pin at coordinate with clear-water margin |
| Red-glow dashed corridor | Amber `#F5C542` stroke-dash corridor; no neon bloom |
| `±20 KM` white bracket | Archivo Black tabular metric over open water |
| Yellow dual light beams | Optional single amber leader/flow; never dual competing spears |

### Reject

1. Simultaneous multi-neon territory fills (`simultaneous_multi_neon_fills`).
2. Thematic circular raster icons and isometric factory props (`thematic_emoji_raster_props`, `isometric_economy_props`).
3. ALL-CAPS running land labels covering the focal island.
4. Source loudness as deliverable target.
5. Source channel glyph or wordmark.
6. Light-grid presentation plate behind the globe as default Geoverum ground (keep abyssal `#03161F`).

---

## 4. Gaps addressed in policy / playbook

| Area | Gap | Resolution |
| :--- | :--- | :--- |
| Dual-territory metric | Distance bracket underspecified | Playbook trigger `dual_territory_distance_metric` |
| Maritime corridor | Trade-route draw-on missing | Playbook trigger `maritime_corridor_draw_on` |
| Economy icons | Raster/3D metaphor props common in source | Ban `isometric_economy_props`; keep Material Symbols only |
| Short-form ASL | Body prior still admits denser cuts | Exemplar `ref_batam_*` documents ~26s ASL / ~1.2 cuts/min |
