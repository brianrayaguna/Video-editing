# Visual Directing Ledger — `ref_batam`

Content hash `f0d083936286f88bf0db36580e8cebe3bba4aa51f33df07dc45968674adc3530`.  
Format: `720×1280`, `60 fps`, `51.950s`, `3117` frames.  
MAD ledger: [`frame-ledger-ref-batam.md`](frame-ledger-ref-batam.md).  
Assets: [`ref-batam/`](ref-batam/).

## Method

| Layer | Coverage |
| :--- | :--- |
| MAD | Every frame → `199` changes / `23` events |
| 1fps grids | Full runtime (`01_hook`, `02_body`) under `ref-batam/visual-pass/section-grids/` |
| Event peaks | `23` stills in `event-frames/` |
| OCR | Lower-third crops → `ref-batam/visual-pass/ocr/` |

## Directing table

| Section | Time | Visual arc | Overlays | Captions (OCR/readable) | Geoverum |
| :--- | ---: | :--- | :--- | :--- | :--- |
| Hook sovereignty | `0–11.2s` | Grid plate + orthographic globe → dive to Riau → Batam crimson fill + Indonesian flag pin → dual Singapore green + Batam red + `±20 KM` | Neon dual fills; yellow `BATAM` / `SINGAPURA` chips; top-center `GEOGRAFYI` mark | `Batam itu Indonesia.` → `Tapi denyut ekonominya.` → foreign-economy lines → `Jaraknya sekitar 20 kilometer.` → Jakarta–Bogor compare | Stagger fills; crimson/cobalt; tabular ±KM in open water; unboxed top-center bug on `9:16` |
| Body economy | `11.2–51.95s` | Continuous Batam regional hold → SEZ/tax icons → factory + money props → inbound/outbound logistics → Malacca dashed corridor with red glow → dual light beams → cash arrows to region | Isometric/factory/money rasters; dual yellow beams; red-glow corridor; green Batam rim late | `pajak lebih ringan`; `Produk dikirim keluar.`; `Tenaga kerja Indonesia.`; `Mesin dan modal global`; `Dan ekonominya` | One amber corridor; Material Symbols only; reject beams/props; keep long ASL glide |

## Map grammar

1. Continuous virtual camera (almost no frozen holds).
2. Simultaneous neon dual fills (reject → stagger).
3. Distance bracket as primary compare device (adopt).
4. Thematic economy props and dual beams (reject).
5. Malacca dashed corridor (adopt as single amber stroke-dash).

## Artefacts

- `ref-batam/frames-full/` (`3117`)
- `ref-batam/contact/`, `event-frames/`, `visual-pass/`
- `ref-batam/frame-changes.json`, `change-events.json`, `ledger-segments.json`, `probe.json`
