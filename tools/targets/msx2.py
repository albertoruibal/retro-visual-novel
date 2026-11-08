"""MSX2 target (V9938 Screen 7).

The editor preview and the .rom build share ``tools/msx2art.py``.  Screen 7 is
a 512 x 212 four-bit bitmap with a 512-colour palette; the runtime draws the
full-width art band and an 80-column 6x8 text layer directly into VRAM.  Scene
data lives in ASCII16 ROM bank 1 and each art band uses one 16K bank.
"""
from __future__ import annotations

import importlib.util
import os
import re

import scenefile

from .base import BuildResult, Target, TargetOption, portable_sources


def _available():
    if importlib.util.find_spec("PIL") is None:
        return False, "Pillow is required for MSX2 art conversion"
    return True, ""


def _preview(path, conv, options, game=None):
    import msx2art
    text_ink, highlight_ink, text_bg = msx2art.text_colours(game)
    return msx2art.preview_bytes(path, conv, options, text_ink, highlight_ink,
                                 text_bg)


def _build(ctx):
    import os
    import shutil
    import tempfile
    import build

    slug = ctx.slug
    build.run([ctx.py, os.path.join(ctx.root, "tools", "gen_port.py"),
               ctx.gdir, "--msx2"], ctx.env)
    td = tempfile.mkdtemp(prefix=f".msx2-{slug}-", dir=ctx.bdir)
    try:
        sources = [
            *portable_sources(ctx.root),
            os.path.join(ctx.root, "src", "msx2", "plat_msx2.c"),
            os.path.join(ctx.root, "src", "portable", "plat.h"),
            os.path.join(ctx.root, "src", "msx2", "msx2_vram.asm"),
            os.path.join(ctx.root, "src", "z80", "zx0_wrap.asm"),
            os.path.join(ctx.root, "vendor", "zx0", "zx0.asm"),
            os.path.join(ctx.bdir, "port_data.c"),
            os.path.join(ctx.bdir, "port_data.h"),
            os.path.join(ctx.bdir, "port_art.asm"),
            os.path.join(ctx.bdir, "port_song.asm"),
            os.path.join(ctx.bdir, "port_font.asm"),
        ]
        names = build.stage_inputs(td, sources)
        names = [n for n in names if n.endswith((".c", ".asm"))]
        build.run(["zcc", "+msx", "-subtype=rom2", "-create-app", "-m",
                   "-pragma-define:MAPPER_ASCII16", "-DPLAT_ROWS=24",
                   "-I.", *names, "-o", slug], ctx.env, cwd=td)
        produced = os.path.join(td, slug + ".rom")
        if not os.path.exists(produced):
            raise SystemExit("MSX2 build produced no .rom file")
        _guard_map(os.path.join(td, slug + ".map"))
        path = os.path.join(ctx.gdir, slug + ".rom")
        shutil.copyfile(produced, path)
    finally:
        shutil.rmtree(td, ignore_errors=True)
    result = BuildResult(target="msx2")
    result.add_output(path, "msx2-rom", os.path.getsize(path))
    return result


def _guard_map(path):
    """ASCII16 keeps resident code in the first 16K page."""
    if not os.path.exists(path):
        return
    txt = open(path, encoding="utf-8", errors="replace").read()
    bad = []
    for sym in ("_main", "_plat_draw_art", "_plat_set_bank", "_port_unpack",
                "_zx0_unpack", "_set_music", "_music_apply", "_ay_vt2_play",
                "asm_VT_PLAY", "asm_VT_INIT", "asm_VT_MUTE",
                "asm_VT_hardware_out"):
        m = re.search(rf"^{re.escape(sym)}\s*=\s*\$([0-9A-Fa-f]+)", txt,
                      re.M)
        if m and int(m.group(1), 16) >= 0x8000:
            bad.append(sym)
    if bad:
        raise SystemExit(
            "MSX2 home-region overflow: %s linked at or above 0x8000; the "
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
            "MSX2 main ROM reaches 0x%04X; the fixed 16 KB bank must stay "
            "below 0x8000. z88dk-appmake otherwise starts at bank 2 and "
            "silently drops the bank-1 scene/inventory data. Shorten the "
            "game or move resident data into a bank." % rom_end)


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


def _scene_rows(doc, art_rows, columns, popup=False):
    """Worst-case (all runtime conditions true) text/option rows per scene."""
    import scenefile
    out = []
    text_top = 1 + art_rows
    for scene in (doc or {}).get("scenes") or []:
        text = 0
        for raw in scene.get("text") or []:
            rendered, conds = scenefile.split_text_line(raw)
            if scenefile.filter_system_conditions(conds, "msx2") is None:
                continue
            clean = "".join(t for t, _flag
                            in scenefile.word_segments(rendered))
            text += _rows(clean, columns)
        opts = 0
        for raw in scene.get("opts") or []:
            rest = str(raw).split("->", 1)[1] if "->" in str(raw) else ""
            if scenefile.filter_system_conditions(
                    scenefile.option_conditions(rest), "msx2") is None:
                continue
            label = str(raw).split("->", 1)[0].strip()
            opts += _rows(label, columns - 2)
        avail = (24 if popup else 23) - text_top
        text_rows = avail if popup else (
            max(1, avail - opts) if opts < avail else 1)
        if text > text_rows:
            out.append((scene.get("id", "?"), text, text_rows))
    return out


def _validate(ctx):
    issues = []
    rows = int(ctx.options.get("art_rows") or 12)
    if rows not in (8, 10, 12):
        issues.append({"level": "error", "section": "game", "id": "targets",
                       "target": "msx2",
                       "msg": f"MSX2 art_rows must be 8, 10 or 12 (got {rows})"})
    cols = int(ctx.options.get("columns") or 64)
    if cols not in (64, 80):
        issues.append({"level": "error", "section": "game", "id": "targets",
                       "target": "msx2",
                       "msg": f"MSX2 columns must be 64 or 80 (got {cols})"})
    if rows in (8, 10, 12) and cols in (64, 80):
        popup = bool(ctx.options.get("menu"))
        for sid, used, avail in _scene_rows(ctx.doc, rows, cols, popup):
            issues.append({
                "level": "warn", "section": "scene", "id": sid,
                "target": "msx2",
                "msg": (f"MSX2: scene {sid!r} needs {used} text rows but the "
                        f"fixed {rows}-row art band leaves {avail}; the MSX2 "
                        "pane does not scroll, so the overflow is hidden"),
            })
    return issues


TARGET = Target(
    id="msx2",
    label="MSX2 (V9938)",
    description="MSX2 V9938 Screen 7 runtime with 16-colour bitmap art and 64/80-column text.",
    outputs=(".rom",),
    options=(
        TargetOption("art_rows", "Art rows", "choice", 12, (8, 10, 12),
                     "Character rows of picture above the text pane.",
                     minimum=8, maximum=12),
        TargetOption("dither", "Dithering", "choice", scenefile.DEFAULT_DITHER,
                     scenefile.DITHER_BINARY_MODES,
                     help="off uses a hard nearest-colour snap; floyd uses "
                          "Floyd-Steinberg error diffusion."),
        TargetOption("columns", "Text columns", "choice", 64, (64, 80),
                     "64 uses 8x8 glyphs across the full 512-pixel width; "
                     "80 uses 6-pixel cells."),
        TargetOption("menu", "Pop-up options", "bool", False,
                     help="Use the SPACE-key or joystick button 2 dialog instead "
                          "of pinned options and the inventory row.",
                     on_value="popup", off_value="inline"),
    ),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    emulator="webmsx",
    machine="MSX2",
    colors=16,
    band_width=512,
)
