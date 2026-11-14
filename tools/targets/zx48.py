"""ZX Spectrum 48K target.

A non-paged build with no NIRVANA+ engine. Scene blobs live in the lower-RAM
flat store at 0x6000 (7168 bytes); dithered 1bpp art (or classic-attribute
colour art when Black and white is off) and the inventory blob are compiled
into the main image, which may now use
0x8000-0xFFFF. A game that does not fit fails the build with a clear message
instead of producing a corrupt TAP.

The 48K has no AY sound chip, so songs declared in ``game.md`` are ignored by
this target (the Systems tab says so and validation warns about it).
"""
from __future__ import annotations

import scenefile

from .base import BuildResult, Target, TargetOption, art_margin_option


def _available():
    try:
        import build  # noqa: F401 - the dispatcher module owns build_env()
        return True, ""
    except Exception as err:                    # noqa: BLE001
        return False, str(err)


def _preview(src, conv, options, game=None):
    import io

    import zxart
    from PIL import Image

    conv = conv or {}
    rows = int(options.get("art_rows") or 10) // 2
    im = Image.open(src).convert("RGB")
    # The crop box follows the primary ZX band; re-fit an explicit crop to the
    # 48K aspect instead of stretching it when the two bands differ.
    flat_conv = conv
    if conv.get("crop"):
        im = zxart.crop_for_band(im, conv["crop"], rows)
        flat_conv = dict(conv)
        flat_conv["crop"] = None
    mono = bool(conv.get("mono")) if conv and "mono" in conv \
        else bool(options.get("mono"))
    if mono:
        img = zxart.mono_image(
            im, crop=flat_conv.get("crop"),
            dither=flat_conv.get("dither", "off"), rows=rows,
            adjust=flat_conv.get("adjust"),
            palette=flat_conv.get("palette", "none"),
            palette_colors=flat_conv.get("palette_colors"),
            margin=flat_conv.get("margin", 0), fill=(0, 0, 0))
    else:
        img = zxart.grid_to_rgb_image(zxart.classic_band(
            im, crop=flat_conv.get("crop"),
            dither=flat_conv.get("dither", "off"), rows=rows,
            adjust=flat_conv.get("adjust"),
            palette=flat_conv.get("palette", "none"),
            palette_colors=flat_conv.get("palette_colors"),
            margin=flat_conv.get("margin", 0), fill=(0, 0, 0)))
    img = zxart.preview_margin_crop(img, conv.get("margin", 0),
                                    zxart.BAND_W, zxart.band_h(rows))
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def _build(ctx):
    import build  # lazy: avoids a circular import while build.py loads targets

    results = build._build_zx48(ctx)
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
    description="Non-paged 48K build with classic mono or attribute-colour "
                "art, no NIRVANA+ engine and no AY music: songs declared in "
                "game.md are ignored. Scenes fit 7 KB of lower RAM; art and "
                "inventory are compiled into the main image, or the build "
                "fails.",
    outputs=(".tap",),
    options=(
        TargetOption(
            "art_rows", "Art rows", "choice", 10,
            (8, 10, 12, 14, 16),
            "Height of the monochrome picture band, independent of the 128K "
            "target; only even 8..16 rows are valid (256x8*rows pixels, "
            "default 10 = 256x80).",
            minimum=8, maximum=16),
        art_margin_option(),
        TargetOption(
            "mono", "Black and white", "bool", True,
            help="Render the picture as a dithered black-and-white band. The "
                 "title, text and menu options keep the Game tab's colours. "
                 "Turn it off for classic attribute-colour art."),
        TargetOption(
            "dither", "Dithering", "choice", scenefile.DEFAULT_DITHER,
            scenefile.DITHER_MODES,
            help="Colour art dithers between each 8x8 cell's ink and paper; "
                 "off snaps to the nearer one. The 1-bit mono band cannot "
                 "honour off, so it becomes a 2x2 Bayer dither. Every ordered "
                 "and error-diffusion scheme is available; coarser ordered "
                 "schemes compress best."),
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
    preview=_preview,
    available=_available,
    emulator="jsspeccy",
    machine="48",
    colors=15,
    engine="Classic attributes",
    artifact_suffix="-48k",
)
