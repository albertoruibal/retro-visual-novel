"""Commodore 64 target.

The runtime is the shared portable story engine on the VIC-II in multicolor
character mode: 40x25 text, 96 hi-res glyphs plus up to 160 multicolor art
tiles in the charset, and compressed scene/inventory/art blobs in the ``.prg``
decoded by the shared 6502 ZX0 C decoder.  The editor preview and the build
share ``tools/c64art.py``.  cc65 (``cl65 -t c64``) is required; z88dk has no
C64 target.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile

import cc65path
from .base import BuildResult, Target, TargetOption, portable_sources

ART_ROWS = (4, 6, 8, 10)
# A .prg with a 2-byte load address at $0801 must end below the display at
# $A000: the last byte is $0800 + (size - 2), so size <= $9801.
PRG_MAX = 0x9801


def _available():
    if importlib.util.find_spec("PIL") is None:
        return False, "Pillow is required for Commodore 64 art conversion"
    if not cc65path.available():
        return False, "cc65 (cl65/ca65/ld65/cc65) is required for the C64 build"
    return True, ""


def _preview(path, conv, options, game=None):
    import c64art
    return c64art.preview_bytes(path, conv, options, game)


def _guard(path):
    size = os.path.getsize(path)
    if size > PRG_MAX:
        raise SystemExit(
            "Commodore 64 main image is %d bytes; it must end below $A000 "
            "(max %d incl. the 2-byte load address). Lower c64 art_rows, "
            "remove arts or shorten the story." % (size, PRG_MAX))
    with open(path, "rb") as f:
        head = f.read(2)
    if head != b"\x01\x08":
        raise SystemExit("Commodore 64 build did not produce a $0801 .prg")


def _build(ctx):
    import build

    slug = ctx.slug
    build.run([ctx.py, os.path.join(ctx.root, "tools", "gen_port.py"),
               ctx.gdir, "--c64"], ctx.env)
    td = tempfile.mkdtemp(prefix=f".c64-{slug}-", dir=ctx.bdir)
    try:
        sources = [
            os.path.join(ctx.root, "src", "c64", "c64_hw.s"),
            os.path.join(ctx.root, "src", "6502", "zx0.c"),
            *portable_sources(ctx.root),
            os.path.join(ctx.root, "src", "c64", "plat_c64.c"),
            os.path.join(ctx.root, "src", "portable", "plat.h"),
            os.path.join(ctx.bdir, "port_data.c"),
            os.path.join(ctx.bdir, "port_data.h"),
            os.path.join(ctx.bdir, "port_font8.h"),
            os.path.join(ctx.root, "src", "c64", "c64.cfg"),
        ]
        names = build.stage_inputs(td, sources)
        compile_names = [n for n in names if n.endswith((".c", ".s"))]
        cmd = ["cl65", "-t", "c64", "-C", "c64.cfg", "-Oirs",
               "-DPLAT_ROWS=25", "-I.", "-m", slug + ".map",
               *compile_names, "-o", slug + ".prg"]
        build.run(cmd, ctx.env, cwd=td)
        produced = os.path.join(td, slug + ".prg")
        if os.path.exists(os.path.join(td, slug + ".map")):
            shutil.copyfile(os.path.join(td, slug + ".map"),
                            os.path.join(ctx.bdir, slug + ".c64.map"))
        if not os.path.exists(produced):
            raise SystemExit("Commodore 64 build produced no .prg file")
        _guard(produced)
        path = os.path.join(ctx.gdir, slug + ".prg")
        shutil.copyfile(produced, path)
    finally:
        shutil.rmtree(td, ignore_errors=True)
    result = BuildResult(target="c64")
    result.add_output(path, "c64-prg", os.path.getsize(path))
    return result


def _validate(ctx):
    rows = int(ctx.options.get("art_rows") or 6)
    if rows not in ART_ROWS:
        return [{"level": "error", "section": "game", "id": "targets",
                 "target": "c64",
                 "msg": f"Commodore 64 art_rows must be 4, 6, 8 or 10 "
                        f"(got {rows})"}]
    return []


TARGET = Target(
    id="c64",
    label="Commodore 64",
    description="C64 VIC-II multicolor-character runtime: 40x25 hi-res text, "
                "160px multicolor art, compressed data in one .prg.",
    outputs=(".prg",),
    options=(
        TargetOption("art_rows", "Art rows", "choice", 6, ART_ROWS,
                     "Character rows of picture; 6 leaves 18 text rows.",
                     minimum=4, maximum=10),
    ),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    emulator="",
    colors=16,
    engine="VIC-II MCM",
    band_width=320,
    aliases=("commodore64",),
)
