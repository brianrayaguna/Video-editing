# Frame Ledger — `ref_png_border`

Content-addressed source hash `dd9ae48f8d67452d9bb1ca2aea367c5ed77b65c3e4efa1c876d7c49074d8c802`.  
Format: `720×1280`, `29.97 fps` CFR, `bt709`, `46.113s`, `1382` frames.

**Method.** Every frame under `ref-png-border/frames-full/` (`f0001`–`f1382`). MAD change detection in `frame-changes.json` (274 raw deltas collapsed to 16 events in `change-events.json`). Contiguous coverage in `ledger-segments.json`. Forty-seven one-second contact sheets. Event peaks in `event-frames/`.

**Probe.** Two shots (`0.000–29.062s`, `29.062–46.113s`). Cuts per minute: `1.301`. ASL p50: `23.056s`. Integrated loudness: `-16.0 LUFS`.

**Source channel mark.** `GEOGRAFYI` top-center. Empirical reference only.

**Legend.** *Hold* — overlay schema stable. *Event* — overlay, caption, or media rewrite.

---

## Shot 0 — New Guinea border cartography (`f0001–f0871`, `0.000–29.062s`)

| Frames | Time (s) | Camera / scene | Overlay state | Caption (observed) | Event |
| :--- | ---: | :--- | :--- | :--- | :--- |
| f0001–f0149 | 0.00–4.97 | Regional New Guinea + N Australia; bathymetry visible | White island outline; Landsat/GEBCO source chrome at bottom | Seperti yang kita ketahui | — |
| f0150–f0281 | 5.00–9.34 | Push toward island | West fill solid green + Indonesian flag pin; east retains satellite; straight meridian + southern “bite” | Yaitu Indonesia | — |
| f0282–f0299 | 9.38–9.94 | Border close | Yellow meridian stroke; bite emphasized | Terdapat sedikit lekukan, | E00 |
| f0300–f0730 | 9.98–24.32 | Slow push / hold along meridian | Yellow border stroke persist | Phrase cuts on border story | E01 |
| f0731–f0765 | 24.36–25.49 | Hard cut to archival B&W | Live map cleared; historical group | Pada Tahun 1893 | E02 |

## Shot 1 — Archival explain + diagram return (`f0872–f1382`, `29.062–46.113s`)

| Frames | Time (s) | Camera / scene | Overlay state | Caption (observed) | Event |
| :--- | ---: | :--- | :--- | :--- | :--- |
| f0766–f0772 | 25.53–25.72 | Archival continue | B&W figures | — | E03 |
| f0773–f0787 | 25.76–26.22 | Archival push | Motion grain | — | E04 |
| f0788–f0798 | 26.26–26.59 | Archival close | Wide-brim figure | — | E05 |
| f0799–f0921 | 26.63–30.70 | Archival close / boat beat | Caption refresh | Untuk memudahkan Inggris → Karena melewati sungai Yang berkelok-kelok | E06–E07 |
| f0922–f0939 | 30.73–31.30 | River canoe archival | Source mark persist | Karena melewati sungai… | E07 |
| f0940–f1046 | 31.33–34.90 | Archival hold | Phrase cuts | — | E08–E11 |
| f1057–f1171 | 35.23–39.03 | Diplomatic still + diagram | Red geometric meridian + blue meandering `Sungai Fly` labels | Agar perbatasan / Dibagian tengah | E12 |
| f1172–f1280 | 39.07–42.67 | Diagram hold / dissolve | Meridian vs river persist | — | E13 |
| f1281–f1378 | 42.71–45.95 | Contemporary political B-roll | Double-exposure balcony beat; PNG flag mask visible | Mengadopsi perbatasan | E14 |
| f1379–f1382 | 45.98–46.11 | Tail | Settle | — | E15 |

Note: shot boundary from probe (`29.062s` ≈ f0871) sits inside the archival stretch; MAD events E02–E07 capture the map→archive rewrite denser than scdet alone.

---

## Persistent motion and overlay rules (observed)

1. Cartographic first act is a continuous glide with a geometric border stroke and asymmetric west/east fill treatment.
2. Second act hands off into archival and contemporary live B-roll with on-map diagrams composited over stills.
3. Caption chips remain dark rounded rectangles, sentence case, lower third, hard switches.
4. Source basemap credits (Landsat / GEBCO) leak into the lower frame on early map beats — Geoverum covers or removes vendor chrome.
5. Border storytelling uses two stroke families: straight meridian (political) vs meandering river (natural).

## Artefacts

- `ref-png-border/frames-full/` — 1382 JPEGs (complete)
- `ref-png-border/contact/sec_XX.jpg`
- `ref-png-border/event-frames/` — 16 event peaks
- `ref-png-border/frame-changes.json`, `change-events.json`, `ledger-segments.json`, `probe.json`
