"""Amstrad CPC targets (464 and 6128).

Mode 1 (320x200, four monochrome shades) is the default display.  Art is
converted to CPC screen bytes and packed into the 6128's extra 16K banks
(BANK_4..BANK_7); the runtime pages a bank, decodes it with the vendored ZX0
decoder, and scatters the band to rows 1..cpc_art_rows.

The CPC 464 has only 64K and no extra banks.  Its build writes the same packed
bank files to the disk but starts with the CRT loader disabled and loads one
compressed art/song blob at a time from the GAME.Bn files through AMSDOS.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import tempfile

import scenefile

from .base import (BuildResult, Target, TargetOption, art_margin_option,
                   mono_option, portable_sources)

# Keep in sync with tools/gen_port.py: the resident AY song workspace. Music
# builds cap the CRT heap below it and keep BANK_2 free.
CPC_SONG_WS = 0x9600


def _define_int(bdir, name, default):
    """Read an integer #define from the generated port_data.h."""
    hdr = os.path.join(bdir, "port_data.h")
    try:
        with open(hdr, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return default
    m = re.search(rf"^#define {name} (0x[0-9A-Fa-f]+|\d+)", text, re.M)
    return int(m.group(1), 0) if m else default


def _available():
    if importlib.util.find_spec("PIL") is None:
        return False, "Pillow is required for CPC art conversion"
    return True, ""


def _preview(path, conv, options, game=None):
    import cpcart
    text_ink, highlight_ink, text_bg = cpcart.text_colours(
        game, bool(options.get("mono")))
    return cpcart.preview_bytes(path, conv, options, text_ink, highlight_ink,
                                text_bg)


def _guard_map(path, bdir):
    """Bank paging runs with the extra RAM bank mapped at 0x4000."""
    if not os.path.exists(path):
        return
    txt = open(path, encoding="utf-8", errors="replace").read()
    bad = []
    # Only the routines that execute while the extra bank is mapped must stay
    # low.  Callers such as plat_draw_art/plat_load may live above 0x4000:
    # cpc_unpack_banked restores the base map before returning, and cpc_set_ink
    # does the same after SCR_SET_INK.
    for sym in ("_cpc_unpack_banked", "_cpc_restore_base", "_cpc_set_ink",
                "_zx0_unpack"):
        m = re.search(rf"^{re.escape(sym)}\s*=\s*\$([0-9A-Fa-f]+)", txt,
                      re.M)
        if m and int(m.group(1), 16) >= 0x4000:
            bad.append(sym)
    if bad:
        raise SystemExit(
            "CPC home-region overflow: %s linked at or above 0x4000; "
            "the extra bank would page over the running decoder." %
            ", ".join(bad))
    music_bad = []
    for sym in ("_set_music", "_music_apply", "_ay_vt2_play",
                "asm_VT_PLAY", "asm_VT_INIT", "asm_VT_MUTE",
                "asm_VT_hardware_out"):
        m = re.search(rf"^{re.escape(sym)}\s*=\s*\$([0-9A-Fa-f]+)", txt,
                      re.M)
        if m and int(m.group(1), 16) >= 0x8000:
            music_bad.append(sym)
    if music_bad:
        raise SystemExit(
            "CPC music code overflow: %s linked at or above 0x8000; the "
            "base-RAM music workspace would overlap the program." %
            ", ".join(music_bad))

    hdr = os.path.join(bdir, "port_data.h")
    n_songs = 0
    ws_base = CPC_SONG_WS
    song_ws = CPC_SONG_WS
    song_ws_size = 0
    if os.path.exists(hdr):
        with open(hdr, encoding="utf-8", errors="replace") as f:
            head = f.read()
        m = re.search(r"^#define N_SONGS (\d+)", head, re.M)
        n_songs = int(m.group(1)) if m else 0
        m = re.search(r"^#define CPC_WS_BASE (0x[0-9A-Fa-f]+|\d+)", head,
                      re.M)
        ws_base = int(m.group(1), 0) if m else CPC_SONG_WS
        m = re.search(r"^#define SONG_WS_ADDR (0x[0-9A-Fa-f]+|\d+)", head,
                      re.M)
        song_ws = int(m.group(1), 0) if m else CPC_SONG_WS
        m = re.search(r"^#define SONG_WS_SIZE (\d+)", head, re.M)
        song_ws_size = int(m.group(1)) if m else 0

    bss = None
    m = re.search(r"^__BSS_END_tail\s*=\s*\$([0-9A-Fa-f]+)", txt, re.M)
    if m:
        bss = int(m.group(1), 16)
    if bss is not None and bss >= ws_base:
        raise SystemExit(
            "CPC base memory reaches 0x%04X; the fixed workspaces at 0x%04X "
            "would overlap it. Shorten the game or lower cpc_art_rows."
            % (bss, ws_base))

    art_asm = os.path.join(bdir, "port_art.asm")
    uses_bank2 = False
    if os.path.exists(art_asm):
        # A stale port_art_bank2.bin from an earlier build is not part of this
        # link; the generated assembly is the authoritative bank list.
        with open(art_asm, encoding="utf-8", errors="replace") as f:
            uses_bank2 = "SECTION BANK_2" in f.read()
    if n_songs:
        if uses_bank2:
            raise SystemExit(
                "CPC music builds cannot also place art/song data in BANK_2; "
                "the 0x8000 page holds the resident song workspace. Lower "
                "cpc_art_rows or remove arts.")
        if song_ws + song_ws_size > 0xA600:
            raise SystemExit(
                "CPC song workspace (0x%04X..0x%04X) reaches the firmware "
                "event blocks at 0xA600; shorten the module."
                % (song_ws, song_ws + song_ws_size))
    elif uses_bank2:
        if bss is not None and bss >= 0x8000:
            raise SystemExit(
                "CPC base memory reaches 0x%04X; BANK_2 art at 0x8000 would "
                "overlap it. Shorten the game or lower cpc_art_rows."
                % bss)


def _guard_disk_map(path, bdir):
    """The CPC 464 keeps the whole program and art buffer in base RAM."""
    if not os.path.exists(path):
        return
    txt = open(path, encoding="utf-8", errors="replace").read()
    ws_base = _define_int(bdir, "CPC_WS_BASE", CPC_SONG_WS)
    art_load = _define_int(bdir, "CPC_ART_LOAD_SIZE", 2)
    bss = None
    m = re.search(r"^__BSS_END_tail\s*=\s*\$([0-9A-Fa-f]+)", txt, re.M)
    if m:
        bss = int(m.group(1), 16)
    if bss is not None and bss >= ws_base:
        raise SystemExit(
            "CPC 464 resident image reaches 0x%04X; the fixed workspaces "
            "start at 0x%04X. Lower cpc464_art_rows, shorten the game, or "
            "use the CPC 6128 target." % (bss, ws_base))
    if art_load < 2:
        raise SystemExit("CPC 464 art load buffer is missing from port_data.h")


def build_cpc(ctx, target_id, gen_flag, out_ext, disk_stream=False):
    """Build one CPC variant; ``disk_stream`` selects the 64K 464 layout."""
    import build

    slug = ctx.slug
    build.run([ctx.py, os.path.join(ctx.root, "tools", "gen_port.py"),
               ctx.gdir, gen_flag], ctx.env)
    td = tempfile.mkdtemp(prefix=f".{target_id}-{slug}-", dir=ctx.bdir)
    try:
        # Stage all inputs in the game-folder build dir and run from there
        # with relative names: zcc mangles source paths that contain spaces
        # (the AppImage mount and some game folders do).
        sources = [
            os.path.join(ctx.root, "src", "cpc", "cpc_paging.asm"),
            os.path.join(ctx.root, "src", "cpc", "cpc_ink.asm"),
        ]
        if disk_stream:
            sources.append(os.path.join(ctx.root, "src", "cpc",
                                        "cpc_disk.asm"))
        sources += [
            os.path.join(ctx.root, "src", "z80", "zx0_wrap.asm"),
            os.path.join(ctx.root, "vendor", "zx0", "zx0.asm"),
            *portable_sources(ctx.root),
            os.path.join(ctx.root, "src", "cpc", "plat_cpc.c"),
            os.path.join(ctx.root, "src", "portable", "plat.h"),
            os.path.join(ctx.bdir, "port_data.c"),
            os.path.join(ctx.bdir, "port_data.h"),
            os.path.join(ctx.bdir, "port_font4.h"),
            os.path.join(ctx.bdir, "port_art.asm"),
            os.path.join(ctx.bdir, "port_ws.asm"),
        ]
        names = build.stage_inputs(td, sources)
        names = [n for n in names if n.endswith((".c", ".asm"))]
        # A fixed 8.3-safe internal name makes the DSK's AMSDOS files (GAME,
        # GAME.4, ...) stable, so the web emulator can auto-type RUN"GAME.
        cmd = ["zcc", "+cpc", "-subtype=dsk", "-create-app", "-m",
               "-Ca-DZX0_LOW", "-DPLAT_ROWS=25", "-I."]
        cmd.append("-pragma-define:CRT_MAX_HEAP_ADDRESS=%d"
                   % _define_int(ctx.bdir, "CPC_WS_BASE", CPC_SONG_WS))
        if disk_stream:
            # The 464 cannot page the bank files at boot; they are read on
            # demand by cpc_disk.asm instead.
            cmd.append("-pragma-define:CRT_DISABLELOADER=1")
        cmd += [*names, "-o", "GAME"]
        build.run(cmd, ctx.env, cwd=td)
        produced = os.path.join(td, "GAME.dsk")
        if not os.path.exists(produced):
            raise SystemExit("CPC build produced no .dsk file")
        if disk_stream:
            _guard_disk_map(os.path.join(td, "GAME.map"), ctx.bdir)
        else:
            _guard_map(os.path.join(td, "GAME.map"), ctx.bdir)
        path = os.path.join(ctx.gdir, slug + out_ext)
        shutil.copyfile(produced, path)
    finally:
        shutil.rmtree(td, ignore_errors=True)
    result = BuildResult(target=target_id)
    result.add_output(path, "cpc464-dsk" if disk_stream else "cpc-dsk",
                      os.path.getsize(path))
    return result


def _build(ctx):
    return build_cpc(ctx, "cpc", "--cpc", ".dsk")


def _validate(ctx):
    mode = int(ctx.options.get("mode") or 1)
    rows = int(ctx.options.get("art_rows") or 12)
    cols = int(ctx.options.get("columns") or 32)
    issues = []
    if mode not in (0, 1, 2):
        issues.append({"level": "error", "section": "game", "id": "targets",
                       "target": "cpc",
                       "msg": "CPC mode must be 0, 1 or 2"})
    # Mode 2 can trade text rows for a taller band; the other modes keep the
    # original cap so the text pane is not squeezed.
    allowed_rows = (8, 10, 12, 14, 16) if mode == 2 else (8, 10, 12)
    if rows not in allowed_rows:
        choices = ", ".join(str(r) for r in allowed_rows[:-1])
        choices += f" or {allowed_rows[-1]}"
        where = " in mode 2" if mode == 2 else ""
        issues.append({"level": "error", "section": "game", "id": "targets",
                       "target": "cpc",
                       "msg": f"CPC art_rows must be {choices}{where} "
                              f"(got {rows})"})
    width = {0: 160, 1: 320, 2: 640}.get(mode, 320)
    if cols not in (32, 40, 62):
        issues.append({"level": "error", "section": "game", "id": "targets",
                       "target": "cpc",
                       "msg": f"CPC columns must be 32, 40 or 62 (got {cols})"})
    elif cols > width // 4:
        issues.append({"level": "error", "section": "game", "id": "targets",
                       "target": "cpc",
                       "msg": f"CPC mode {mode} fits at most {width // 4} "
                              f"text columns (asked for {cols})"})
    return issues


def cpc_options(default_rows=12):
    return (
        TargetOption("mode", "Video mode", "choice", 1, (0, 1, 2),
                     "CPC video mode: 0 (160px/16 inks), 1 (320px mono, "
                     "black/grey/white ramp), 2 (640px/2 inks)."),
        TargetOption("columns", "Text columns", "choice", 32, (32, 40, 62),
                     "32 shares the SMS layout; 40 is native Mode 1; 62 uses "
                     "a compact 4px font."),
        TargetOption("art_rows", "Art rows", "choice", default_rows,
                     (8, 10, 12, 14, 16),
                     "Character rows of picture above the scrolling text pane. "
                     "14 and 16 need Mode 2 (fewer text rows remain).",
                     minimum=8, maximum=16),
        art_margin_option(),
        mono_option(),
        TargetOption("dither", "Dithering", "choice", scenefile.DEFAULT_DITHER,
                     scenefile.DITHER_MODES,
                     help="off snaps to the nearest colour; bayer2/bayer4/"
                          "bayer8 and noise ordered-dither the palette; floyd, "
                          "atkinson, jarvis, stucki and sierra diffuse the "
                          "error (smoother, but larger blobs). Mode 1's grey "
                          "ramp always dithers (off uses Bayer 4x4)."),
        TargetOption("menu", "Pop-up options", "bool", False,
                     help="Use the SPACE-key dialog for the options and held "
                          "items instead of pinned options and the inventory "
                          "row.",
                     on_value="popup", off_value="inline"),
    )


TARGET = Target(
    id="cpc",
    label="Amstrad CPC 6128",
    description="Amstrad CPC Mode 0/1/2 text runtime with compressed art in "
                "the extra 16K banks; any mode can use the under-art action "
                "dialog.",
    outputs=(".dsk",),
    options=cpc_options(12),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    emulator="cpcjs",
    colors=4,
    band_width=320,
)
