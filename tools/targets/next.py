"""ZX Spectrum Next target.

The runtime is a native Next build: the shared portable story engine, a ULA
text layer, Layer 2 256-colour art and the Next's AY player.  ``tools/gen_port.py
--next`` writes the scene/art/song banks and the generated tables; the build
links them with ``zcc +zxn -clib=classic -subtype=nex``.
"""
from __future__ import annotations

import importlib.util

import scenefile

from .base import (BuildResult, Target, TargetOption,
                   art_margin_option, mono_option)


def _available():
    if importlib.util.find_spec("PIL") is None:
        return False, "Pillow is required for ZX Next art conversion"
    return True, ""


def _preview(path, conv, options, game=None):
    import nextart
    return nextart.preview_bytes(path, conv, options, game)


def _build(ctx):
    import build

    results = build._build_next(ctx)
    out = BuildResult(target="next")
    for item in results or []:
        out.add_output(item.get("path", ""), item.get("kind", ""),
                       item.get("size"))
    return out


def _validate(ctx):
    issues = []
    rows = int(ctx.options.get("art_rows") or 10)
    if rows not in (8, 10, 12, 14, 16):
        issues.append({
            "level": "error", "section": "game", "id": "targets",
            "target": "next",
            "msg": f"ZX Next art_rows must be an even 8..16 (got {rows})",
        })
    import build
    missing = build._z88dk_missing()
    if missing:
        issues.append({
            "level": "error", "section": "game", "id": "targets",
            "target": "next",
            "msg": "ZX Next: z88dk is missing " + ", ".join(missing),
        })
    return issues


TARGET = Target(
    id="next",
    label="ZX Spectrum Next",
    description="Native Next build with Layer 2 256-colour art, 2 MB banks "
                "and the shared AY music player. Outputs a .nex.",
    outputs=(".nex",),
    options=(
        TargetOption(
            "art_rows", "Art rows", "choice", 10,
            (8, 10, 12, 14, 16),
            "Height of the Layer 2 picture band in 8px rows (256x8*rows "
            "pixels, default 10 = 256x80).",
            minimum=8, maximum=16),
        art_margin_option(),
        mono_option(),
        TargetOption(
            "dither", "Dithering", "choice", scenefile.DEFAULT_DITHER,
            scenefile.DITHER_MODES,
            help="off uses a hard nearest-colour snap; bayer2/bayer4/bayer8 "
                 "and noise ordered-dither the palette; floyd, atkinson, "
                 "jarvis, stucki and sierra diffuse the error."),
        TargetOption(
            "menu", "Pop-up options", "bool", False,
            help="Show scene options and held items in a SPACE-key dialog "
                 "instead of the pinned option list and row-23 inventory band.",
            on_value="popup", off_value="inline"),
        TargetOption(
            "title_ink", "Title colour", "choice",
            scenefile.TITLE_INK_INHERIT,
            scenefile.TITLE_INK_TOKENS,
            help="Colour of the scene title on row 0 and the item screen's "
                 "title. 'text' (default) follows the Game tab's Text colour."),
    ),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    engine="Layer 2",
    colors=256,
    band_width=256,
)
