"""Nintendo Entertainment System target.

The runtime is the shared portable story engine on the NES PPU: 32x30
background tiles, two 4KB pattern tables per CHR bank (art plus normal font in
table 0, normal plus highlight font in table 1).  The custom ``src/nes/nes.cfg``
puts all code in the fixed last PRG bank and the compressed story/art blobs in
switchable bank 0; converted song streams fill the banks in between.  The
cartridge is MMC1 (mapper 1) with 8KB CHR ROM banks and 8KB battery WRAM at
$6000.  ``tools/gen_port.py --nes`` writes the PRG tables,
``build/port_nes_chr.bin`` and ``build/port_nes_song.bin``; this target links
the code, assembles the PRG banks, patches the iNES header, installs the
custom NMI vector and appends the generated CHR banks.  cc65 (``cl65 -t nes``)
is required.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import tempfile

import cc65path
import scenefile
from .base import (BuildResult, Target, TargetOption,
                   art_margin_option, mono_option,
                   portable_sources)

ART_ROWS = (8, 10, 12)
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


def _map_segment_end(text, name):
    m = re.search(rf"^{name}\s+([0-9A-Fa-f]{{6}})\s+([0-9A-Fa-f]{{6}})",
                  text, re.M)
    return int(m.group(2), 16) if m else None


def _map_symbol(text, name):
    m = re.search(rf"\b{re.escape(name)}\s+([0-9A-Fa-f]{{6}})\b", text)
    return int(m.group(1), 16) if m else None


def _guard_map(path):
    text = open(path, encoding="utf-8").read()
    rod = _map_segment_end(text, "RODATA")
    if rod is not None and rod >= 0xC000:
        raise SystemExit(
            "NES story/art data reaches 0x%04X; bank 0 at $8000-$BFFF holds "
            "only 16KB. Lower nes art_rows, remove arts or shorten the story."
            % rod)
    fixed = ("_nes_nmi", "_nes_audio_tick", "_nes_music_play",
             "_nes_music_stop", "_nes_prg_bank", "_plat_sfx", "_port_unpack",
             "_plat_draw_art", "_plat_read_key", "_main")
    bad = []
    for sym in fixed:
        addr = _map_symbol(text, sym)
        if addr is not None and not 0xC000 <= addr < 0x10000:
            bad.append(sym)
    if bad:
        raise SystemExit(
            "NES fixed-bank overflow: %s linked below $C000; PRG bank "
            "switching would replace the running code." % ", ".join(bad))


def _build(ctx):
    import build

    slug = ctx.out_stem
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

    song_path = os.path.join(ctx.bdir, "port_nes_song.bin")
    song_data = open(song_path, "rb").read() if os.path.exists(song_path) else b""
    if len(song_data) % 0x4000:
        raise SystemExit("NES song bank image is not a whole number of 16KB banks")
    song_banks = len(song_data) // 0x4000

    td = tempfile.mkdtemp(prefix=f".nes-{slug}-", dir=ctx.bdir)
    try:
        sources = [
            os.path.join(ctx.root, "src", "nes", "nes_mmc1.s"),
            os.path.join(ctx.root, "src", "nes", "nes_ppu.s"),
            os.path.join(ctx.root, "src", "nes", "nes_audio_tick.s"),
            os.path.join(ctx.root, "src", "nes", "nes_music.c"),
            os.path.join(ctx.root, "src", "nes", "nes_sfx.c"),
            os.path.join(ctx.root, "src", "6502", "zx0.c"),
            *portable_sources(ctx.root),
            os.path.join(ctx.root, "src", "nes", "plat_nes.c"),
            os.path.join(ctx.root, "src", "portable", "plat.h"),
            os.path.join(ctx.bdir, "port_data.c"),
            os.path.join(ctx.bdir, "port_data.h"),
            os.path.join(ctx.root, "src", "nes", "nes.cfg"),
        ]
        names = build.stage_inputs(td, sources)
        compile_names = [n for n in names if n.endswith((".c", ".s"))]
        cmd = ["cl65", "-t", "nes", "-C", "nes.cfg", "-Oirs",
               "-DPLAT_ROWS=30", "-I.", "-m", slug + ".map",
               *compile_names, "-o", slug + ".nes"]
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
        _guard_map(map_dst)
        data = open(produced, "rb").read()
        if len(data) < 16 or data[:4] != b"NES\x1a":
            raise SystemExit("NES build did not produce an iNES image")
        prg_pages = data[4]
        prg_size = prg_pages * 0x4000
        if prg_size != 0x8000:
            raise SystemExit("NES linker image is %d bytes; the custom layout "
                             "expects the 16KB story bank plus the fixed bank"
                             % prg_size)
        image = data[16:16 + 0x8000]
        if len(image) != 0x8000:
            raise SystemExit("NES linker image is truncated")
        bank0 = image[:0x4000]
        fixed = image[0x4000:]
        reset = fixed[0x3FFC] | (fixed[0x3FFD] << 8)
        if not 0xC000 <= reset < 0x10000:
            raise SystemExit("NES reset vector 0x%04X is outside the fixed "
                             "bank" % reset)

        total = 1
        while total < 2 + song_banks:
            total <<= 1
        if total > 16:
            raise SystemExit(
                "NES needs %d PRG banks; MMC1 16KB mode addresses at most 16. "
                "Shorten or remove songs." % (2 + song_banks))
        padding = total - 2 - song_banks
        final_prg = bytearray(bank0 + song_data + bytes(padding * 0x4000) + fixed)

        header = bytearray(data[:16])
        header[4] = total
        header[5] = banks & 0xFF
        header[6] = (header[6] & 0x0F) | 0x10
        match = re.search(r"(?<![A-Za-z0-9_])_nes_nmi\s+([0-9A-Fa-f]{6})\b",
                          open(map_dst, encoding="utf-8").read())
        if not match:
            raise SystemExit("NES link map has no _nes_nmi symbol")
        nmi_addr = int(match.group(1), 16)
        if not 0xC000 <= nmi_addr < 0x10000:
            raise SystemExit("NES _nes_nmi is outside the fixed bank")
        vector = (total - 1) * 0x4000 + 0x3FFA
        final_prg[vector] = nmi_addr & 0xFF
        final_prg[vector + 1] = (nmi_addr >> 8) & 0xFF
        final = bytes(header) + final_prg + chr_data
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
                       "msg": f"NES art_rows must be 8, 10 or 12 (got {rows})"})
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
    description="NES PPU background runtime with MMC1 PRG/CHR banks, "
                "4-colour tile art, compressed story data and NES APU music.",
    outputs=(".nes",),
    options=(
        TargetOption("art_rows", "Art rows", "choice", 10, ART_ROWS,
                     "Character rows of picture; 12 leaves 16 text rows.",
                     minimum=8, maximum=12),
        art_margin_option(),
        mono_option(),
        TargetOption("dither", "Dithering", "choice", scenefile.DEFAULT_DITHER,
                     scenefile.DITHER_MODES,
                     help="off snaps to the nearest of each block's four "
                          "colours; bayer2/bayer4/bayer8 and noise "
                          "ordered-dither them; floyd, atkinson, jarvis, "
                          "stucki and sierra diffuse the error."),
    ),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    emulator="emulatorjs-nes",
    colors=10,
    engine="NES PPU",
    band_width=256,
    aliases=("nintendo", "famicom"),
)
