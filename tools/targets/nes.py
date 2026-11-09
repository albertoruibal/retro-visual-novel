"""Nintendo Entertainment System target.

The runtime is the shared portable story engine on the NES PPU: 32x30
background tiles, two 4KB pattern tables per CHR bank (art plus normal font in
table 0, normal plus highlight font plus the collision tile in table 1), and a 32KB fixed PRG with the
compressed scene/inventory data resident.  The cartridge is MMC1 (mapper 1)
with 8KB CHR ROM banks and 8KB battery WRAM at $6000.  ``tools/gen_port.py
--nes`` writes the PRG tables and ``build/port_nes_chr.bin``; this target links
the code, patches the NES2.0
header, installs the custom NMI vector and appends the generated CHR banks.
cc65 (``cl65 -t nes``) is required.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import struct
import tempfile

import cc65path
import scenefile
from .base import BuildResult, Target, TargetOption, portable_sources

ART_ROWS = (6, 8, 10)
CHR_BANK = 0x2000
CHR_MAX_BANKS = 16


def _available():
    if importlib.util.find_spec("PIL") is None:
        return False, "Pillow is required for NES art conversion"
    if not cc65path.available():
        return False, "cc65 (cl65/ca65/ld65/cc65) is required for the NES build"
    return True, ""


def _preview(path, conv, options, game=None):
    import nesart
    return nesart.preview_bytes(path, conv, options, game)


def _build(ctx):
    import build

    slug = ctx.slug
    build.run([ctx.py, os.path.join(ctx.root, "tools", "gen_port.py"),
               ctx.gdir, "--nes"], ctx.env)
    chr_path = os.path.join(ctx.bdir, "port_nes_chr.bin")
    if not os.path.exists(chr_path):
        raise SystemExit("NES build produced no CHR bank image")
    chr_data = open(chr_path, "rb").read()
    banks = len(chr_data) // CHR_BANK
    if not banks or len(chr_data) != banks * CHR_BANK:
        raise SystemExit("NES CHR image is not a whole number of 8KB banks")
    if banks > CHR_MAX_BANKS:
        raise SystemExit("NES needs %d CHR banks; the MMC1 limit is %d"
                         % (banks, CHR_MAX_BANKS))

    td = tempfile.mkdtemp(prefix=f".nes-{slug}-", dir=ctx.bdir)
    try:
        sources = [
            os.path.join(ctx.root, "src", "nes", "nes_mmc1.s"),
            os.path.join(ctx.root, "src", "nes", "nes_ppu.s"),
            os.path.join(ctx.root, "src", "6502", "zx0.c"),
            *portable_sources(ctx.root),
            os.path.join(ctx.root, "src", "nes", "plat_nes.c"),
            os.path.join(ctx.root, "src", "portable", "plat.h"),
            os.path.join(ctx.bdir, "port_data.c"),
            os.path.join(ctx.bdir, "port_data.h"),
        ]
        names = build.stage_inputs(td, sources)
        compile_names = [n for n in names if n.endswith((".c", ".s"))]
        cmd = ["cl65", "-t", "nes", "-Oirs", "-DPLAT_ROWS=30", "-I.",
               "-m", slug + ".map", *compile_names, "-o", slug + ".nes"]
        build.run(cmd, ctx.env, cwd=td)
        produced = os.path.join(td, slug + ".nes")
        map_src = os.path.join(td, slug + ".map")
        map_dst = os.path.join(ctx.bdir, slug + ".nes.map")
        if os.path.exists(map_src):
            shutil.copyfile(map_src, map_dst)
        if not os.path.exists(produced):
            raise SystemExit("NES build produced no .nes file")
        if not os.path.exists(map_dst):
            raise SystemExit("NES build produced no link map")
        match = re.search(r"(?<![A-Za-z0-9_])_nes_nmi\s+([0-9A-Fa-f]{6})\b",
                          open(map_dst, encoding="utf-8").read())
        if not match:
            raise SystemExit("NES link map has no _nes_nmi symbol")
        nmi_addr = int(match.group(1), 16)
        if not 0x8000 <= nmi_addr < 0x10000:
            raise SystemExit("NES _nes_nmi is outside the PRG window")
        data = open(produced, "rb").read()
        if len(data) < 16 or data[:4] != b"NES\x1a":
            raise SystemExit("NES build did not produce an iNES/NES2.0 image")
        prg_pages = data[4]
        prg_size = prg_pages * 0x4000
        if prg_size != 0x8000:
            raise SystemExit("NES PRG is %d bytes; this target expects the "
                             "32KB fixed bank" % prg_size)
        header = bytearray(data[:16])
        # NES2.0: PRG count stays 2, CHR count becomes the generated bank
        # count, mapper low nibble becomes 1 (MMC1).
        header[5] = banks & 0xFF
        header[6] = (header[6] & 0x0F) | 0x10
        prg = bytearray(data[16:16 + prg_size])
        prg[0x7FFA] = nmi_addr & 0xFF
        prg[0x7FFB] = (nmi_addr >> 8) & 0xFF
        final = bytes(header) + bytes(prg) + chr_data
        path = os.path.join(ctx.gdir, slug + ".nes")
        with open(path, "wb") as f:
            f.write(final)
    finally:
        shutil.rmtree(td, ignore_errors=True)
    result = BuildResult(target="nes")
    result.add_output(path, "nes-rom", os.path.getsize(path))
    return result


def _validate(ctx):
    rows = int(ctx.options.get("art_rows") or 10)
    issues = []
    if rows not in ART_ROWS:
        issues.append({"level": "error", "section": "game", "id": "targets",
                       "target": "nes",
                       "msg": f"NES art_rows must be 6, 8 or 10 (got {rows})"})
    arts = len((ctx.doc or {}).get("arts") or [])
    if arts + 1 > CHR_MAX_BANKS:
        issues.append({"level": "error", "section": "game", "id": "targets",
                       "target": "nes",
                       "msg": f"NES supports at most {CHR_MAX_BANKS - 1} arts "
                              f"(8KB CHR banks); this game has {arts}"})
    return issues


TARGET = Target(
    id="nes",
    label="Nintendo Entertainment System",
    description="NES PPU background runtime with MMC1 CHR banks, 4-colour "
                "tile art and compressed story data in a 32KB PRG.",
    outputs=(".nes",),
    options=(
        TargetOption("art_rows", "Art rows", "choice", 10, ART_ROWS,
                     "Character rows of picture; 10 leaves 18 text rows.",
                     minimum=6, maximum=10),
        TargetOption("dither", "Dithering", "choice", scenefile.DEFAULT_DITHER,
                     scenefile.DITHER_BINARY_MODES,
                     help="off uses a hard four-colour snap; floyd uses "
                          "Floyd-Steinberg error diffusion."),
    ),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    emulator="emulatorjs-nes",
    colors=16,
    engine="NES PPU",
    band_width=256,
    aliases=("nintendo", "famicom"),
)
