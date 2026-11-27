#!/usr/bin/env python3
"""Curated open-license typography catalog, downloader, and static font instantiator.

Manages 38 commercially safe font families (SIL OFL 1.1 / Apache-2.0) across five
editorial categories (`display`, `sans`, `serif`, `mono`, `handwriting`) inside
`assets/geo/fonts/`, derives static Bold/SemiBold/ExtraBold/Black/Italic `.ttf`
instances for `libass` / FFmpeg when `fonttools` is available, writes
`assets/geo/fonts/FONTS_MANIFEST.json`, and keeps `fonts.conf` synchronized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FONTS_DIR = REPO_ROOT / "assets" / "geo" / "fonts"
MANIFEST_PATH = FONTS_DIR / "FONTS_MANIFEST.json"
USER_AGENT = "vedit-font-catalog/1.0"
_GF_BASE = "https://raw.githubusercontent.com/google/fonts/main"
_VALID_FONT_MAGICS = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")


def _gf(rel: str) -> str:
    return f"{_GF_BASE}/{rel}"


FONT_CATALOG: list[dict[str, Any]] = [
    # --- Display (9) ---
    {
        "family": "Archivo Black",
        "category": "display",
        "license": "SIL OFL 1.1",
        "files": {
            "ArchivoBlack-Regular.ttf": [_gf("ofl/archivoblack/ArchivoBlack-Regular.ttf")],
        },
    },
    {
        "family": "Unbounded",
        "category": "display",
        "license": "SIL OFL 1.1",
        "files": {
            "Unbounded-Variable.ttf": [_gf("ofl/unbounded/Unbounded%5Bwght%5D.ttf")],
        },
    },
    {
        "family": "Bebas Neue",
        "category": "display",
        "license": "SIL OFL 1.1",
        "files": {
            "BebasNeue-Regular.ttf": [_gf("ofl/bebasneue/BebasNeue-Regular.ttf")],
        },
    },
    {
        "family": "Oswald",
        "category": "display",
        "license": "SIL OFL 1.1",
        "files": {
            "Oswald-Variable.ttf": [_gf("ofl/oswald/Oswald%5Bwght%5D.ttf")],
        },
    },
    {
        "family": "Anton",
        "category": "display",
        "license": "SIL OFL 1.1",
        "files": {
            "Anton-Regular.ttf": [_gf("ofl/anton/Anton-Regular.ttf")],
        },
    },
    {
        "family": "League Gothic",
        "category": "display",
        "license": "SIL OFL 1.1",
        "files": {
            "LeagueGothic-Variable.ttf": [
                _gf("ofl/leaguegothic/LeagueGothic%5Bwdth%5D.ttf"),
                _gf("ofl/leaguegothic/LeagueGothic-Regular.ttf"),
            ],
        },
    },
    {
        "family": "Syne",
        "category": "display",
        "license": "SIL OFL 1.1",
        "files": {
            "Syne-Variable.ttf": [_gf("ofl/syne/Syne%5Bwght%5D.ttf")],
        },
    },
    {
        "family": "Barlow Condensed",
        "category": "display",
        "license": "SIL OFL 1.1",
        "files": {
            "BarlowCondensed-Regular.ttf": [
                _gf("ofl/barlowcondensed/BarlowCondensed-Regular.ttf")
            ],
            "BarlowCondensed-SemiBold.ttf": [
                _gf("ofl/barlowcondensed/BarlowCondensed-SemiBold.ttf")
            ],
            "BarlowCondensed-Bold.ttf": [_gf("ofl/barlowcondensed/BarlowCondensed-Bold.ttf")],
            "BarlowCondensed-ExtraBold.ttf": [
                _gf("ofl/barlowcondensed/BarlowCondensed-ExtraBold.ttf")
            ],
            "BarlowCondensed-Italic.ttf": [_gf("ofl/barlowcondensed/BarlowCondensed-Italic.ttf")],
            "BarlowCondensed-BoldItalic.ttf": [
                _gf("ofl/barlowcondensed/BarlowCondensed-BoldItalic.ttf")
            ],
        },
    },
    {
        "family": "Cinzel",
        "category": "display",
        "license": "SIL OFL 1.1",
        "files": {
            "Cinzel-Variable.ttf": [_gf("ofl/cinzel/Cinzel%5Bwght%5D.ttf")],
        },
    },
    # --- Editorial & Documentary Sans (15) ---
    {
        "family": "Rubik",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "Rubik-Variable.ttf": [_gf("ofl/rubik/Rubik%5Bwght%5D.ttf")],
            "Rubik-Italic-Variable.ttf": [_gf("ofl/rubik/Rubik-Italic%5Bwght%5D.ttf")],
        },
    },
    {
        "family": "Space Grotesk",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "SpaceGrotesk-Variable.ttf": [_gf("ofl/spacegrotesk/SpaceGrotesk%5Bwght%5D.ttf")],
        },
    },
    {
        "family": "Inter",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "Inter-Variable.ttf": [_gf("ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf")],
            "Inter-Italic-Variable.ttf": [_gf("ofl/inter/Inter-Italic%5Bopsz%2Cwght%5D.ttf")],
        },
    },
    {
        "family": "Montserrat",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "Montserrat-Variable.ttf": [_gf("ofl/montserrat/Montserrat%5Bwght%5D.ttf")],
            "Montserrat-Italic-Variable.ttf": [
                _gf("ofl/montserrat/Montserrat-Italic%5Bwght%5D.ttf")
            ],
        },
    },
    {
        "family": "Plus Jakarta Sans",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "PlusJakartaSans-Variable.ttf": [
                _gf("ofl/plusjakartasans/PlusJakartaSans%5Bwght%5D.ttf")
            ],
            "PlusJakartaSans-Italic-Variable.ttf": [
                _gf("ofl/plusjakartasans/PlusJakartaSans-Italic%5Bwght%5D.ttf")
            ],
        },
    },
    {
        "family": "Roboto",
        "category": "sans",
        "license": "Apache-2.0",
        "files": {
            "Roboto-Variable.ttf": [
                _gf("ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf"),
                _gf("apache/roboto/static/Roboto-Regular.ttf"),
            ],
            "Roboto-Italic-Variable.ttf": [
                _gf("ofl/roboto/Roboto-Italic%5Bwdth%2Cwght%5D.ttf"),
                _gf("apache/roboto/static/Roboto-Italic.ttf"),
            ],
            "Roboto-Medium.ttf": [
                _gf("ofl/roboto/static/Roboto-Medium.ttf"),
                _gf("apache/roboto/static/Roboto-Medium.ttf"),
            ],
            "Roboto-Bold.ttf": [
                _gf("ofl/roboto/static/Roboto-Bold.ttf"),
                _gf("apache/roboto/static/Roboto-Bold.ttf"),
            ],
            "Roboto-Black.ttf": [
                _gf("ofl/roboto/static/Roboto-Black.ttf"),
                _gf("apache/roboto/static/Roboto-Black.ttf"),
            ],
            "Roboto-BoldItalic.ttf": [
                _gf("ofl/roboto/static/Roboto-BoldItalic.ttf"),
                _gf("apache/roboto/static/Roboto-BoldItalic.ttf"),
            ],
            "Roboto-BlackItalic.ttf": [
                _gf("ofl/roboto/static/Roboto-BlackItalic.ttf"),
                _gf("apache/roboto/static/Roboto-BlackItalic.ttf"),
            ],
        },
    },
    {
        "family": "Poppins",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "Poppins-Regular.ttf": [_gf("ofl/poppins/Poppins-Regular.ttf")],
            "Poppins-Medium.ttf": [_gf("ofl/poppins/Poppins-Medium.ttf")],
            "Poppins-SemiBold.ttf": [_gf("ofl/poppins/Poppins-SemiBold.ttf")],
            "Poppins-Bold.ttf": [_gf("ofl/poppins/Poppins-Bold.ttf")],
            "Poppins-ExtraBold.ttf": [_gf("ofl/poppins/Poppins-ExtraBold.ttf")],
            "Poppins-Black.ttf": [_gf("ofl/poppins/Poppins-Black.ttf")],
            "Poppins-Italic.ttf": [_gf("ofl/poppins/Poppins-Italic.ttf")],
            "Poppins-BoldItalic.ttf": [_gf("ofl/poppins/Poppins-BoldItalic.ttf")],
        },
    },
    {
        "family": "Outfit",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "Outfit-Variable.ttf": [_gf("ofl/outfit/Outfit%5Bwght%5D.ttf")],
        },
    },
    {
        "family": "DM Sans",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "DMSans-Variable.ttf": [_gf("ofl/dmsans/DMSans%5Bopsz%2Cwght%5D.ttf")],
            "DMSans-Italic-Variable.ttf": [
                _gf("ofl/dmsans/DMSans-Italic%5Bopsz%2Cwght%5D.ttf")
            ],
        },
    },
    {
        "family": "Manrope",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "Manrope-Variable.ttf": [_gf("ofl/manrope/Manrope%5Bwght%5D.ttf")],
        },
    },
    {
        "family": "Open Sans",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "OpenSans-Variable.ttf": [_gf("ofl/opensans/OpenSans%5Bwdth%2Cwght%5D.ttf")],
            "OpenSans-Italic-Variable.ttf": [
                _gf("ofl/opensans/OpenSans-Italic%5Bwdth%2Cwght%5D.ttf")
            ],
        },
    },
    {
        "family": "Lato",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "Lato-Regular.ttf": [_gf("ofl/lato/Lato-Regular.ttf")],
            "Lato-Bold.ttf": [_gf("ofl/lato/Lato-Bold.ttf")],
            "Lato-Black.ttf": [_gf("ofl/lato/Lato-Black.ttf")],
            "Lato-Italic.ttf": [_gf("ofl/lato/Lato-Italic.ttf")],
            "Lato-BoldItalic.ttf": [_gf("ofl/lato/Lato-BoldItalic.ttf")],
        },
    },
    {
        "family": "Nunito",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "Nunito-Variable.ttf": [_gf("ofl/nunito/Nunito%5Bwght%5D.ttf")],
            "Nunito-Italic-Variable.ttf": [_gf("ofl/nunito/Nunito-Italic%5Bwght%5D.ttf")],
        },
    },
    {
        "family": "Sora",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "Sora-Variable.ttf": [_gf("ofl/sora/Sora%5Bwght%5D.ttf")],
        },
    },
    {
        "family": "Work Sans",
        "category": "sans",
        "license": "SIL OFL 1.1",
        "files": {
            "WorkSans-Variable.ttf": [_gf("ofl/worksans/WorkSans%5Bwght%5D.ttf")],
            "WorkSans-Italic-Variable.ttf": [
                _gf("ofl/worksans/WorkSans-Italic%5Bwght%5D.ttf")
            ],
        },
    },
    # --- Editorial & Archival Serif (6) ---
    {
        "family": "EB Garamond",
        "category": "serif",
        "license": "SIL OFL 1.1",
        "files": {
            "EBGaramond-Variable.ttf": [_gf("ofl/ebgaramond/EBGaramond%5Bwght%5D.ttf")],
            "EBGaramond-Italic-Variable.ttf": [
                _gf("ofl/ebgaramond/EBGaramond-Italic%5Bwght%5D.ttf")
            ],
        },
    },
    {
        "family": "Playfair Display",
        "category": "serif",
        "license": "SIL OFL 1.1",
        "files": {
            "PlayfairDisplay-Variable.ttf": [
                _gf("ofl/playfairdisplay/PlayfairDisplay%5Bwght%5D.ttf")
            ],
            "PlayfairDisplay-Italic-Variable.ttf": [
                _gf("ofl/playfairdisplay/PlayfairDisplay-Italic%5Bwght%5D.ttf")
            ],
        },
    },
    {
        "family": "Lora",
        "category": "serif",
        "license": "SIL OFL 1.1",
        "files": {
            "Lora-Variable.ttf": [_gf("ofl/lora/Lora%5Bwght%5D.ttf")],
            "Lora-Italic-Variable.ttf": [_gf("ofl/lora/Lora-Italic%5Bwght%5D.ttf")],
        },
    },
    {
        "family": "Merriweather",
        "category": "serif",
        "license": "SIL OFL 1.1",
        "files": {
            "Merriweather-Variable.ttf": [
                _gf("ofl/merriweather/Merriweather%5Bopsz%2Cwdth%2Cwght%5D.ttf"),
                _gf("ofl/merriweather/Merriweather-Regular.ttf"),
            ],
            "Merriweather-Italic-Variable.ttf": [
                _gf("ofl/merriweather/Merriweather-Italic%5Bopsz%2Cwdth%2Cwght%5D.ttf"),
                _gf("ofl/merriweather/Merriweather-Italic.ttf"),
            ],
        },
    },
    {
        "family": "Libre Baskerville",
        "category": "serif",
        "license": "SIL OFL 1.1",
        "files": {
            "LibreBaskerville-Variable.ttf": [
                _gf("ofl/librebaskerville/LibreBaskerville%5Bwght%5D.ttf")
            ],
            "LibreBaskerville-Italic-Variable.ttf": [
                _gf("ofl/librebaskerville/LibreBaskerville-Italic%5Bwght%5D.ttf")
            ],
        },
    },
    {
        "family": "Instrument Serif",
        "category": "serif",
        "license": "SIL OFL 1.1",
        "files": {
            "InstrumentSerif-Regular.ttf": [
                _gf("ofl/instrumentserif/InstrumentSerif-Regular.ttf")
            ],
            "InstrumentSerif-Italic.ttf": [
                _gf("ofl/instrumentserif/InstrumentSerif-Italic.ttf")
            ],
        },
    },
    # --- Technical, Code & Dossier Mono (5) ---
    {
        "family": "Space Mono",
        "category": "mono",
        "license": "SIL OFL 1.1",
        "files": {
            "SpaceMono-Regular.ttf": [_gf("ofl/spacemono/SpaceMono-Regular.ttf")],
            "SpaceMono-Bold.ttf": [_gf("ofl/spacemono/SpaceMono-Bold.ttf")],
            "SpaceMono-Italic.ttf": [_gf("ofl/spacemono/SpaceMono-Italic.ttf")],
            "SpaceMono-BoldItalic.ttf": [_gf("ofl/spacemono/SpaceMono-BoldItalic.ttf")],
        },
    },
    {
        "family": "IBM Plex Mono",
        "category": "mono",
        "license": "SIL OFL 1.1",
        "files": {
            "IBMPlexMono-Regular.ttf": [_gf("ofl/ibmplexmono/IBMPlexMono-Regular.ttf")],
            "IBMPlexMono-Medium.ttf": [_gf("ofl/ibmplexmono/IBMPlexMono-Medium.ttf")],
            "IBMPlexMono-SemiBold.ttf": [_gf("ofl/ibmplexmono/IBMPlexMono-SemiBold.ttf")],
            "IBMPlexMono-Bold.ttf": [_gf("ofl/ibmplexmono/IBMPlexMono-Bold.ttf")],
            "IBMPlexMono-Italic.ttf": [_gf("ofl/ibmplexmono/IBMPlexMono-Italic.ttf")],
            "IBMPlexMono-BoldItalic.ttf": [_gf("ofl/ibmplexmono/IBMPlexMono-BoldItalic.ttf")],
        },
    },
    {
        "family": "JetBrains Mono",
        "category": "mono",
        "license": "SIL OFL 1.1",
        "files": {
            "JetBrainsMono-Variable.ttf": [
                _gf("ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf")
            ],
            "JetBrainsMono-Italic-Variable.ttf": [
                _gf("ofl/jetbrainsmono/JetBrainsMono-Italic%5Bwght%5D.ttf")
            ],
        },
    },
    {
        "family": "Source Code Pro",
        "category": "mono",
        "license": "SIL OFL 1.1",
        "files": {
            "SourceCodePro-Variable.ttf": [
                _gf("ofl/sourcecodepro/SourceCodePro%5Bwght%5D.ttf")
            ],
            "SourceCodePro-Italic-Variable.ttf": [
                _gf("ofl/sourcecodepro/SourceCodePro-Italic%5Bwght%5D.ttf")
            ],
        },
    },
    {
        "family": "Courier Prime",
        "category": "mono",
        "license": "SIL OFL 1.1",
        "files": {
            "CourierPrime-Regular.ttf": [_gf("ofl/courierprime/CourierPrime-Regular.ttf")],
            "CourierPrime-Bold.ttf": [_gf("ofl/courierprime/CourierPrime-Bold.ttf")],
            "CourierPrime-Italic.ttf": [_gf("ofl/courierprime/CourierPrime-Italic.ttf")],
            "CourierPrime-BoldItalic.ttf": [_gf("ofl/courierprime/CourierPrime-BoldItalic.ttf")],
        },
    },
    # --- Handwritten & Annotation (3) ---
    {
        "family": "Caveat",
        "category": "handwriting",
        "license": "SIL OFL 1.1",
        "files": {
            "Caveat-Variable.ttf": [_gf("ofl/caveat/Caveat%5Bwght%5D.ttf")],
        },
    },
    {
        "family": "Permanent Marker",
        "category": "handwriting",
        "license": "Apache-2.0",
        "files": {
            "PermanentMarker-Regular.ttf": [
                _gf("apache/permanentmarker/PermanentMarker-Regular.ttf")
            ],
        },
    },
    {
        "family": "Patrick Hand",
        "category": "handwriting",
        "license": "SIL OFL 1.1",
        "files": {
            "PatrickHand-Regular.ttf": [_gf("ofl/patrickhand/PatrickHand-Regular.ttf")],
        },
    },
]

# Static weight instantiations from variable TTFs so libass / FFmpeg renders full weights.
STATIC_DERIVATIONS: list[tuple[str, str, int, str]] = [
    ("SpaceGrotesk-Variable.ttf", "SpaceGrotesk-Bold.ttf", 700, "Space Grotesk"),
    ("Unbounded-Variable.ttf", "Unbounded-Bold.ttf", 700, "Unbounded"),
    ("Unbounded-Variable.ttf", "Unbounded-Black.ttf", 900, "Unbounded"),
    ("Inter-Variable.ttf", "Inter-SemiBold.ttf", 600, "Inter"),
    ("Inter-Variable.ttf", "Inter-Bold.ttf", 700, "Inter"),
    ("Inter-Italic-Variable.ttf", "Inter-Italic.ttf", 400, "Inter"),
    ("Montserrat-Variable.ttf", "Montserrat-Bold.ttf", 700, "Montserrat"),
    ("Montserrat-Variable.ttf", "Montserrat-Black.ttf", 900, "Montserrat"),
    ("Montserrat-Italic-Variable.ttf", "Montserrat-BoldItalic.ttf", 700, "Montserrat"),
    ("Rubik-Variable.ttf", "Rubik-Bold.ttf", 700, "Rubik"),
    ("Rubik-Variable.ttf", "Rubik-Black.ttf", 900, "Rubik"),
    ("Rubik-Italic-Variable.ttf", "Rubik-BoldItalic.ttf", 700, "Rubik"),
    ("PlusJakartaSans-Variable.ttf", "PlusJakartaSans-Bold.ttf", 700, "Plus Jakarta Sans"),
    ("PlusJakartaSans-Variable.ttf", "PlusJakartaSans-ExtraBold.ttf", 800, "Plus Jakarta Sans"),
    ("Oswald-Variable.ttf", "Oswald-Bold.ttf", 700, "Oswald"),
    ("EBGaramond-Variable.ttf", "EBGaramond-Bold.ttf", 700, "EB Garamond"),
    ("EBGaramond-Italic-Variable.ttf", "EBGaramond-Italic.ttf", 400, "EB Garamond"),
    ("PlayfairDisplay-Variable.ttf", "PlayfairDisplay-Bold.ttf", 700, "Playfair Display"),
    ("PlayfairDisplay-Italic-Variable.ttf", "PlayfairDisplay-Italic.ttf", 400, "Playfair Display"),
    ("Outfit-Variable.ttf", "Outfit-Bold.ttf", 700, "Outfit"),
    ("Outfit-Variable.ttf", "Outfit-ExtraBold.ttf", 800, "Outfit"),
    ("DMSans-Variable.ttf", "DMSans-Bold.ttf", 700, "DM Sans"),
    ("DMSans-Italic-Variable.ttf", "DMSans-BoldItalic.ttf", 700, "DM Sans"),
    ("Manrope-Variable.ttf", "Manrope-Bold.ttf", 700, "Manrope"),
    ("OpenSans-Variable.ttf", "OpenSans-Bold.ttf", 700, "Open Sans"),
    ("OpenSans-Italic-Variable.ttf", "OpenSans-Italic.ttf", 400, "Open Sans"),
    ("Nunito-Variable.ttf", "Nunito-Bold.ttf", 700, "Nunito"),
    ("Sora-Variable.ttf", "Sora-Bold.ttf", 700, "Sora"),
    ("WorkSans-Variable.ttf", "WorkSans-Bold.ttf", 700, "Work Sans"),
    ("Lora-Variable.ttf", "Lora-Bold.ttf", 700, "Lora"),
    ("Lora-Italic-Variable.ttf", "Lora-Italic.ttf", 400, "Lora"),
    ("LibreBaskerville-Variable.ttf", "LibreBaskerville-Bold.ttf", 700, "Libre Baskerville"),
    ("LibreBaskerville-Italic-Variable.ttf", "LibreBaskerville-Italic.ttf", 400, "Libre Baskerville"),
    ("Cinzel-Variable.ttf", "Cinzel-Bold.ttf", 700, "Cinzel"),
    ("Syne-Variable.ttf", "Syne-Bold.ttf", 700, "Syne"),
    ("Syne-Variable.ttf", "Syne-ExtraBold.ttf", 800, "Syne"),
    ("JetBrainsMono-Variable.ttf", "JetBrainsMono-Bold.ttf", 700, "JetBrains Mono"),
    ("SourceCodePro-Variable.ttf", "SourceCodePro-Bold.ttf", 700, "Source Code Pro"),
    ("Caveat-Variable.ttf", "Caveat-Bold.ttf", 700, "Caveat"),
]


def is_valid_font_bytes(data: bytes) -> bool:
    """Return True when raw bytes start with a valid TrueType/OpenType/collection magic."""
    return len(data) > 1024 and data[:4] in _VALID_FONT_MAGICS


def is_valid_font_file(path: Path) -> bool:
    """Validate that a font file on disk exists and starts with TTF/OTF magic bytes."""
    if not path.is_file() or path.stat().st_size <= 1024:
        return False
    with path.open("rb") as fh:
        head = fh.read(4)
    return head in _VALID_FONT_MAGICS


def _download_candidate(urls: list[str], dest: Path) -> tuple[str, str, str]:
    if is_valid_font_file(dest):
        return (dest.name, "cached", str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err = "no URLs"
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read()
            if not is_valid_font_bytes(data):
                last_err = f"invalid font header from {url} ({len(data)} bytes)"
                continue
            tmp = dest.with_suffix(dest.suffix + ".part")
            try:
                tmp.write_bytes(data)
                tmp.replace(dest)
            except Exception:
                tmp.unlink(missing_ok=True)
                raise
            return (dest.name, "downloaded", url)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = f"{url}: {exc}"
    return (dest.name, "failed", last_err)


def _derive_static_instances(fonts_dir: Path, allowed_families: set[str] | None) -> list[str]:
    try:
        from fontTools.ttLib import TTFont  # type: ignore[import-not-found]
        from fontTools.varLib.instancer import (  # type: ignore[import-not-found]
            instantiateVariableFont,
        )
    except ImportError:
        return []

    derived: list[str] = []
    for src_name, dst_name, wght, family in STATIC_DERIVATIONS:
        if allowed_families and family not in allowed_families:
            continue
        src = fonts_dir / src_name
        dst = fonts_dir / dst_name
        if is_valid_font_file(dst):
            derived.append(dst_name)
            continue
        if not is_valid_font_file(src):
            continue
        font = TTFont(str(src))
        if "fvar" not in font:
            continue
        # Pin every variable axis (e.g. opsz, wdth, wght) so libass receives a true static TTF.
        loc: dict[str, float] = {a.axisTag: float(a.defaultValue) for a in font["fvar"].axes}
        if "wght" not in loc:
            continue
        loc["wght"] = float(wght)
        static_font = instantiateVariableFont(font, loc, inplace=False, updateFontNames=False)
        is_italic = "italic" in dst_name.lower()
        is_bold = wght >= 700
        subfamily = (
            "Bold Italic"
            if (is_bold and is_italic)
            else ("Bold" if is_bold else ("Italic" if is_italic else "Regular"))
        )
        names = static_font["name"]
        for name_id in (2, 4, 6, 16, 17, 21, 22, 25):
            names.removeNames(nameID=name_id)
        names.setName(family, 1, 3, 1, 0x409)
        names.setName(subfamily, 2, 3, 1, 0x409)
        names.setName(f"{family} {subfamily}", 4, 3, 1, 0x409)
        names.setName(Path(dst_name).stem, 6, 3, 1, 0x409)
        static_font["OS/2"].usWeightClass = int(wght)
        fs_sel = static_font["OS/2"].fsSelection & ~0b1100001
        if is_italic:
            fs_sel |= 0b0000001
        if is_bold:
            fs_sel |= 0b0100000
        if not is_bold and not is_italic:
            fs_sel |= 0b1000000
        static_font["OS/2"].fsSelection = fs_sel
        mac_style = static_font["head"].macStyle & ~0b11
        if is_bold:
            mac_style |= 0b01
        if is_italic:
            mac_style |= 0b10
        static_font["head"].macStyle = mac_style
        tmp = dst.with_suffix(dst.suffix + ".part")
        try:
            static_font.save(str(tmp))
            tmp.replace(dst)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        derived.append(dst_name)
    return derived


def _write_fonts_conf(fonts_dir: Path) -> Path:
    conf_path = fonts_dir / "fonts.conf"
    xml = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
        "<fontconfig>\n"
        f"  <dir>{fonts_dir.resolve()}</dir>\n"
        "  <cachedir>/tmp/fontconfig-cache</cachedir>\n"
        "</fontconfig>\n"
    )
    conf_path.write_text(xml, encoding="utf-8")
    return conf_path


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _family_stem(family: str) -> str:
    return family.lower().replace(" ", "")


def list_installed_fonts(
    *,
    fonts_dir: Path = FONTS_DIR,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    """Inspect installed catalog fonts and local `.ttf`/`.otf` files."""
    cat_filter = {c.strip().lower() for c in (categories or []) if c.strip()}
    files_on_disk = (
        sorted(
            p
            for p in fonts_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".ttf", ".otf"}
        )
        if fonts_dir.is_dir()
        else []
    )
    by_name = {p.name: p for p in files_on_disk}
    static_by_family: dict[str, list[str]] = {}
    for _, dst_name, _, fam in STATIC_DERIVATIONS:
        static_by_family.setdefault(fam, []).append(dst_name)

    families_out: list[dict[str, Any]] = []
    matched_files: set[str] = set()
    for entry in FONT_CATALOG:
        cat = str(entry["category"])
        if cat_filter and cat not in cat_filter:
            continue
        fam = str(entry["family"])
        expected = list(entry["files"].keys()) + static_by_family.get(fam, [])
        stem = _family_stem(fam)
        present = sorted(
            {
                fn
                for fn in expected
                if fn in by_name
            }
            | {
                p.name
                for p in files_on_disk
                if p.name.lower().startswith(stem)
            }
        )
        matched_files.update(present)
        families_out.append(
            {
                "family": fam,
                "category": cat,
                "license": entry["license"],
                "installed": bool(present),
                "files": present,
                "expected_files": expected,
            }
        )

    installed_count = sum(1 for f in families_out if f["installed"])
    return {
        "fonts_dir": str(fonts_dir),
        "total_catalog_families": len(families_out),
        "installed_families": installed_count,
        "total_font_files": len(files_on_disk),
        "manifest_present": (fonts_dir / "FONTS_MANIFEST.json").is_file(),
        "families": families_out,
    }


def fetch_all_fonts(
    *,
    fonts_dir: Path = FONTS_DIR,
    categories: list[str] | None = None,
    derive_static: bool = True,
    max_workers: int = 8,
) -> dict[str, Any]:
    """Download catalog fonts, derive static instances, and write FONTS_MANIFEST.json."""
    cat_filter = {c.strip().lower() for c in (categories or []) if c.strip()}
    selected = [
        e for e in FONT_CATALOG if not cat_filter or str(e["category"]) in cat_filter
    ]
    if not selected:
        valid = sorted({str(e["category"]) for e in FONT_CATALOG})
        raise ValueError(f"No font families match categories={categories!r}; valid: {valid}")

    fonts_dir.mkdir(parents=True, exist_ok=True)
    tasks: list[tuple[str, list[str], Path]] = []
    for entry in selected:
        fam = str(entry["family"])
        for fname, urls in entry["files"].items():
            tasks.append((fam, list(urls), fonts_dir / fname))

    results: dict[str, list[dict[str, str]]] = {"downloaded": [], "cached": [], "failed": []}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {
            pool.submit(_download_candidate, urls, dest): (fam, dest.name)
            for fam, urls, dest in tasks
        }
        for fut in as_completed(futs):
            fam, _ = futs[fut]
            fname, status, detail = fut.result()
            results[status].append({"family": fam, "file": fname, "detail": detail})

    allowed_fams = {str(e["family"]) for e in selected}
    derived = _derive_static_instances(fonts_dir, allowed_fams) if derive_static else []
    conf_path = _write_fonts_conf(fonts_dir)

    all_files = sorted(
        p for p in fonts_dir.iterdir() if p.is_file() and p.suffix.lower() in {".ttf", ".otf"}
    )
    manifest_families: list[dict[str, Any]] = []
    static_by_family: dict[str, list[str]] = {}
    for _, dst_name, _, fam in STATIC_DERIVATIONS:
        static_by_family.setdefault(fam, []).append(dst_name)
    for entry in FONT_CATALOG:
        fam = str(entry["family"])
        stem = _family_stem(fam)
        fam_files = sorted(
            {
                p.name: p
                for p in all_files
                if p.name in entry["files"]
                or p.name in static_by_family.get(fam, [])
                or p.name.lower().startswith(stem)
            }.values(),
            key=lambda p: p.name,
        )
        manifest_families.append(
            {
                "family": fam,
                "category": entry["category"],
                "license": entry["license"],
                "files": [
                    {
                        "name": p.name,
                        "bytes": p.stat().st_size,
                        "sha256": _file_sha256(p),
                    }
                    for p in fam_files
                ],
            }
        )
    manifest_payload = {
        "schema_version": "1.0",
        "total_families": len(FONT_CATALOG),
        "installed_families": sum(1 for f in manifest_families if f["files"]),
        "total_files": len(all_files),
        "families": manifest_families,
    }
    (fonts_dir / "FONTS_MANIFEST.json").write_text(
        json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "ok": len(results["failed"]) == 0,
        "fonts_dir": str(fonts_dir),
        "fonts_conf": str(conf_path),
        "manifest": str(fonts_dir / "FONTS_MANIFEST.json"),
        "downloaded_count": len(results["downloaded"]),
        "cached_count": len(results["cached"]),
        "failed_count": len(results["failed"]),
        "derived_static_count": len(derived),
        "failed": sorted(results["failed"], key=lambda x: x["file"]),
        "installed_summary": list_installed_fonts(fonts_dir=fonts_dir, categories=categories),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch and verify the curated open-license font catalog for Geo & HyperFrames."
    )
    parser.add_argument(
        "--category",
        action="append",
        help="Optional category filter (display, sans, serif, mono, handwriting). Repeatable.",
    )
    parser.add_argument("--no-static", action="store_true", help="Skip variable->static derivation.")
    parser.add_argument("--list", action="store_true", help="List installed catalog fonts as JSON.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output (always JSON).")
    args = parser.parse_args(argv)
    del args.json

    if args.list:
        summary = list_installed_fonts(categories=args.category)
        sys.stdout.write(json.dumps(summary, indent=2) + "\n")
        return 0

    report = fetch_all_fonts(categories=args.category, derive_static=not args.no_static)
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
