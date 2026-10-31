"""Sega Master System target.

The editor preview and the .sms build share ``tools/smsart.py``.  The runtime
is the portable scene engine plus a VDP text/art layer; each art is stored
uncompressed in its own Sega-mapper ROM bank.
"""
from __future__ import annotations

import importlib.util

from .base import BuildResult, Target, TargetOption, portable_sources


def _available():
    if importlib.util.find_spec("PIL") is None:
        return False, "Pillow is required for SMS art conversion"
    return True, ""


def _preview(path, conv, options, game=None):
    import smsart
    text_ink, _highlight_ink, text_bg = smsart.text_colours(game)
    return smsart.preview_bytes(path, conv, options, text_ink, text_bg)


def _build(ctx):
    import os
    import shutil
    import tempfile
    import build

    slug = ctx.slug
    build.run([ctx.py, os.path.join(ctx.root, "tools", "gen_port.py"),
               ctx.gdir, "--sms"], ctx.env)
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
        ]
        names = build.stage_inputs(td, sources)
        names = [n for n in names if n.endswith((".c", ".asm"))]
        build.run(["zcc", "+sms", "-startup=16", "-clib=new", "-create-app",
                   "-DPLAT_ROWS=24", "-I.", *names, "-o", slug],
                  ctx.env, cwd=td)
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
    ),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    emulator="emulatorjs",
    colors=16,
)
