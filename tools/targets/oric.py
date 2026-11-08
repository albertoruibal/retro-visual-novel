"""Oric Atmos target.

The runtime is the shared portable story engine on the Oric Atmos HIRES
bitmap (240x200 at $A000, 6 pixels per byte): the title is on character row 0,
the picture on rows 1..art_rows and the text pane below.  Text is drawn in
software with a 6x8 glyph table; the options and held items are pinned above
the row-24 inventory unless ``## oric menu: popup`` selects the portable
overlay dialog.  Story and art blobs are resident and ZX0-compressed (the
Atmos has no banked memory), decoded by the shared 6502 decoder.

cc65 (``cl65 -t atmos``) is required; z88dk has no Oric target.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import tempfile

import cc65path
import scenefile
from .base import BuildResult, Target, TargetOption, portable_sources

ART_ROWS = (4, 6, 8, 10, 12)
# cc65's atmos.cfg keeps the image and BSS below the 2K C stack at $97FF, so
# the BSS area ends at $9000.  HIRES uses $A000-$BF3F.
BSS_END = 0x9000
RAM_END = 0x9800


def _available():
    if importlib.util.find_spec("PIL") is None:
        return False, "Pillow is required for Oric Atmos art conversion"
    if not cc65path.available():
        return False, "cc65 (cl65/ca65/ld65/cc65) is required for the Oric Atmos build"
    return True, ""


def _preview(path, conv, options, game=None):
    import oricart
    return oricart.preview_bytes(path, conv, options, game)


def _guard_map(path):
    """Keep the resident image/BSS below the Oric C stack and HIRES screen."""
    if not os.path.exists(path):
        return
    text = open(path, encoding="utf-8", errors="replace").read()

    def value(name):
        m = re.search(rf"^{re.escape(name)}\s*=\s*\$([0-9A-Fa-f]+)", text, re.M)
        return int(m.group(1), 16) if m else None

    bss_start = value("__BSS_RUN__")
    if bss_start is None:
        bss_start = value("__ONCE_RUN__")
    bss_size = value("__BSS_SIZE__")
    bss_tail = value("__BSS_END_tail")
    if bss_tail is None and bss_start is not None and bss_size is not None:
        bss_tail = bss_start + bss_size - 1 if bss_size else bss_start
    if bss_start is not None and bss_start > BSS_END:
        raise SystemExit(
            "Oric Atmos main image ends at 0x%04X; code+data must stay below "
            "the BSS/stack area at 0x%04X. Lower oric art_rows, remove arts "
            "or shorten the story." % (bss_start, BSS_END))
    if bss_tail is not None and bss_tail > BSS_END:
        raise SystemExit(
            "Oric Atmos BSS reaches 0x%04X; the C stack starts below 0x%04X. "
            "Shorten a scene or the inventory text." % (bss_tail, RAM_END))


def _build(ctx):
    import build

    slug = ctx.slug
    out_name = slug + "-oric.tap"
    build.run([ctx.py, os.path.join(ctx.root, "tools", "gen_port.py"),
               ctx.gdir, "--oric"], ctx.env)
    td = tempfile.mkdtemp(prefix=f".oric-{slug}-", dir=ctx.bdir)
    try:
        sources = [
            os.path.join(ctx.root, "src", "6502", "zx0.c"),
            *portable_sources(ctx.root),
            os.path.join(ctx.root, "src", "oric", "plat_oric.c"),
            os.path.join(ctx.root, "src", "portable", "plat.h"),
            os.path.join(ctx.bdir, "port_data.c"),
            os.path.join(ctx.bdir, "port_data.h"),
            os.path.join(ctx.bdir, "port_font6.h"),
            os.path.join(ctx.root, "src", "oric", "atmos.cfg"),
        ]
        names = build.stage_inputs(td, sources)
        compile_names = [n for n in names if n.endswith((".c", ".s"))]
        cmd = ["cl65", "-t", "atmos", "-C", "atmos.cfg", "-Oirs",
               "-DPLAT_ROWS=25", "-I.", "-m", slug + ".map",
               *compile_names, "-o", out_name]
        build.run(cmd, ctx.env, cwd=td)
        produced = os.path.join(td, out_name)
        if os.path.exists(os.path.join(td, slug + ".map")):
            shutil.copyfile(os.path.join(td, slug + ".map"),
                            os.path.join(ctx.bdir, slug + ".oric.map"))
        if not os.path.exists(produced):
            raise SystemExit("Oric Atmos build produced no .tap file")
        _guard_map(os.path.join(td, slug + ".map"))
        path = os.path.join(ctx.gdir, out_name)
        shutil.copyfile(produced, path)
    finally:
        shutil.rmtree(td, ignore_errors=True)
    result = BuildResult(target="oric")
    result.add_output(path, "oric-tap", os.path.getsize(path))
    return result


def _rows(text, width):
    """Rows the runtime wraps ``text`` into at ``width`` columns."""
    n = 0
    s = text or ""
    while s:
        k = last = 0
        while k < len(s) and k < width:
            if s[k] == " ":
                last = k
            k += 1
        if k < len(s) and last:
            k = last
        if not k:
            k = 1
        s = s[k:]
        while s.startswith(" "):
            s = s[1:]
        n += 1
    return n


def _validate(ctx):
    rows = int(ctx.options.get("art_rows") or 8)
    if rows not in ART_ROWS:
        return [{"level": "error", "section": "game", "id": "targets",
                 "target": "oric",
                 "msg": f"Oric Atmos art_rows must be 4, 6, 8, 10 or 12 "
                        f"(got {rows})"}]
    issues = []
    if not bool(ctx.options.get("menu")):
        # The pinned options share rows PORT_TEXT_TOP..23 with the scrolling
        # text; row 24 is the inventory band.  Warn when the worst case leaves
        # them no room, since the engine then draws them over the art.
        avail = 23 - rows
        for scene in (ctx.doc or {}).get("scenes") or []:
            used = 0
            for raw in scene.get("opts") or []:
                rest = str(raw).split("->", 1)[1] if "->" in str(raw) else ""
                if scenefile.filter_system_conditions(
                        scenefile.option_conditions(rest), "oric") is None:
                    continue
                label = str(raw).split("->", 1)[0].strip()
                used += _rows(label, 38)
            if used >= avail:
                sid = scene.get("id", "?")
                issues.append({
                    "level": "warn", "section": "scene", "id": sid,
                    "target": "oric",
                    "msg": (f"Oric Atmos: scene {sid!r} needs {used} option "
                            f"rows but the pinned {rows}-row layout leaves "
                            f"{avail} above the inventory row; use "
                            "'## oric menu: popup' or shorter labels"),
                })
    return issues


TARGET = Target(
    id="oric",
    label="Oric Atmos",
    description="Oric Atmos HIRES runtime: 240x200 monochrome dithered art, "
                "40-column software text and pinned options or a SPACE "
                "action dialog.",
    outputs=(".tap",),
    artifact_suffix="-oric",
    options=(
        TargetOption("art_rows", "Art rows", "choice", 8, ART_ROWS,
                     "Character rows of picture; 8 leaves 16 text rows.",
                     minimum=4, maximum=12),
        TargetOption("dither", "Dithering", "choice", scenefile.DEFAULT_DITHER,
                     scenefile.DITHER_MODES,
                     help="The 1-bit screen cannot honour off, so an off choice "
                          "becomes a 2x2 Bayer dither. Every ordered and "
                          "error-diffusion scheme is available."),
        TargetOption("menu", "Pop-up options", "bool", False,
                     help="Show scene options and held items in a SPACE-key "
                          "dialog instead of the pinned option list and "
                          "row-24 inventory band.",
                     on_value="popup", off_value="inline"),
    ),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    emulator="oricutron",
    machine="atmos",
    colors=2,
    engine="Oric HIRES",
    band_width=240,
)
