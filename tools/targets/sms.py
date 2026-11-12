"""Sega Master System target.

The editor preview and the .sms build share ``tools/smsart.py``.  The runtime
is the portable scene engine plus a VDP text/art layer; each art is stored
uncompressed in its own Sega-mapper ROM bank.
"""
from __future__ import annotations

import importlib.util
import os
import re

import scenefile

from .base import (BuildResult, Target, TargetOption,
                   art_margin_option, mono_option,
                   portable_sources)


def _available():
    if importlib.util.find_spec("PIL") is None:
        return False, "Pillow is required for SMS art conversion"
    return True, ""


def _n_songs(bdir):
    path = os.path.join(bdir, "port_data.h")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read()
    except OSError:
        return 0
    m = re.search(r"^#define N_SONGS (\d+)", head, re.M)
    return int(m.group(1)) if m else 0


def _guard_map(path):
    """Keep resident code below the data-bank window and BSS off the stack."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        txt = f.read()
    bad = []
    for sym in ("_z80_rst_38h", "_sms_psg_play", "_sms_psg_stop",
                "_sms_detect_region", "_port_unpack", "_zx0_unpack",
                "asm_PSGlib_Frame", "asm_PSGlib_Play", "asm_PSGlib_Stop"):
        m = re.search(rf"^{re.escape(sym)}\s*=\s*\$([0-9A-Fa-f]+)", txt, re.M)
        if m and int(m.group(1), 16) >= 0x8000:
            bad.append(sym)
    if bad:
        raise SystemExit(
            "SMS resident overflow: %s linked at or above 0x8000; the "
            "switchable ROM bank would cover it." % ", ".join(bad))
    m = re.search(r"^__BSS_END_tail\s*=\s*\$([0-9A-Fa-f]+)", txt, re.M)
    if m and int(m.group(1), 16) >= 0xDF00:
        raise SystemExit(
            "SMS RAM overflow: BSS reaches 0x%s (stack at 0xDFF0). "
            "Shorten the game or the song." % m.group(1))


def _preview(path, conv, options, game=None):
    import smsart
    text_ink, _highlight_ink, text_bg = smsart.text_colours(
        game, bool(options.get("mono")))
    return smsart.preview_bytes(path, conv, options, text_ink, text_bg)


def _build(ctx):
    import os
    import shutil
    import tempfile
    import build

    slug = ctx.slug
    build.run([ctx.py, os.path.join(ctx.root, "tools", "gen_port.py"),
               ctx.gdir, "--sms"], ctx.env)
    n_songs = _n_songs(ctx.bdir)
    td = tempfile.mkdtemp(prefix=f".sms-{slug}-", dir=ctx.bdir)
    try:
        sources = [
            *portable_sources(ctx.root),
            os.path.join(ctx.root, "src", "sms", "plat_sms.c"),
            os.path.join(ctx.root, "src", "portable", "plat.h"),
            os.path.join(ctx.bdir, "port_font8.h"),
            os.path.join(ctx.root, "src", "z80", "zx0_wrap.asm"),
            os.path.join(ctx.root, "vendor", "zx0", "zx0.asm"),
            os.path.join(ctx.bdir, "port_data.c"),
            os.path.join(ctx.bdir, "port_data.h"),
            os.path.join(ctx.bdir, "port_banks.asm"),
            os.path.join(ctx.bdir, "port_song.asm"),
        ]
        if n_songs:
            sources.append(os.path.join(ctx.root, "src", "sms",
                                        "sms_music.asm"))
        names = build.stage_inputs(td, sources)
        names = [n for n in names if n.endswith((".c", ".asm"))]
        cmd = ["zcc", "+sms", "-startup=16", "-clib=new", "-create-app", "-m",
               "-DPLAT_ROWS=24", "-I."]
        if n_songs:
            cmd.append("-pragma-define:CRT_ENABLE_RST=128")
        cmd += [*names, "-o", slug]
        build.run(cmd, ctx.env, cwd=td)
        _guard_map(os.path.join(td, slug + ".map"))
        produced = os.path.join(td, slug + ".sms")
        if not os.path.exists(produced):
            raise SystemExit("SMS build produced no .sms file")
        path = os.path.join(ctx.gdir, slug + ".sms")
        shutil.copyfile(produced, path)
    finally:
        shutil.rmtree(td, ignore_errors=True)
    result = BuildResult(target="sms")
    result.add_output(path, "sms-rom", os.path.getsize(path))
    return result


def _validate(ctx):
    rows = int(ctx.options.get("art_rows") or 12)
    if rows not in (8, 10, 12):
        return [{"level": "error", "section": "game", "id": "targets",
                 "target": "sms",
                 "msg": f"SMS art_rows must be 8, 10 or 12 (got {rows})"}]
    return []


TARGET = Target(
    id="sms",
    label="Sega Master System",
    description="Sega Master System runtime (full-height text, A-button options/items dialog, banked 4bpp art).",
    outputs=(".sms",),
    options=(
        TargetOption("art_rows", "Art rows", "choice", 12, (8, 10, 12),
                     "SMS character rows of picture; 12 leaves 11 rows below it.",
                     minimum=8, maximum=12),
        art_margin_option(),
        mono_option(),
        TargetOption("dither", "Dithering", "choice", scenefile.DEFAULT_DITHER,
                     scenefile.DITHER_BINARY_MODES,
                     help="off uses a hard nearest-colour snap; floyd uses "
                          "Floyd-Steinberg error diffusion."),
    ),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    emulator="emulatorjs",
    colors=16,
)
