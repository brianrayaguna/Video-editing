# Frame Ledger — `ref_batam`

Content-addressed source hash `f0d083936286f88bf0db36580e8cebe3bba4aa51f33df07dc45968674adc3530`.  
Format: `720×1280`, `60 fps` CFR, `bt709`, `51.950s`, `3117` frames.

**Method.** Every frame under `ref-batam/frames-full/` (`f0001`–`f3117`). Mean-absolute-difference change detection in `frame-changes.json` (199 raw deltas collapsed to 23 overlay/schema events in `change-events.json`). Contiguous coverage of all frames in `ledger-segments.json`. Fifty-two one-second contact sheets in `contact/`. Event peaks in `event-frames/`.

**Probe.** Two shots (`0.000–11.200s`, `11.200–51.950s`). Cuts per minute: `1.155`. ASL p50: `25.975s`. Integrated loudness: `-9.1 LUFS` (hot; deliverables still master to `-14.0`).

**Source channel mark.** `GEOGRAFYI` top-center. Treated as empirical reference only; glyph and wordmark are not copied.

**Legend.** *Hold* — overlay schema stable while the camera moves. *Event* — overlay, caption, or scene rewrite.

---

## Shot 0 — Globe dive to Batam sovereignty (`f0001–f0672`, `0.000–11.200s`)

| Frames | Time (s) | Camera / scene | Overlay state | Caption (observed) | Event |
| :--- | ---: | :--- | :--- | :--- | :--- |
| f0001–f0001 | 0.00 | Black / pre-roll | — | — | — |
| f0002–f0085 | 0.02–1.40 | Orthographic globe / Atlantic settle; light grid plate behind Earth | Source watermark lands | Batam itu Indonesia. | E00 |
| f0086–f0279 | 1.42–4.63 | Dive / push into Riau–Singapore | Batam crimson glow + Indonesian flag pin + yellow `BATAM` chip on land | Batam itu Indonesia. | E01 |
| f0280–f0355 | 4.65–5.90 | Regional Riau hold | Batam fill + flag | Phrase refresh | E02 |
| f0356–f0438 | 5.92–7.28 | Slow push; Singapore north of frame | Batam red glow + white rim | Batam berdiri hanya selemparan batu | E03 |
| f0439–f0540 | 7.30–8.98 | Dual framing Singapore–Batam | Dual neon fills preparing | — | E04 |
| f0541–f0672 | 9.00–11.18 | Dual settle | Singapore green + Batam red; white `±20 KM` bracket | Jaraknya sekitar 20 kilometer. | E05 |

## Shot 1 — Economic explainers on continuous map (`f0673–f3117`, `11.200–51.950s`)

| Frames | Time (s) | Camera / scene | Overlay state | Caption (observed) | Event |
| :--- | ---: | :--- | :--- | :--- | :--- |
| f0673–f0674 | 11.20–11.22 | Hard rewrite into coastal close / lower plate | Transition residue | Jakarta ke Bogor. | E06 start |
| f0675–f0808 | 11.23–13.45 | Coastal / industrial explain beat | Split plate / map residual | Jakarta ke Bogor. | E06 |
| f0809–f1082 | 13.47–18.02 | Return to Batam regional | Batam red fill; factory callout pin | Batam dirancang sebagai | E07 |
| f1083–f1216 | 18.03–20.25 | Micro push | Fill hold | Phrase cuts | E08 |
| f1217–f1358 | 20.27–22.62 | Batam regional | Circular thematic icons (money / regulation chart) | Aturan lebih longgar. | E09 |
| f1359–f1485 | 22.63–24.73 | Pull / pan | Icon cluster persist | — | E10 |
| f1486–f1659 | 24.75–27.63 | Wider Riau | Icons clear / map calm | — | E11 |
| f1660–f1817 | 27.65–30.27 | Malay Peninsula + Sumatra pull | Tiny sovereignty pin near Singapore/Batam tip | bekerja untuk pasar luar negeri. | E12 |
| f1818–f1885 | 30.28–31.40 | Regional | Calm satellite | — | E13 |
| f1886–f1997 | 31.42–33.27 | Batam push | Yellow dual light-beam / spear overlays | — | E14 |
| f1998–f2147 | 33.28–35.77 | Batam center | Dual amber beams toward urban core | Uangnya muter lintas negara. | E15 |
| f2148–f2247 | 35.78–37.43 | Pull to SE Asia | Beams clear | — | E16 |
| f2248–f2347 | 37.45–39.10 | SE Asia wide | Maritime corridor prep | — | E17 |
| f2348–f2572 | 39.12–42.85 | Indo-Pacific widen | Dashed Malacca trade corridor with red glow | Lokasinya strategis | E18 |
| f2573–f2786 | 42.87–46.42 | Corridor hold / micro | Corridor persist | Phrase cuts | E19 |
| f2787–f2916 | 46.43–48.58 | Pull / reframe | Corridor fades; Batam rim brightens | — | E20 |
| f2917–f2940 | 48.60–48.98 | Regional settle | Batam white/amber exterior stroke | Dan ekonominya | E21 |
| f2941–f3117 | 49.00–51.95 | Tail hold | Stroke settle; caption breath | — | E22 |

---

## Persistent motion and overlay rules (observed)

1. Virtual camera motion remains non-zero across most `0.5s` windows; frozen still holds are rare.
2. After landing, the top-center source watermark stays dead still.
3. Caption chips use a dark rounded rectangle, white sentence-case Indonesian, lower ~72–78% of frame height, hard phrase switches.
4. Territory fills are high-chroma neon (crimson / lime) with white exterior rims; Geoverum remaps chroma and forbids simultaneous neon multi-fills unless staggered.
5. Metric brackets (`±20 KM`) and dashed trade corridors are primary explanatory devices.
6. Thematic circular raster/3D icons (money bag, factory isometric, regulation chart) appear as economy metaphors.

## Artefacts

- `ref-batam/frames-full/` — 3117 JPEGs (complete)
- `ref-batam/contact/sec_XX.jpg` — one-second sheets
- `ref-batam/event-frames/` — 23 event peaks
- `ref-batam/frame-changes.json`, `change-events.json`, `ledger-segments.json`, `probe.json`
