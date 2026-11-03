"""Nintendo Game Boy Color (CGB) target.

``tools/gen_port.py --gb`` writes the portable scene/inventory blobs raw into
MBC1 banks (metadata stays in bank 0, scenes start at bank 1), converts art to
palette-aware 2bpp tile/map/attribute blobs in the banks above and packs the
converted PT3/APU song streams into the following banks.  ``plat_gb.c`` renders
the 20x18 text screen with the CGB colour palettes and draws the band;
``gb_copy.asm`` copies a selected bank's blob without a ZX0 decoder and
``gb_music.c`` streams the song from banked ROM.  The cartridge header is
patched to CGB-enhanced (0x80) so the same ``.gbc`` also boots on an original
monochrome Game Boy.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import tempfile

from .base import BuildResult, Target, TargetOption, portable_sources

CGB_ENHANCED_FLAG = 0x80


def _available():
    if importlib.util.find_spec("PIL") is None:
        return False, "Pillow is required for Game Boy Color art conversion"
    return True, ""


def _preview(path, conv, options, game=None):
    import gbart
    return gbart.preview_bytes(path, conv, options)


def _patch_cgb_header(path):
    """Mark the appmake cartridge as CGB-enhanced and refresh its checksums."""
    with open(path, "rb") as f:
        data = bytearray(f.read())
    data[0x143] = CGB_ENHANCED_FLAG
    data[0x14D] = 0
    data[0x14E] = 0
    data[0x14F] = 0
    chk = sum(data[0x134:0x14D]) & 0xFF
    data[0x14D] = (0xE7 - chk) & 0xFF
    total = sum(data) & 0xFFFF
    data[0x14E] = (total >> 8) & 0xFF
    data[0x14F] = total & 0xFF
    with open(path, "wb") as f:
        f.write(data)


def _guard_map(path):
    if not os.path.exists(path):
        return
    txt = open(path, encoding="utf-8", errors="replace").read()
    bad = []
    for sym in ("_main", "_plat_set_bank", "_port_unpack", "_gb_vram_copy",
                "_plat_draw_art", "_gb_music_vbl", "_gb_music_tick",
                "_gb_music_play", "_gb_music_stop", "_gb_music_byte",
                "_gb_music_write"):
        m = re.search(rf"^{re.escape(sym)}\s*=\s*\$([0-9A-Fa-f]+)", txt,
                      re.M)
        if m and int(m.group(1), 16) >= 0x4000:
            bad.append(sym)
    if bad:
        raise SystemExit(
            "Game Boy Color fixed-bank overflow: %s linked at or above "
            "0x4000; bank switching would replace the running code."
            % ", ".join(bad))
    m = re.search(r"^__BSS_END_tail\s*=\s*\$([0-9A-Fa-f]+)", txt, re.M)
    if m and int(m.group(1), 16) >= 0xE000:
        raise SystemExit("Game Boy Color RAM overflow: BSS reaches the stack "
                         "at 0xE000")


def _build(ctx):
    import build

    slug = ctx.slug
    build.run([ctx.py, os.path.join(ctx.root, "tools", "gen_port.py"),
               ctx.gdir, "--gb"], ctx.env)
    td = tempfile.mkdtemp(prefix=f".gbc-{slug}-", dir=ctx.bdir)
    try:
        sources = [
            os.path.join(ctx.root, "src", "gb", "gb_copy.asm"),
            os.path.join(ctx.root, "src", "gb", "gb_vram.asm"),
            *portable_sources(ctx.root),
            os.path.join(ctx.root, "src", "gb", "plat_gb.c"),
            os.path.join(ctx.root, "src", "gb", "gb_music.c"),
            os.path.join(ctx.root, "src", "portable", "plat.h"),
            os.path.join(ctx.bdir, "port_data.c"),
            os.path.join(ctx.bdir, "port_data.h"),
            os.path.join(ctx.bdir, "port_font2.h"),
            os.path.join(ctx.bdir, "port_gb_scene.asm"),
            os.path.join(ctx.bdir, "port_gb_art.asm"),
            os.path.join(ctx.bdir, "port_gb_song.asm"),
        ]
        names = build.stage_inputs(td, sources)
        names = [n for n in names if n.endswith((".c", ".asm"))]
        build.run(["zcc", "+gb", "-compiler=sdcc", "-create-app", "-m",
                   "-DPLAT_ROWS=18", "-I.", *names, "-o", slug],
                  ctx.env, cwd=td)
        produced = os.path.join(td, slug + ".gb")
        if not os.path.exists(produced):
            raise SystemExit("Game Boy Color build produced no cartridge")
        _guard_map(os.path.join(td, slug + ".map"))
        _patch_cgb_header(produced)
        path = os.path.join(ctx.gdir, slug + ".gbc")
        shutil.copyfile(produced, path)
    finally:
        shutil.rmtree(td, ignore_errors=True)
    result = BuildResult(target="gb")
    result.add_output(path, "gbc-rom", os.path.getsize(path))
    return result


def _validate(ctx):
    rows = int(ctx.options.get("art_rows") or 6)
    if rows not in (4, 6, 8):
        return [{"level": "error", "section": "game", "id": "targets",
                 "target": "gb",
                 "msg": f"Game Boy Color art_rows must be 4, 6 or 8 "
                        f"(got {rows})"}]
    return []


TARGET = Target(
    id="gb",
    label="Nintendo Game Boy Color",
    description="CGB-enhanced runtime with eight colour palettes, banked "
                "tile art, a 20x18 text screen and a B-button action dialog.",
    outputs=(".gbc",),
    options=(
        TargetOption("art_rows", "Art rows", "choice", 6, (4, 6, 8),
                     "Character rows of picture; 6 leaves 11 rows below it.",
                     minimum=4, maximum=8),
    ),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    emulator="gambatte",
    colors=32,
    engine="GBC tiles",
    band_width=160,
)
