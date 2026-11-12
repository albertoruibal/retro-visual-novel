"""ZX Spectrum 128K target (the original engine).

The byte-identical ZX pipeline still lives in tools/build.py; this module is
the registry adapter so the same dispatcher can build it alongside SMS/CPC.
The legacy ``zx`` id is accepted as an alias and canonicalised to ``zx128``.
"""
from __future__ import annotations

import scenefile

from .base import (BuildResult, Target, TargetOption,
                   art_margin_option, mono_option)


def _available():
    try:
        import build  # noqa: F401 - the dispatcher module owns build_env()
        return True, ""
    except Exception as err:                    # noqa: BLE001
        return False, str(err)


def _build(ctx):
    import build  # lazy: avoids a circular import while build.py loads targets

    results = build._build_zx128(ctx.slug)
    out = BuildResult(target="zx128")
    for item in results or []:
        out.add_output(item.get("path", ""), item.get("kind", ""),
                       item.get("size"))
    return out


def _validate(ctx):
    import build

    issues = []
    missing = build._z88dk_missing()
    if missing:
        issues.append({
            "level": "error", "section": "game", "id": "targets",
            "target": "zx128",
            "msg": "ZX Spectrum 128K: z88dk is missing " + ", ".join(missing),
        })
    return issues


TARGET = Target(
    id="zx128",
    label="ZX Spectrum 128K",
    description="Original NIRVANA+ engine, TAP and 128K SNA output.",
    outputs=(".tap", ".sna"),
    options=(
        TargetOption(
            "art_rows", "Art rows", "choice", 10,
            (8, 10, 12, 14, 16),
            "Height of the NIRVANA+ picture band; only even 8..16 rows are "
            "valid (256x8*rows pixels, default 10 = 256x80).",
            minimum=8, maximum=16, game_key="art_lines"),
        art_margin_option(),
        mono_option(),
        TargetOption(
            "dither", "Dithering", "choice", scenefile.DEFAULT_DITHER,
            scenefile.DITHER_MODES,
            help="How each 8x2 cell mixes its ink/paper colours: off snaps to "
                 "the nearest, ordered Bayer schemes are coarsest (2x2) to "
                 "finest (8x8), noise adds grain, and the error-diffusion "
                 "kernels (floyd, atkinson, jarvis, stucki, sierra) smooth "
                 "flat gradients."),
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
                 "title. 'text' (default) follows the Game tab's Text colour; "
                 "a Spectrum ink names an exact bright or dim colour."),
    ),
    build=_build,
    validate=_validate,
    available=_available,
    emulator="jsspeccy",
    machine="128",
    colors=16,
    engine="NIRVANA+",
    aliases=("zx",),
)
