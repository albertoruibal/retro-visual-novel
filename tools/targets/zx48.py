"""ZX Spectrum 48K target.

A non-paged NIRVANA+ build: all compressed art/scene/inventory data must fit
the 48K's lower RAM (0x6000-0x7BFF, 7168 bytes) and the main image must stay
below the engine at 0xDC03. A game that does not fit fails the build with a
clear message instead of producing a corrupt TAP.

The 48K has no AY sound chip, so songs declared in ``game.md`` are ignored by
this target (the Systems tab says so and validation warns about it).
"""
from __future__ import annotations

import scenefile

from .base import BuildResult, Target, TargetOption


def _available():
    try:
        import build  # noqa: F401 - the dispatcher module owns build_env()
        return True, ""
    except Exception as err:                    # noqa: BLE001
        return False, str(err)


def _build(ctx):
    import build  # lazy: avoids a circular import while build.py loads targets

    results = build._build_zx48(ctx.slug)
    out = BuildResult(target="zx48")
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
            "target": "zx48",
            "msg": "ZX Spectrum 48K: z88dk is missing " + ", ".join(missing),
        })
    rows = int(ctx.options.get("art_rows") or 10)
    if rows not in (8, 10, 12, 14, 16):
        issues.append({
            "level": "error", "section": "game", "id": "targets",
            "target": "zx48",
            "msg": f"ZX Spectrum 48K art_rows must be an even 8..16 "
                   f"(got {rows})",
        })
    if (ctx.doc or {}).get("game", {}).get("songs"):
        issues.append({
            "level": "warn", "section": "game", "id": "targets",
            "target": "zx48",
            "msg": "ZX Spectrum 48K has no AY sound chip; songs are ignored "
                   "in this build (use the 128K target for music).",
        })
    return issues


TARGET = Target(
    id="zx48",
    label="ZX Spectrum 48K",
    description="NIRVANA+ engine for 48K machines. No banked storage and "
                "no AY music: songs declared in game.md are ignored by this "
                "build. The story must fit 7 KB of compressed art/scene data "
                "plus a main image below 0xDC03, or the build fails.",
    outputs=(".tap",),
    options=(
        TargetOption(
            "art_rows", "Art rows", "choice", 10,
            (8, 10, 12, 14, 16),
            "Height of the NIRVANA+ picture band, shared with the 128K "
            "target; only even 8..16 rows are valid (256x8*rows pixels, "
            "default 10 = 256x80).",
            minimum=8, maximum=16, game_key="art_lines"),
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
    machine="48",
    colors=16,
    engine="NIRVANA+",
    artifact_suffix="-48k",
)
