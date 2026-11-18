"""Full-film MAD + contacts + shot-aligned ledger for ref_ethiopia_toba."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

BASE = Path(__file__).resolve().parent
FPS = 30000 / 1001
SIZE = (128, 72)  # w, h
MAD_THRESHOLD = 9.0
MERGE_GAP = 8
EVENT_EXPORT_CAP = 90

frames_dir = BASE / "frames-full"
contact_dir = BASE / "contact-full"
event_dir = BASE / "event-frames"
contact_dir.mkdir(exist_ok=True)
event_dir.mkdir(exist_ok=True)

# Clear prior partial exports
for p in event_dir.glob("*.jpg"):
    p.unlink()
for p in contact_dir.glob("sec_*.jpg"):
    p.unlink()

frames = sorted(frames_dir.glob("f*.jpg"))
n = len(frames)
print(f"frames={n} fps={FPS:.3f}", flush=True)
if n != 47565:
    raise SystemExit(f"expected 47565 frames, got {n}")


def load_gray(path: Path) -> np.ndarray:
    return np.asarray(
        Image.open(path).convert("L").resize(SIZE, Image.BILINEAR),
        dtype=np.float32,
    )


# Parallel grayscale load in chunks, then sequential MAD
print("loading grayscale proxies…", flush=True)
grays = [None] * n
chunk = 2000
with ThreadPoolExecutor(max_workers=8) as pool:
    for start in range(0, n, chunk):
        end = min(n, start + chunk)
        paths = frames[start:end]
        loaded = list(pool.map(load_gray, paths))
        grays[start:end] = loaded
        print(f"  loaded {end}/{n}", flush=True)

print("computing MAD…", flush=True)
changes: list[dict] = []
prev = grays[0]
for i in range(1, n):
    cur = grays[i]
    mad = float(np.mean(np.abs(cur - prev)))
    if mad >= MAD_THRESHOLD:
        changes.append(
            {
                "frame": i + 1,
                "prev_frame": i,
                "mad": round(mad, 3),
                "t_s": round(i / FPS, 3),
            }
        )
    prev = cur
    if i % 10000 == 0:
        print(f"  mad @{i}/{n}", flush=True)

(BASE / "frame-changes.json").write_text(json.dumps(changes, indent=2) + "\n")

events: list[dict] = []
if changes:
    cluster = [changes[0]]
    for c in changes[1:]:
        if c["frame"] - cluster[-1]["frame"] <= MERGE_GAP:
            cluster.append(c)
        else:
            peak = max(cluster, key=lambda x: x["mad"])
            events.append(
                {
                    "event_index": len(events),
                    "frame": peak["frame"],
                    "t_s": peak["t_s"],
                    "peak_mad": peak["mad"],
                    "span_frames": [cluster[0]["frame"], cluster[-1]["frame"]],
                    "raw_count": len(cluster),
                }
            )
            cluster = [c]
    peak = max(cluster, key=lambda x: x["mad"])
    events.append(
        {
            "event_index": len(events),
            "frame": peak["frame"],
            "t_s": peak["t_s"],
            "peak_mad": peak["mad"],
            "span_frames": [cluster[0]["frame"], cluster[-1]["frame"]],
            "raw_count": len(cluster),
        }
    )

(BASE / "change-events.json").write_text(json.dumps(events, indent=2) + "\n")
print(f"changes={len(changes)} events={len(events)}", flush=True)

# Highest-MAD + section-representative peaks (even time bins)
by_mad = sorted(events, key=lambda e: e["peak_mad"], reverse=True)
picked: dict[int, dict] = {e["event_index"]: e for e in by_mad[:70]}
duration_s = n / FPS
bin_count = 20
bin_w = duration_s / bin_count
for b in range(bin_count):
    t0, t1 = b * bin_w, (b + 1) * bin_w
    in_bin = [e for e in events if t0 <= e["t_s"] < t1]
    if not in_bin:
        continue
    peak = max(in_bin, key=lambda e: e["peak_mad"])
    picked[peak["event_index"]] = peak
major = sorted(picked.values(), key=lambda e: e["frame"])[:EVENT_EXPORT_CAP]
for ev in major:
    src = frames_dir / f"f{ev['frame']:05d}.jpg"
    if src.exists():
        Image.open(src).save(
            event_dir / f"e{ev['event_index']:03d}_f{ev['frame']:05d}.jpg",
            quality=88,
        )
print(f"event_frames={len(list(event_dir.glob('*.jpg')))}", flush=True)

# Contact strips every 2 seconds
thumb_w, thumb_h = 64, 36
seconds = int(np.ceil(n / FPS))
for sec in range(0, seconds, 2):
    start = int(sec * FPS)
    end = min(n, int((sec + 2) * FPS))
    if start >= n:
        break
    idxs = np.linspace(start, end - 1, num=min(15, end - start), dtype=int)
    sheet = Image.new("RGB", (len(idxs) * thumb_w, thumb_h), (3, 22, 31))
    for col, idx in enumerate(idxs):
        im = Image.open(frames[idx]).resize((thumb_w, thumb_h), Image.BILINEAR)
        sheet.paste(im, (col * thumb_w, 0))
    sheet.save(contact_dir / f"sec_{sec:04d}.jpg", quality=80)
    if sec % 200 == 0:
        print(f"  contact @{sec}s", flush=True)
print(f"contacts={len(list(contact_dir.glob('sec_*.jpg')))}", flush=True)

probe = json.loads((BASE / "probe.json").read_text())
craft = json.loads((BASE / "shot-craft.json").read_text())
kind_by_shot = {s["shot_index"]: s for s in craft.get("shots", [])}
for idx in craft.get("map_overlay_shots", []):
    kind_by_shot.setdefault(idx, {})["kind"] = (
        kind_by_shot.get(idx, {}).get("kind") or "map_overlay"
    )
    kind_by_shot[idx]["is_map"] = True

rows = []
for sh in probe["shots"]:
    i = sh["shot_index"]
    f0 = max(1, int(round(sh["start_s"] * FPS)) + 1)
    f1 = min(n, int(round(sh["end_s"] * FPS)))
    meta = kind_by_shot.get(i, {})
    rows.append(
        {
            "shot_index": i,
            "start_s": sh["start_s"],
            "end_s": sh["end_s"],
            "duration_s": sh["duration_s"],
            "frame_start": f0,
            "frame_end": f1,
            "frame_count": max(0, f1 - f0 + 1),
            "kind": meta.get("kind") or "unclassified",
            "is_map": bool(
                meta.get("is_map") or meta.get("kind") == "map_overlay"
            ),
            "purple": meta.get("purple"),
            "yellow": meta.get("yellow"),
        }
    )

# Contiguous coverage: stitch shot ends to next starts
rows[0]["frame_start"] = 1
for i in range(len(rows) - 1):
    rows[i]["frame_end"] = rows[i + 1]["frame_start"] - 1
    rows[i]["frame_count"] = rows[i]["frame_end"] - rows[i]["frame_start"] + 1
rows[-1]["frame_end"] = n
rows[-1]["frame_count"] = rows[-1]["frame_end"] - rows[-1]["frame_start"] + 1
covered = sum(r["frame_count"] for r in rows)

ledger = {
    "source_id": "ref_ethiopia_toba",
    "sha256": probe["sha256"],
    "fps": FPS,
    "frame_count": n,
    "duration_s": round(n / FPS, 3),
    "shot_count": len(rows),
    "mad_threshold": MAD_THRESHOLD,
    "mad_merge_gap": MERGE_GAP,
    "mad_proxy_size": list(SIZE),
    "mad_changes": len(changes),
    "mad_events": len(events),
    "event_frames_exported": len(major),
    "frame_coverage": covered,
    "shots": rows,
}
(BASE / "frame-ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")
print(f"ledger shots={len(rows)} coverage={covered}/{n}", flush=True)

segs = []
cursor = 1
for e in events:
    if cursor < e["frame"]:
        segs.append({"start": cursor, "end": e["frame"] - 1, "kind": "hold"})
    segs.append(
        {
            "start": e["frame"],
            "end": e["frame"],
            "kind": "event",
            "event": e["event_index"],
            "mad": e["peak_mad"],
            "t_s": e["t_s"],
        }
    )
    cursor = e["frame"] + 1
if cursor <= n:
    segs.append({"start": cursor, "end": n, "kind": "hold"})
seg_cover = sum(1 + s["end"] - s["start"] for s in segs)
(BASE / "ledger-segments.json").write_text(
    json.dumps(
        {
            "fps": FPS,
            "frame_count": n,
            "segments": segs,
            "segment_count": len(segs),
            "coverage": seg_cover,
        },
        indent=2,
    )
    + "\n"
)
print(f"segments={len(segs)} covered={seg_cover}", flush=True)
print("DONE", flush=True)
