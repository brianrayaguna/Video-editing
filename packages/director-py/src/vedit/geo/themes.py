"""Externalizable documentary audio theme profiles with optional brand-directory overrides."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DEFAULT_AUDIO_THEMES: dict[str, dict[str, Any]] = {
    "maritime": {
        "keywords": (
            "pelabuhan",
            "kapal",
            "selat",
            "laut",
            "dermaga",
            "samudra",
            "kargo",
            "maritim",
            "port",
            "ship",
            "strait",
            "ocean",
            "sea",
            "maritime",
            "vessel",
            "canal",
            "harbor",
        ),
        "curious_query": "mysterious rhythmic marimba documentary",
        "tension_query": "dark suspense orchestral hybrid documentary",
        "ambience_query": "ocean waves sea ambience",
        "ambience_gain_db": -27.5,
        "foley": {
            "maritime_horn": ("distant cargo ship fog horn", -17.0, 2.4, 0.8),
            "underwater_dive": ("underwater dive splash submerge", -9.5, 2.2, 0.7),
        },
    },
    "weather": {
        "keywords": (
            "badai",
            "debu",
            "angin",
            "kering",
            "kekeringan",
            "hujan",
            "salju",
            "iklim",
            "storm",
            "dust",
            "wind",
            "drought",
            "blizzard",
            "hurricane",
            "climate",
            "monsoon",
        ),
        "curious_query": "minimal documentary acoustic investigative",
        "tension_query": "ominous dark ambient tension documentary",
        "ambience_query": "wind blowing prairie ambience",
        "ambience_gain_db": -26.5,
        "foley": {
            "wind_gust": ("strong wind dust gust", -14.0, 2.2, 0.7),
        },
    },
    "infrastructure": {
        "keywords": (
            "kereta",
            "jembatan",
            "terowongan",
            "bendungan",
            "jalan",
            "tol",
            "pipa",
            "kabel",
            "railway",
            "train",
            "bridge",
            "tunnel",
            "dam",
            "highway",
            "pipeline",
            "cable",
            "grid",
        ),
        "curious_query": "pulsing minimal tech documentary",
        "tension_query": "tense pulse investigative documentary",
        "ambience_query": "distant industrial city hum ambience",
        "ambience_gain_db": -28.0,
        "foley": {},
    },
    "geology": {
        "keywords": (
            "gunung",
            "gempa",
            "lempeng",
            "vulkanik",
            "magma",
            "patahan",
            "sungai",
            "lembah",
            "volcano",
            "earthquake",
            "tectonic",
            "fault",
            "magma",
            "canyon",
            "glacier",
            "river",
        ),
        "curious_query": "cinematic atmospheric wonder documentary",
        "tension_query": "deep rumble suspense documentary",
        "ambience_query": "deep mountain wind nature ambience",
        "ambience_gain_db": -27.5,
        "foley": {},
    },
    "aviation": {
        "keywords": (
            "pesawat",
            "bandara",
            "penerbangan",
            "udara",
            "rute terbang",
            "aircraft",
            "airport",
            "flight",
            "airspace",
            "airline",
            "aviation",
        ),
        "curious_query": "modern investigative electronic documentary",
        "tension_query": "suspenseful hybrid documentary",
        "ambience_query": "distant airplane jet ambience",
        "ambience_gain_db": -28.0,
        "foley": {},
    },
    "geopolitics": {
        "keywords": (
            "perbatasan",
            "negara",
            "perjanjian",
            "wilayah",
            "ekonomi",
            "miliar",
            "strategis",
            "border",
            "treaty",
            "territory",
            "sovereignty",
            "geopolitics",
            "billion",
            "enclave",
        ),
        "curious_query": "investigative minimal documentary marimba",
        "tension_query": "dark investigative tension orchestral",
        "ambience_query": "subtle outdoor air room ambience",
        "ambience_gain_db": -30.0,
        "foley": {},
    },
}


def load_audio_themes(*, brand_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return theme profiles, layering optional `<brand_dir>/audio_themes.json` overrides."""
    themes = copy.deepcopy(DEFAULT_AUDIO_THEMES)
    if brand_dir is not None:
        override_path = brand_dir / "audio_themes.json"
        if override_path.is_file():
            raw = json.loads(override_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for name, cfg in raw.items():
                    if not isinstance(cfg, dict):
                        continue
                    entry = dict(cfg)
                    if isinstance(entry.get("keywords"), list):
                        entry["keywords"] = tuple(str(k).lower() for k in entry["keywords"])
                    themes[str(name)] = entry
    return themes
