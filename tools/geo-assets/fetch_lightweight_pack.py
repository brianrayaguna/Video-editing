#!/usr/bin/env python3
"""Idempotent fetcher and procedural synthesizer for the lightweight Geoverum asset pack.

Installs open-license fonts (SIL OFL 1.1), Lucide SVG icons (ISC/MIT), flag SVGs (MIT),
procedural 48 kHz kinetic SFX WAVs (CC0), and paper/grain textures (CC0) under `assets/`.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.request
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
FONTS_DIR = REPO_ROOT / "assets" / "geo" / "fonts"
ICONS_DIR = REPO_ROOT / "assets" / "geo" / "icons"
FLAGS_DIR = REPO_ROOT / "assets" / "geo" / "flags"
TEXTURES_DIR = REPO_ROOT / "assets" / "geo" / "textures"
SFX_DIR = REPO_ROOT / "assets" / "audio" / "sfx"
MANIFEST_OUT = REPO_ROOT / "assets" / "geo" / "LIGHTWEIGHT_PACK.json"

USER_AGENT = "vedit-lightweight-pack/1.0"

FONT_URLS: dict[str, str] = {
    "Rubik-Variable.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/rubik/Rubik%5Bwght%5D.ttf",
    "PlusJakartaSans-Variable.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/plusjakartasans/PlusJakartaSans%5Bwght%5D.ttf",
    "Oswald-Variable.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/oswald/Oswald%5Bwght%5D.ttf",
    "BebasNeue-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/bebasneue/BebasNeue-Regular.ttf",
}

LUCIDE_ICONS: list[str] = [
    "skull", "shield-off", "siren", "flame", "ban", "lock", "trees", "mountain",
    "droplets", "cloud-rain", "wind", "bug", "paw-print", "car", "truck", "ship",
    "plane", "train-front", "route", "anchor", "compass", "flag", "users",
    "footprints", "dollar-sign", "landmark", "building", "scale", "clock",
    "calendar", "camera", "crosshair", "map-pin", "radar",
    "arrow-up-right", "globe", "radio", "zap", "shield", "eye",
]

FLAG_CODES: list[str] = [
    # Americas
    "us", "ca", "mx", "gt", "bz", "hn", "sv", "ni", "cr", "pa",
    "co", "ve", "ec", "pe", "br", "bo", "py", "uy", "ar", "cl", "cu", "do", "jm",
    # Asia-Pacific
    "id", "sg", "my", "th", "vn", "ph", "jp", "kr", "cn", "tw", "in", "pk", "bd", "au", "nz",
    # Europe
    "gb", "fr", "de", "es", "pt", "it", "nl", "be", "ch", "se", "no", "pl", "ua", "ru", "tr", "gr",
    # Middle East & Africa
    "sa", "ae", "eg", "il", "ir", "qa", "za", "ng", "ke", "ma", "et", "gh",
]


def _download(url: str, dest: Path) -> tuple[str, bool, str]:
    if dest.is_file() and dest.stat().st_size > 100:
        return (dest.name, True, "cached")
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 80:
            return (dest.name, False, f"too small ({len(data)} bytes)")
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            tmp.write_bytes(data)
            tmp.replace(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return (dest.name, True, f"downloaded ({len(data)} B)")
    except Exception as exc:  # noqa: BLE001
        return (dest.name, False, str(exc))


def _derive_static_bold_fonts() -> list[str]:
    derived: list[str] = []
    pairs = [
        ("SpaceGrotesk-Variable.ttf", "SpaceGrotesk-Bold.ttf", 700),
        ("Montserrat-Variable.ttf", "Montserrat-Bold.ttf", 700),
        ("Rubik-Variable.ttf", "Rubik-Bold.ttf", 700),
        ("Rubik-Variable.ttf", "Rubik-Black.ttf", 900),
        ("PlusJakartaSans-Variable.ttf", "PlusJakartaSans-Bold.ttf", 700),
        ("PlusJakartaSans-Variable.ttf", "PlusJakartaSans-ExtraBold.ttf", 800),
        ("Oswald-Variable.ttf", "Oswald-Bold.ttf", 700),
    ]
    for src_name, dst_name, wght in pairs:
        src = FONTS_DIR / src_name
        dst = FONTS_DIR / dst_name
        if not src.is_file() or (dst.is_file() and dst.stat().st_size > 10_000):
            if dst.is_file():
                derived.append(dst_name)
            continue
        font = TTFont(str(src))
        if "fvar" in font:
            loc: dict[str, float] = {a.axisTag: float(a.defaultValue) for a in font["fvar"].axes}
            if "wght" not in loc:
                continue
            loc["wght"] = float(wght)
            static_font = instantiateVariableFont(font, loc, inplace=False, updateFontNames=False)
            static_font["OS/2"].usWeightClass = int(wght)
            if wght >= 700:
                static_font["OS/2"].fsSelection = (static_font["OS/2"].fsSelection & ~0b1000001) | 0b100000
                static_font["head"].macStyle |= 1
            tmp = dst.with_suffix(dst.suffix + ".part")
            try:
                static_font.save(str(tmp))
                tmp.replace(dst)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise
            derived.append(dst_name)
    return derived


def _write_wav_48k_stereo(path: Path, samples: np.ndarray, sr: int = 48000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = float(np.max(np.abs(samples)))
    if peak > 1e-6:
        samples = samples / peak * 0.85
    pcm = np.clip(samples * 32767.0, -32767, 32767).astype(np.int16)
    stereo = np.column_stack((pcm, pcm)).ravel()
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(stereo.tobytes())


def _synthesize_sfx_pack() -> list[str]:
    sr = 48000
    rng = np.random.default_rng(42)
    created: list[str] = []

    def t_arr(dur: float) -> np.ndarray:
        return np.linspace(0.0, dur, int(sr * dur), endpoint=False)

    def env(t: np.ndarray, attack: float, decay: float) -> np.ndarray:
        a = np.clip(t / max(attack, 1e-4), 0.0, 1.0)
        d = np.exp(-np.maximum(0.0, t - attack) / max(decay, 1e-4))
        return a * d

    specs: dict[str, np.ndarray] = {}

    # 1. pop_soft: warm bubble pop
    t = t_arr(0.14)
    freq = 280.0 + 420.0 * np.exp(-t / 0.025)
    specs["pop_soft.wav"] = np.sin(2 * math.pi * np.cumsum(freq) / sr) * env(t, 0.004, 0.032)

    # 2. pop_bright: crisp label pop
    t = t_arr(0.12)
    freq = 520.0 + 780.0 * np.exp(-t / 0.018)
    specs["pop_bright.wav"] = np.sin(2 * math.pi * np.cumsum(freq) / sr) * env(t, 0.002, 0.026)

    # 3. ding_glass: clean documentary bell accent
    t = t_arr(0.45)
    specs["ding_glass.wav"] = (
        0.65 * np.sin(2 * math.pi * 1318.5 * t) * env(t, 0.003, 0.14)
        + 0.35 * np.sin(2 * math.pi * 2637.0 * t) * env(t, 0.002, 0.08)
    )

    # 4. chime_soft: warm two-harmonic reveal chime
    t = t_arr(0.55)
    specs["chime_soft.wav"] = (
        0.6 * np.sin(2 * math.pi * 880.0 * t) * env(t, 0.008, 0.18)
        + 0.4 * np.sin(2 * math.pi * 1320.0 * t) * env(t, 0.012, 0.14)
    )

    # 5. tick_ui: tight micro-click
    t = t_arr(0.05)
    specs["tick_ui.wav"] = (
        np.sin(2 * math.pi * 2400.0 * t) * env(t, 0.001, 0.007)
        + 0.25 * rng.standard_normal(len(t)) * env(t, 0.001, 0.004)
    )

    # 6. counter_tick: mechanical odometer tick
    t = t_arr(0.04)
    specs["counter_tick.wav"] = np.sin(2 * math.pi * 1850.0 * t) * env(t, 0.0008, 0.005)

    # 7. pin_drop: sharp map pin click + low settle
    t = t_arr(0.18)
    specs["pin_drop.wav"] = (
        0.55 * np.sin(2 * math.pi * 1100.0 * t) * env(t, 0.002, 0.022)
        + 0.55 * np.sin(2 * math.pi * 190.0 * t) * env(t, 0.003, 0.045)
    )

    # 8. whoosh_fast: short airy transition swish
    t = t_arr(0.32)
    noise = rng.standard_normal(len(t))
    win = np.hanning(len(t)) ** 1.6
    kernel = np.hanning(19)
    kernel /= kernel.sum()
    specs["whoosh_fast.wav"] = np.convolve(noise, kernel, mode="same") * win

    # 9. whoosh_deep: cinematic camera dive whoosh
    t = t_arr(0.58)
    noise = rng.standard_normal(len(t))
    kernel = np.hanning(55)
    kernel /= kernel.sum()
    low_noise = np.convolve(noise, kernel, mode="same")
    sub = np.sin(2 * math.pi * np.cumsum(110.0 - 55.0 * (t / 0.58)) / sr)
    win = np.sin(math.pi * (t / 0.58)) ** 1.4
    specs["whoosh_deep.wav"] = (0.7 * low_noise + 0.35 * sub) * win

    # 10. swoosh_zoom: whip-zoom blur swoop
    t = t_arr(0.42)
    noise = rng.standard_normal(len(t))
    kernel = np.hanning(31)
    kernel /= kernel.sum()
    f_sweep = 160.0 + 480.0 * np.sin(math.pi * (t / 0.42))
    specs["swoosh_zoom.wav"] = (
        0.65 * np.convolve(noise, kernel, mode="same")
        + 0.35 * np.sin(2 * math.pi * np.cumsum(f_sweep) / sr)
    ) * (np.sin(math.pi * (t / 0.42)) ** 1.3)

    # 11. flash_swish: exposure flash transition
    t = t_arr(0.38)
    noise = rng.standard_normal(len(t))
    kernel = np.hanning(13)
    kernel /= kernel.sum()
    specs["flash_swish.wav"] = (
        0.6 * np.convolve(noise, kernel, mode="same") * env(t, 0.02, 0.09)
        + 0.4 * np.sin(2 * math.pi * 1560.0 * t) * env(t, 0.005, 0.11)
    )

    # 12. sub_thud: dramatic bass drop impact
    t = t_arr(0.45)
    f_drop = 125.0 * np.exp(-t / 0.065) + 38.0
    specs["sub_thud.wav"] = np.sin(2 * math.pi * np.cumsum(f_drop) / sr) * env(t, 0.004, 0.14)

    # 13. stamp_impact: heavy wooden stamp slam
    t = t_arr(0.30)
    f_st = 165.0 * np.exp(-t / 0.03) + 52.0
    click = rng.standard_normal(len(t)) * env(t, 0.001, 0.015)
    specs["stamp_impact.wav"] = (
        0.75 * np.sin(2 * math.pi * np.cumsum(f_st) / sr) * env(t, 0.002, 0.085)
        + 0.45 * click
    )

    # 14. radar_ping: sonar/radar threat ring ping
    t = t_arr(0.55)
    specs["radar_ping.wav"] = (
        0.75 * np.sin(2 * math.pi * 1046.5 * t) * env(t, 0.003, 0.16)
        + 0.25 * np.sin(2 * math.pi * 2093.0 * t) * env(t, 0.002, 0.08)
    )

    # 15. warning_pulse: double low alert pulse
    t = t_arr(0.44)
    p1 = env(t, 0.005, 0.06)
    p2 = np.where(t >= 0.18, env(np.maximum(0.0, t - 0.18), 0.005, 0.07), 0.0)
    specs["warning_pulse.wav"] = np.sin(2 * math.pi * 440.0 * t) * (p1 + 0.85 * p2)

    # 16. paper_flip: crisp archival page/blueprint flick
    t = t_arr(0.24)
    noise = rng.standard_normal(len(t))
    kernel = np.hanning(9)
    kernel /= kernel.sum()
    specs["paper_flip.wav"] = np.convolve(noise, kernel, mode="same") * env(t, 0.015, 0.055)

    for fname, wave_data in specs.items():
        out = SFX_DIR / fname
        _write_wav_48k_stereo(out, wave_data, sr=sr)
        created.append(fname)
    return created


def _synthesize_textures() -> list[str]:
    TEXTURES_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    created: list[str] = []

    # 1. vintage_paper.png (512x512 seamless warm paper grain)
    sz = 512
    base = np.full((sz, sz, 3), [217, 210, 195], dtype=np.float32)
    grain = rng.normal(0.0, 6.5, (sz, sz, 1)).astype(np.float32)
    ys = np.linspace(0, 2 * math.pi, sz, dtype=np.float32)[:, None]
    xs = np.linspace(0, 2 * math.pi, sz, dtype=np.float32)[None, :]
    fiber = (np.sin(xs * 6) * 2.5 + np.cos(ys * 8) * 2.0)[:, :, None]
    img = np.clip(base + grain + fiber, 0, 255).astype(np.uint8)
    Image.fromarray(img, mode="RGB").save(TEXTURES_DIR / "vintage_paper.png", optimize=True)
    created.append("vintage_paper.png")

    # 2. parchment_fold.png (512x512 subtle paper crease shading)
    parch = np.full((sz, sz, 3), [228, 218, 198], dtype=np.float32)
    parch += rng.normal(0.0, 5.0, (sz, sz, 1)).astype(np.float32)
    # Soft vertical & horizontal fold creases
    vx = np.exp(-((np.arange(sz) - sz * 0.5) ** 2) / (2 * 5.0**2))[None, :, None]
    hy = np.exp(-((np.arange(sz) - sz * 0.5) ** 2) / (2 * 5.0**2))[:, None, None]
    parch -= (vx + hy) * 18.0
    Image.fromarray(np.clip(parch, 0, 255).astype(np.uint8), mode="RGB").save(
        TEXTURES_DIR / "parchment_fold.png", optimize=True
    )
    created.append("parchment_fold.png")

    # 3. subtle_grain.png (512x512 monochrome film grain overlay)
    g = np.clip(128.0 + rng.normal(0.0, 22.0, (sz, sz)), 0, 255).astype(np.uint8)
    Image.fromarray(g, mode="L").save(TEXTURES_DIR / "subtle_grain.png", optimize=True)
    created.append("subtle_grain.png")

    return created


def main() -> None:
    tasks: list[tuple[str, str, Path]] = []
    for fname, url in FONT_URLS.items():
        tasks.append(("font", url, FONTS_DIR / fname))
    for icon in LUCIDE_ICONS:
        url = f"https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/{icon}.svg"
        tasks.append(("icon", url, ICONS_DIR / f"{icon}.svg"))
    for code in FLAG_CODES:
        url = f"https://raw.githubusercontent.com/lipis/flag-icons/main/flags/4x3/{code}.svg"
        tasks.append(("flag", url, FLAGS_DIR / f"{code}.svg"))

    results: dict[str, list[str]] = {"font": [], "icon": [], "flag": []}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = {pool.submit(_download, url, dest): (cat, dest) for cat, url, dest in tasks}
        for fut in as_completed(futs):
            cat, dest = futs[fut]
            name, ok, msg = fut.result()
            if ok:
                results[cat].append(name)
            else:
                failures.append(f"{cat}:{name} ({msg})")

    derived_fonts = _derive_static_bold_fonts()
    sfx_files = _synthesize_sfx_pack()
    texture_files = _synthesize_textures()

    # Compute total size across newly installed pack files.
    all_paths = (
        [FONTS_DIR / f for f in results["font"] + derived_fonts]
        + [ICONS_DIR / f for f in results["icon"]]
        + [FLAGS_DIR / f for f in results["flag"]]
        + [SFX_DIR / f for f in sfx_files]
        + [TEXTURES_DIR / f for f in texture_files]
    )
    total_bytes = sum(p.stat().st_size for p in all_paths if p.is_file())
    sha_sample = hashlib.sha256(
        "\n".join(sorted(p.name for p in all_paths if p.is_file())).encode("utf-8")
    ).hexdigest()[:16]

    manifest: dict[str, Any] = {
        "pack_id": "geoverum_lightweight_pack",
        "inventory_hash": sha_sample,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "counts": {
            "fonts_downloaded": len(results["font"]),
            "fonts_derived_static": len(derived_fonts),
            "icons_svg": len(results["icon"]),
            "flags_svg": len(results["flag"]),
            "sfx_wav_48k": len(sfx_files),
            "textures_png": len(texture_files),
        },
        "failures": failures,
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
