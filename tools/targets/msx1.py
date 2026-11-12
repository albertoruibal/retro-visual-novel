"""MSX1 target (TMS9918A Graphics II).

The editor preview and the .rom build share ``tools/msx1art.py``.  SCREEN 2
is a 32x24 tile display: the art band is 256 x (8*art_rows) pixels with two
TMS9918 colours per 8x1 cell row, above a 32-column text pane.  Scene data lives
in ASCII16 ROM bank 1 and each art uses one 16K bank; the shared 8x8 font gets
the bank after the art.  The ``mono`` system option renders the picture as a
dithered white-on-black band instead of the 15-colour palette.
"""
from __future__ import annotations

import importlib.util
import os
import re

import scenefile

from .base import (BuildResult, Target, TargetOption, art_margin_option,
                   portable_sources)


def _available():
    if importlib.util.find_spec("PIL") is None:
        return False, "Pillow is required for MSX1 art conversion"
    return True, ""


def _preview(path, conv, options, game=None):
    import msx1art
    mono = bool((conv or {}).get("mono") or options.get("mono"))
    _text, _highlight, text_bg = msx1art.text_colours(game, mono)
    return msx1art.preview_bytes(path, conv, options, text_bg, mono)


def _build(ctx):
    import os
    import shutil
    import tempfile
    import build

    slug = ctx.slug
    build.run([ctx.py, os.path.join(ctx.root, "tools", "gen_port.py"),
               ctx.gdir, "--msx1"], ctx.env)
    td = tempfile.mkdtemp(prefix=f".msx1-{slug}-", dir=ctx.bdir)
    try:
        sources = [
            *portable_sources(ctx.root),
            os.path.join(ctx.root, "src", "msx1", "plat_msx1.c"),
            os.path.join(ctx.root, "src", "portable", "plat.h"),
            os.path.join(ctx.root, "src", "msx1", "msx1_vram.asm"),
            os.path.join(ctx.root, "src", "z80", "zx0_wrap.asm"),
            os.path.join(ctx.root, "vendor", "zx0", "zx0.asm"),
            os.path.join(ctx.bdir, "port_data.c"),
            os.path.join(ctx.bdir, "port_data.h"),
            os.path.join(ctx.bdir, "port_art.asm"),
            os.path.join(ctx.bdir, "port_font.asm"),
        ]
        names = build.stage_inputs(td, sources)
        names = [n for n in names if n.endswith((".c", ".asm"))]
        build.run(["zcc", "+msx", "-subtype=rom", "-create-app", "-m",
                   "-pragma-define:MAPPER_ASCII16", "-DPLAT_ROWS=24",
                   "-I.", *names, "-o", slug], ctx.env, cwd=td)
        produced = os.path.join(td, slug + ".rom")
        if not os.path.exists(produced):
            raise SystemExit("MSX1 build produced no .rom file")
        _guard_map(os.path.join(td, slug + ".map"))
        path = os.path.join(ctx.gdir, slug + "-msx1.rom")
        shutil.copyfile(produced, path)
    finally:
        shutil.rmtree(td, ignore_errors=True)
    result = BuildResult(target="msx1")
    result.add_output(path, "msx1-rom", os.path.getsize(path))
    return result


def _guard_map(path):
    """ASCII16 keeps resident code in the first 16K page."""
    if not os.path.exists(path):
        return
    txt = open(path, encoding="utf-8", errors="replace").read()
    bad = []
    for sym in ("_main", "_plat_draw_art", "_plat_set_bank", "_port_unpack",
                "_zx0_unpack"):
        m = re.search(rf"^{re.escape(sym)}\s*=\s*\$([0-9A-Fa-f]+)", txt,
                      re.M)
        if m and int(m.group(1), 16) >= 0x8000:
            bad.append(sym)
    if bad:
        raise SystemExit(
            "MSX1 home-region overflow: %s linked at or above 0x8000; the "
            "ASCII16 art bank would page over the running code." %
            ", ".join(bad))
    rom_end = 0
    for m in re.finditer(
            r"^__(?:code|rodata)_[A-Za-z0-9_]*_tail\s*=\s*\$([0-9A-Fa-f]+)",
            txt, re.M | re.IGNORECASE):
        addr = int(m.group(1), 16)
        if addr < 0x10000:
            rom_end = max(rom_end, addr)
    if rom_end > 0x8000:
        raise SystemExit(
            "MSX1 main ROM reaches 0x%04X; the fixed 16 KB bank must stay "
            "below 0x8000. Shorten the game or move resident data into a "
            "bank." % rom_end)


def _validate(ctx):
    issues = []
    rows = int(ctx.options.get("art_rows") or 10)
    if rows not in (8, 10, 12):
        issues.append({"level": "error", "section": "game", "id": "targets",
                       "target": "msx1",
                       "msg": f"MSX1 art_rows must be 8, 10 or 12 (got {rows})"})
    if (ctx.doc or {}).get("game", {}).get("songs"):
        issues.append({
            "level": "warn", "section": "game", "id": "targets",
            "target": "msx1",
            "msg": "MSX1 has no music player yet; songs are ignored in this "
                   "build (use the MSX2 target for music).",
        })
    return issues


TARGET = Target(
    id="msx1",
    label="MSX1 (TMS9918A)",
    description="MSX1 SCREEN 2 runtime: 256x192 tile art, 32-column text and "
                "an optional black-and-white picture.",
    outputs=(".rom",),
    options=(
        TargetOption("art_rows", "Art rows", "choice", 10, (8, 10, 12),
                     "Character rows of picture above the text pane.",
                     minimum=8, maximum=12),
        art_margin_option(),
        TargetOption("mono", "Black and white", "bool", False,
                     help="Convert the picture to a dithered white-on-black "
                          "1-bit band and force white text, instead of the "
                          "TMS9918A's 15-colour palette."),
        TargetOption("dither", "Dithering", "choice", scenefile.DEFAULT_DITHER,
                     scenefile.DITHER_MODES,
                     help="Colour art dithers between each 8x1 row's ink and "
                          "paper; Black and white substitutes a 2x2 Bayer "
                          "dither for off. bayer2/bayer4/bayer8 and noise "
                          "are ordered schemes; floyd, atkinson, jarvis, "
                          "stucki and sierra diffuse the error."),
        TargetOption("menu", "Pop-up options", "bool", False,
                     help="Use the SPACE-key or joystick button 2 dialog "
                          "instead of pinned options and the inventory row.",
                     on_value="popup", off_value="inline"),
    ),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    emulator="webmsx",
    machine="MSX1",
    colors=15,
    engine="TMS9918A",
    band_width=256,
    artifact_suffix="-msx1",
)
