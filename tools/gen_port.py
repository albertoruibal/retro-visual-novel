#!/usr/bin/env python3
"""Generate the portable text-adventure data used by the portable runtimes.

The same scene/inventory blobs as the ZX engine are emitted as C arrays.  On
SMS/CPC/MSX2 they are ZX0-compressed and decompressed one scene at a time with
the vendored decoder.  On Game Boy Color they are stored raw in MBC1 banks (the SM83
has no compatible decoder) and copied by ``src/gb/gb_copy.asm``.  All generated
``port_*`` sources, assemblies and bank images are written under the game's
``build/`` folder; only the final ROM/disk output stays at the root.

Per-target art handling:
  * SMS ``--sms``: 4bpp planar tiles, one art per Sega-mapper ROM bank
    (``port_banks.asm``).
  * CPC ``--cpc``: CPC screen bytes in the 6128's extra 16K banks.
  * CPC 464 ``--cpc464``: the same bank files are written to the disk, but the
    runtime loads one compressed art/song blob at a time through AMSDOS instead
    of paging the extra 16K banks (the 464 has no extra RAM).
  * MSX2 ``--msx2``: V9938 Screen 7 4bpp bitmap bands with a per-art palette,
    one per ASCII16 bank; scene data in bank 1.
  * GB ``--gb``: raw 2bpp tile/map blobs in MBC1 banks; scene data is split
    across banks 2 and up.
  * Oric ``--oric``: resident 240 x (8*art_rows) monochrome HIRES bytes,
    one ZX0-compressed blob per art; scenes/inventory stay resident too.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamestore
import gen_scenes
import scenefile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Resident CPC song workspace. Music builds keep art/song data out of BANK_2
# so this base-RAM page stays free for the workspace. The firmware event
# blocks start at 0xA600, so the module is placed just below that, leaving the
# growing BSS clear of it.
CPC_SONG_WS = 0x9600
CPC_TOP = 0xA600


def _cpc_ws_layout(scene_size, inv_size, song_size):
    """Fixed base/song addresses for the CPC base-RAM workspaces.

    The scene and inventory workspaces never overlap at runtime (the item
    screen reloads the scene on return), so they share one buffer sized to the
    larger. The song workspace follows it, all just below the firmware event
    blocks at 0xA600.
    """
    shared = max(scene_size, inv_size)
    song = CPC_TOP - song_size if song_size else CPC_TOP
    return song - shared, song


def _arr(lines, typ, name, values, fmt):
    lines.append(f"const {typ} {name}[{len(values)}] = {{")
    for i in range(0, len(values), 16):
        lines.append("    " + ", ".join(fmt % v for v in values[i:i + 16]) + ",")
    lines.append("};")


def _bytes_arr(lines, name, data):
    if not data:
        data = b"\0"
    _arr(lines, "unsigned char", name, list(data), "0x%02X")


def _c_string(lines, name, text):
    data = gen_scenes.esc_bytes(text)
    _arr(lines, "char", name, list(data), "%d")


def _bank_pack(blobs, start_bank):
    """Pack raw blobs into 16K banks, returning ``(data, banks, offsets)``."""
    data = {}
    banks = []
    offs = []
    bank = start_bank
    for blob in blobs:
        if len(blob) > 0x4000:
            sys.exit(f"{len(blob)}B blob does not fit one 16K bank")
        if bank not in data or len(data[bank]) + len(blob) > 0x4000:
            if bank in data:
                bank += 1
            data[bank] = bytearray()
        banks.append(bank)
        offs.append(len(data[bank]))
        data[bank] += blob
    return data, banks, offs


def _cpc_pack(packed, bank_max, allow_bank2=True):
    """Pack compressed CPC art/song blobs into the 6128's banks.

    The CPC 464 build uses the same packed bank files, but writes them to the
    disk and loads one blob at a time through AMSDOS (it cannot map the extra
    banks).

    Returns ``(bank_data, banks, offsets)`` in blob order, or ``None`` when the
    blobs do not fit.  Best-fit decreasing is the fast path; a bounded
    backtracking search handles the near-capacity cases where fragmentation
    defeats the greedy order.  ``allow_bank2=False`` (music builds) keeps the
    base-RAM BANK_2 page free for the resident song workspace.
    """
    order = sorted(range(len(packed)), key=lambda i: len(packed[i]),
                   reverse=True)
    sizes = [len(packed[i]) for i in order]
    total = sum(sizes)
    # Keep BANK_2 (base RAM at 0x8000) as the last resort: it shares the
    # region with BSS/stack and `tools/targets/cpc.py` rejects it when the
    # program reaches 0x8000.  The four extra banks hold 64K by themselves.
    bins = (4, 5, 6, 7) if (total <= 4 * 0x4000 or not allow_bank2) \
        else (4, 5, 6, 7, 2)
    caps = [bank_max[bn] for bn in bins]

    rem = caps[:]
    assign = [None] * len(sizes)
    ok = True
    for i, size in enumerate(sizes):
        best = None
        for j, room in enumerate(rem):
            if size <= room and (best is None or room < best[0]):
                best = (room, j)
        if best is None:
            ok = False
            break
        j = best[1]
        rem[j] -= size
        assign[i] = j

    if not ok:
        rem = caps[:]
        assign = [None] * len(sizes)
        nodes = [0]
        limit = 1_000_000

        def dfs(idx):
            nodes[0] += 1
            if idx == len(sizes):
                return True
            if nodes[0] > limit:
                return False
            size = sizes[idx]
            seen = set()
            for j in sorted(range(len(rem)), key=lambda k: rem[k]):
                if rem[j] < size or rem[j] in seen:
                    continue
                seen.add(rem[j])
                rem[j] -= size
                assign[idx] = j
                if dfs(idx + 1):
                    return True
                rem[j] += size
                assign[idx] = None
            return False

        if not dfs(0):
            return None

    data = {bn: bytearray() for bn in bins}
    banks = [0] * len(packed)
    offs = [0] * len(packed)
    # Lay blobs out in their declared order (the packer only sorts by size to
    # pick a bin).  The CPC 464 passes the songs first so their offset stays
    # within the 2K AMSDOS stream buffer, which keeps the char-by-char load
    # fast.
    inverse = [0] * len(packed)
    for idx, orig in enumerate(order):
        inverse[orig] = idx
    for orig in range(len(packed)):
        idx = inverse[orig]
        bn = bins[assign[idx]]
        banks[orig] = bn
        offs[orig] = len(data[bn])
        data[bn] += packed[orig]
    return data, banks, offs


def _write_bank_asm(gdir, filename, bank_data, file_prefix, public_prefix=""):
    """Write one ``.asm`` with a ``SECTION BANK_NN`` per non-empty bank."""
    asm = ["; generated by tools/gen_port.py - do not edit"]
    for bn in sorted(bank_data):
        body = bank_data[bn]
        if not body:
            continue
        path = os.path.join(gdir, f"{file_prefix}{bn}.bin")
        with open(path, "wb") as f:
            f.write(body)
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        asm.append(f"SECTION BANK_{bn:02X}")
        if public_prefix:
            asm.append(f"PUBLIC {public_prefix}{bn}")
            asm.append(f"{public_prefix}{bn}:")
        asm.append(f'    BINARY "{rel}"')
    with open(os.path.join(gdir, filename), "w", encoding="utf-8") as f:
        f.write("\n".join(asm) + "\n")


def _write_next_bank_asm(gdir, filename, bank_data, file_prefix):
    """Write 16K Next banks as ``SECTION BANK_n`` (decimal, no leading zero)."""
    asm = ["; generated by tools/gen_port.py - do not edit"]
    for bn in sorted(bank_data):
        body = bank_data[bn]
        if not body:
            continue
        path = os.path.join(gdir, f"{file_prefix}{bn}.bin")
        with open(path, "wb") as f:
            f.write(body)
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        asm.append(f"SECTION BANK_{bn}")
        asm.append(f'    BINARY "{rel}"')
    with open(os.path.join(gdir, filename), "w", encoding="utf-8") as f:
        f.write("\n".join(asm) + "\n")


def _flip8(value):
    """Reverse the eight bits of one LSB-left font row for the SMS VDP."""
    out = 0
    for bit in range(8):
        if value & (1 << bit):
            out |= 1 << (7 - bit)
    return out


def _write_gb_font(gdir):
    """Emit the 96 2bpp Game Boy Color font tiles used by plat_gb.c."""
    import gbart
    font8 = open(gen_scenes.FONT8X8, "rb").read()
    font = gbart.font_tiles(font8, gen_scenes.ACCENT_GLYPHS_8X8)
    lines = ["/* generated by tools/gen_port.py - do not edit */",
             f"const unsigned char port_font2[{len(font)}] = {{"]
    for i in range(0, len(font), 16):
        lines.append("    " + ",".join("%d" % b for b in font[i:i + 16]) + ",")
    lines.append("};")
    with open(os.path.join(gdir, "port_font2.h"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _write_sms_font(gdir):
    """Emit the 96 1bpp SMS glyphs from the shared 8x8 font."""
    font = bytearray(open(gen_scenes.FONT8X8, "rb").read())
    for ch, rows in gen_scenes.ACCENT_GLYPHS_8X8.items():
        off = (ch - 32) * 8
        for i, row in enumerate(rows):
            font[off + i] = row
    font = bytes(_flip8(row) for row in font)
    lines = ["/* generated by tools/gen_port.py - do not edit */",
             f"const unsigned char port_font8[{len(font)}] = {{"]
    for i in range(0, len(font), 16):
        lines.append("    " + ",".join("%d" % b for b in font[i:i + 16]) + ",")
    lines.append("};")
    with open(os.path.join(gdir, "port_font8.h"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _oric_row(value):
    """Fit an LSB-left 8-pixel row to the Oric's six-pixel cell.

    Pixels beyond column 5 are folded into the rightmost cell instead of being
    dropped, so wide glyphs (M, W, #, %, @, ...) keep their right edge.
    """
    if value & 0xE0:
        value |= 0x20
    out = 0
    for bit in range(6):
        if value & (1 << bit):
            out |= 1 << (5 - bit)
    return out


def _write_oric_font(gdir):
    """Emit the 96 6x8 Oric HIRES glyphs (bit 5 is the leftmost pixel)."""
    font = bytearray(open(gen_scenes.FONT8X8, "rb").read())
    for ch, rows in gen_scenes.ACCENT_GLYPHS_8X8.items():
        off = (ch - 32) * 8
        for i, row in enumerate(rows):
            font[off + i] = row
    font = bytes(_oric_row(row) for row in font)
    lines = ["/* generated by tools/gen_port.py - do not edit */",
             f"const unsigned char port_font6[{len(font)}] = {{"]
    for i in range(0, len(font), 16):
        lines.append("    " + ",".join("%d" % b for b in font[i:i + 16]) + ",")
    lines.append("};")
    with open(os.path.join(gdir, "port_font6.h"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _cpc_font_bytes():
    """Return the 4x8 glyph table (with accented slots) used by plat_cpc.c."""
    font = bytearray(open(gen_scenes.BASE_FONT, "rb").read())
    for ch, glyph in gen_scenes.ACCENT_GLYPHS.items():
        off = (ch - 32) * 8
        for i, nib in enumerate(glyph):
            font[off + i] = nib & 0x0F
    for i in range(len(font)):
        font[i] &= 0x0F
    return bytes(font)


def _write_cpc_font(gdir):
    """Emit the 4x8 glyph table (with accented slots) used by plat_cpc.c."""
    font = _cpc_font_bytes()
    lines = ["/* generated by tools/gen_port.py - do not edit */",
             f"const unsigned char port_font4[{len(font)}] = {{"]
    for i in range(0, len(font), 16):
        lines.append("    " + ",".join("%d" % b for b in font[i:i + 16]) + ",")
    lines.append("};")
    with open(os.path.join(gdir, "port_font4.h"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _msx2_font8_bytes():
    """Return the raw 8x8 font for 64-column Screen 7 text.

    ``plat_msx2.c`` expands each row into four Screen 7 bytes at startup.  The
    font lives in its own ROM bank because the 16 KB fixed bank is full.
    """
    font = bytearray(open(gen_scenes.FONT8X8, "rb").read())
    for ch, rows in gen_scenes.ACCENT_GLYPHS_8X8.items():
        off = (ch - 32) * 8
        for i, row in enumerate(rows):
            font[off + i] = row
    return bytes(font)


def main():
    raw = sys.argv[1:]
    target_id = ""
    if "--target" in raw:
        i = raw.index("--target")
        if i + 1 < len(raw):
            target_id = raw[i + 1].strip().lower()
            del raw[i:i + 2]
    for i, value in enumerate(list(raw)):
        if value.startswith("--target="):
            target_id = value.split("=", 1)[1].strip().lower()
            del raw[i]
            break
    args = [a for a in raw if not a.startswith("--")]
    arg = args[0] if args else None
    if not arg:
        sys.exit("usage: gen_port.py <game-dir-or-slug> "
                 "[--sms|--cpc|--cpc464|--msx2|--gb|--next|--c64|--nes|--oric|"
                 "--target <id>]")
    if os.path.isdir(arg):
        gdir = os.path.abspath(arg)
    else:
        game = gamestore.resolve(arg)
        if game is None:
            sys.exit(f"no such game: {arg!r}")
        gdir = game["dir"]
    bdir = os.path.join(gdir, gamestore.BUILD_NAME)
    os.makedirs(bdir, exist_ok=True)
    doc = scenefile.parse(os.path.join(gdir, "game.md"))
    scenes = doc["scenes"]
    arts = doc["arts"]
    game = doc["game"]
    idmap = {b["id"]: i for i, b in enumerate(scenes)}
    artmap = {a["id"]: i for i, a in enumerate(arts)}
    item_names = scenefile.item_display_names(game, doc.get("item_meta"))
    have_messages = any(scenefile.split_option_msg(o)[1]
                        for b in scenes for o in b.get("opts") or [])
    have_messages = have_messages or any(
        scenefile.split_option_msg(o)[1]
        for meta in (doc.get("item_meta") or {}).values()
        for o in meta.get("opts") or [])
    flag_map, item_list, _order = scenefile.assign_flags(
        scenes, game.get("start", []), game.get("flags", []),
        scenefile.declared_items(game, doc.get("item_meta")),
        item_names=item_names, item_meta=doc.get("item_meta"))
    system = target_id
    if not system:
        for flag, name in (("--sms", "sms"), ("--cpc", "cpc"),
                           ("--cpc464", "cpc464"),
                           ("--msx2", "msx2"), ("--gb", "gb"),
                           ("--next", "next"), ("--c64", "c64"),
                           ("--nes", "nes"), ("--oric", "oric")):
            if flag in raw:
                system = name
                break
    scene_raw = [gen_scenes.build_scene_blob(b, idmap, artmap, flag_map,
                                             system)
                 for b in scenes]
    any_words = any(scenefile.parse_words(
                        scenefile.split_text_line(raw)[0])[1]
                    for b in scenes for raw in b.get("text", []))
    ui = scenefile.inventory_strings(game)
    inv_raw, have_desc, have_opts = gen_scenes.build_inv_blob(
        item_list, flag_map, doc.get("item_meta") or {}, ui,
        int(game.get("carry", 0) or 0), idmap, system)
    use_sms = "--sms" in raw or target_id == "sms"
    use_cpc464 = "--cpc464" in raw or target_id == "cpc464"
    use_cpc = "--cpc" in raw or target_id == "cpc" or use_cpc464
    use_msx2 = "--msx2" in raw or target_id == "msx2"
    use_gb = "--gb" in raw or target_id == "gb"
    use_next = "--next" in raw or target_id == "next"
    use_c64 = "--c64" in raw or target_id == "c64"
    use_nes = "--nes" in raw or target_id == "nes"
    use_oric = "--oric" in raw or target_id == "oric"
    music_target = use_cpc or use_msx2 or use_next or use_sms or use_gb
    songs, songmap = gen_scenes.song_setup(doc)
    song_blobs = []
    song_packed = []
    song_bank = []
    song_off = []
    song_ws_size = 0
    scene_song = []
    if music_target:
        music_dir = os.path.join(gdir, "assets", "music")
        song_blobs = gen_scenes.load_song_blobs(songs, music_dir)
        if use_gb:
            import gbmusic
            try:
                song_blobs = [gbmusic.pt3_to_gb(b, name=sid)
                              for sid, b in zip(songs, song_blobs)]
            except gbmusic.GbMusicError as err:
                sys.exit(f"Game Boy music: {err}")
            song_packed = list(song_blobs)
        else:
            if use_sms:
                import smsmusic
                try:
                    song_blobs = [smsmusic.pt3_to_psg(b, name=sid)
                                  for sid, b in zip(songs, song_blobs)]
                except smsmusic.SmsMusicError as err:
                    sys.exit(f"SMS music: {err}")
                song_ws_size = max(map(len, song_blobs), default=0)
            else:
                song_ws_size = gen_scenes.max_song_size(song_blobs)
            # The CPC 464 loader lends its 2K stream buffer to CAS_IN_OPEN when
            # reading a song; reserve at least that much in the workspace (the
            # decoded module itself is usually smaller).
            if use_cpc464 and song_ws_size:
                song_ws_size = max(song_ws_size, 2048)
            song_packed = [gen_scenes.pack_blob(
                               gen_scenes.zx0_compress(b, gdir))
                           for b in song_blobs]
        scene_song = gen_scenes.scene_song_array(scenes, doc, songmap)
    # Game Boy Color has no SM83 ZX0 decoder, so its blobs stay raw and are
    # copied by gb_copy.asm. All other portable targets keep the compressed
    # format.
    if use_gb:
        scene_store = [gen_scenes.pack_blob(b) for b in scene_raw]
        inv_store = gen_scenes.pack_blob(inv_raw) if inv_raw else b""
    else:
        scene_store = [gen_scenes.zx0_compress(b, gdir) for b in scene_raw]
        inv_store = gen_scenes.zx0_compress(inv_raw, gdir) if inv_raw else b""
    art_rows = 12
    art_blobs = []
    art_ntiles = []
    art_bank = []
    art_off = []
    cpc_options = {}
    cpc_art_load_size = 2
    c64_options = {}
    c64_art_data = b""
    nes_options = {}
    nes_art_data = b""
    nes_chr_data = b""
    oric_options = {}
    oric_art_data = b""
    # Text colours follow the `# Game` settings; each target gets its own
    # hardware ink/CRAM value or an MSX2 little-endian palette pair.
    port_text_ink = 13
    port_highlight_ink = 18
    port_text_bg = 0
    msx2_options = {}
    msx2_font_bank = 0
    cpc_ws_base = CPC_SONG_WS
    cpc_song_addr = CPC_SONG_WS
    gb_options = {}
    gb_scene_bank = []
    gb_scene_off = []
    gb_inv_bank = 0
    gb_inv_off = 0
    gb_text_palette = []
    gb_text_pal = 0
    gb_text_sel_pal = 0
    gb_art_pal_base = 0
    next_scene_bank = []
    next_scene_off = []
    next_inv_bank = 0
    next_inv_off = 0
    next_art_pal_bank = []
    next_art_pal_off = []
    next_stage_ws_size = 1
    next_options = {}
    next_text = (0, 0)
    next_highlight = (4, 0)
    next_bg = (0, 0)
    next_title = (0, 0)
    if use_next:
        import targets
        target = targets.get_target("next")
        if target is None:
            sys.exit("ZX Next target is not registered")
        next_options = targets.target_options(doc, target)
        art_rows = int(next_options.get("art_rows") or 10)
        colours = scenefile.text_colours(game)
        next_text = colours["text"]
        next_highlight = colours["highlight"]
        next_bg = colours["bg"]
        token = next_options.get("title_ink")
        if not token or token == scenefile.TITLE_INK_INHERIT:
            next_title = next_text
        else:
            next_title = scenefile.WORD_INKS.get(str(token).strip().lower(),
                                                 next_text)
    if use_msx2:
        import targets
        target = targets.get_target("msx2")
        if target is None:
            sys.exit("MSX2 target is not registered")
        msx2_options = targets.target_options(doc, target)
        art_rows = int(msx2_options.get("art_rows") or 12)
    if use_gb:
        import gbart
        import targets
        target = targets.get_target("gb")
        if target is None:
            sys.exit("Game Boy Color target is not registered")
        gb_options = targets.target_options(doc, target)
        art_rows = int(gb_options.get("art_rows") or 8)
        text_ink, highlight_ink, text_bg = gbart.text_colours(game)
        gb_text_palette = [text_bg, text_bg, text_bg, text_ink,
                           text_bg, text_bg, text_bg, highlight_ink]
        gb_text_pal = gbart.TEXT_PALETTE
        gb_text_sel_pal = gbart.TEXT_SEL_PALETTE
        gb_art_pal_base = 0
    if use_c64:
        import c64art
        import targets
        target = targets.get_target("c64")
        if target is None:
            sys.exit("Commodore 64 target is not registered")
        c64_options = targets.target_options(doc, target)
        art_rows = int(c64_options.get("art_rows") or 8)
        port_text_ink, port_highlight_ink, port_text_bg = \
            c64art.text_colours(game)
        _write_sms_font(bdir)
    if use_nes:
        import nesart
        import targets
        target = targets.get_target("nes")
        if target is None:
            sys.exit("NES target is not registered")
        nes_options = targets.target_options(doc, target)
        art_rows = int(nes_options.get("art_rows") or 10)
        port_text_ink, port_highlight_ink, port_text_bg = \
            nesart.text_colours(game)
    if use_oric:
        import oricart
        import targets
        target = targets.get_target("oric")
        if target is None:
            sys.exit("Oric Atmos target is not registered")
        oric_options = targets.target_options(doc, target)
        art_rows = int(oric_options.get("art_rows") or 8)
        port_text_ink, port_highlight_ink, port_text_bg = \
            oricart.text_colours(game)
        _write_oric_font(bdir)
    if use_cpc:
        import targets
        cpc_target_id = "cpc464" if use_cpc464 else "cpc"
        target = targets.get_target(cpc_target_id)
        if target is None:
            sys.exit(f"{cpc_target_id} target is not registered")
        cpc_options = targets.target_options(doc, target)
        art_rows = int(cpc_options.get("art_rows") or
                       (8 if use_cpc464 else 12))
        cpc_ws_base, cpc_song_addr = _cpc_ws_layout(
            max(1, max(map(len, scene_raw), default=1)),
            max(1, len(inv_raw) if inv_raw else 1),
            song_ws_size)
        if cpc_ws_base < 0x8000:
            sys.exit("CPC workspaces do not fit below 0xA600; shorten the "
                     "game or lower cpc_art_rows")
    if use_sms:
        import targets
        target = targets.get_target("sms")
        if target is None:
            sys.exit("SMS target is not registered")
        sms_options = targets.target_options(doc, target)
        art_rows = int(sms_options.get("art_rows") or 12)
        _write_sms_font(bdir)
        import smsart
        port_text_ink, port_highlight_ink, port_text_bg = \
            smsart.text_colours(game)
        art_root = os.path.join(gdir, "assets", "art")
        gen_dir = os.path.join(gdir, "assets", "gen")
        for art in arts:
            path = scenefile.resolve_art_image(art_root, art, gen_dir)
            if path and os.path.exists(path):
                conv = scenefile.conversion_options(art, game, system)
                blob, ntiles = smsart.art_blob(
                    path, conv, art_rows, text_ink=port_text_ink,
                    text_bg=port_text_bg)
            else:
                blob, ntiles = smsart.blank_blob(
                    art_rows, text_ink=port_text_ink,
                    text_bg=port_text_bg), 0
            if len(blob) > 0x4000:
                sys.exit(f"art {art['id']!r}: {len(blob)}B does not fit one "
                         "16K SMS bank")
            art_blobs.append(blob)
            art_ntiles.append(ntiles)
        if len(art_blobs) > 30:
            sys.exit(f"{len(art_blobs)} arts need more than the 30 data banks "
                     "(BANK_02..BANK_1F)")
        asm = ["; generated by tools/gen_port.py - do not edit"]
        for i, blob in enumerate(art_blobs):
            bank = 2 + i
            path = os.path.join(bdir, f"port_bank{bank:02d}.bin")
            with open(path, "wb") as f:
                f.write(blob)
            asm.append(f"SECTION BANK_{bank:02X}")
            asm.append('    BINARY "%s"' % path.replace("\\", "/"))
        with open(os.path.join(bdir, "port_banks.asm"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(asm) + "\n")
        if song_packed:
            song_start = 2 + len(art_blobs)
            if song_start > 0x1F:
                sys.exit("SMS art banks leave no room for the songs; "
                         "remove arts or lower sms art_rows")
            song_data, song_bank, song_off = _bank_pack(song_packed,
                                                        song_start)
            if max(song_data) > 0x1F:
                sys.exit("SMS art/song data needs more than the 30 data "
                         "banks (BANK_02..BANK_1F)")
            _write_bank_asm(bdir, "port_song.asm", song_data,
                            "port_song_bank")
        else:
            with open(os.path.join(bdir, "port_song.asm"), "w",
                      encoding="utf-8") as f:
                f.write("; generated by tools/gen_port.py - do not edit\n")
    elif use_cpc:
        import cpcart
        port_text_ink, port_highlight_ink, port_text_bg = \
            cpcart.text_colours(game)
        art_root = os.path.join(gdir, "assets", "art")
        gen_dir = os.path.join(gdir, "assets", "gen")
        # Banks 4..7 are the 6128's extra 64K.  BANK_2 is base RAM at
        # 0x8000; it holds the overflow above a small stack/heap reserve.
        # Music builds leave BANK_2 free for the resident song workspace.
        bank_max = {2: 0x2000, 4: 0x4000, 5: 0x4000, 6: 0x4000, 7: 0x4000}
        packed_arts = []
        for art in arts:
            path = scenefile.resolve_art_image(art_root, art, gen_dir)
            conv = scenefile.conversion_options(art, game, system)
            blob = (cpcart.art_blob(path, conv, cpc_options,
                                    port_text_ink, port_highlight_ink,
                                    port_text_bg)
                    if path else None)
            if blob is None:
                blob = cpcart.blank_blob(cpc_options.get("mode", 1),
                                         cpc_options.get("art_rows", 12),
                                         port_text_ink, port_highlight_ink,
                                         port_text_bg)
            packed = gen_scenes.pack_blob(gen_scenes.zx0_compress(blob, gdir))
            if len(packed) > 0x4000:
                sys.exit(f"art {art['id']!r}: {len(packed)}B does not fit one "
                         "CPC 16K bank")
            packed_arts.append(packed)
            art_blobs.append(blob)
            art_ntiles.append(0)
        # The 464 streams songs from the disk with CAS IN CHAR.  Packing them
        # before the art keeps the song offset inside the 2K AMSDOS buffer, so
        # the load never has to skip across a whole bank one byte at a time.
        packed_all = (song_packed + packed_arts if use_cpc464
                      else packed_arts + song_packed)
        packed_result = _cpc_pack(packed_all, bank_max,
                                  allow_bank2=(use_cpc464 or not songs))
        if packed_result is None:
            if use_cpc464:
                sys.exit(f"CPC 464 art/song data does not fit the disk banks "
                         f"({sum(len(v) for v in packed_all)}B packed); "
                         "lower cpc464_art_rows, remove arts or shorten the "
                         "songs")
            if songs:
                sys.exit(f"CPC art/song data does not fit the 6128's four "
                         f"extra 16K banks ({sum(len(v) for v in packed_all)}B "
                         "packed); lower cpc_art_rows, remove arts or shorten "
                         "the songs")
            sys.exit(f"CPC art data does not fit the 6128's art banks "
                     f"({sum(len(v) for v in packed_all)}B packed); lower "
                     "cpc_art_rows or use fewer arts")
        cpc_art_load_size = max(2, max(map(len, packed_all), default=2))
        bank_data, all_bank, all_off = packed_result
        if use_cpc464:
            song_bank = all_bank[:len(song_packed)]
            song_off = all_off[:len(song_packed)]
            art_bank = all_bank[len(song_packed):]
            art_off = all_off[len(song_packed):]
        else:
            art_bank = all_bank[:len(packed_arts)]
            art_off = all_off[:len(packed_arts)]
            song_bank = all_bank[len(packed_arts):]
            song_off = all_off[len(packed_arts):]
        asm = ["; generated by tools/gen_port.py - do not edit"]
        for bn, data_bytes in bank_data.items():
            if not data_bytes:
                continue
            path = os.path.join(bdir, f"port_art_bank{bn}.bin")
            with open(path, "wb") as f:
                f.write(data_bytes)
            rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
            asm.append(f"SECTION BANK_{bn}")
            asm.append(f"PUBLIC _port_art_bank{bn}")
            asm.append(f"_port_art_bank{bn}:")
            asm.append(f'    BINARY "{rel}"')
        with open(os.path.join(bdir, "port_art.asm"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(asm) + "\n")
        _write_cpc_font(bdir)
        with open(os.path.join(bdir, "port_ws.asm"), "w",
                  encoding="utf-8") as f:
            f.write("; generated by tools/gen_port.py - do not edit\n")
            f.write("PUBLIC _scene_ws\n")
            f.write("PUBLIC _inv_ws\n")
            f.write("defc _scene_ws = 0x%04X\n" % cpc_ws_base)
            f.write("defc _inv_ws = 0x%04X\n" % cpc_ws_base)
    elif use_msx2:
        import msx2art
        msx2_text_ink, msx2_highlight_ink, msx2_bg = \
            msx2art.text_colours(game)
        port_text_ink = msx2art.palette_pair(msx2_text_ink)
        port_highlight_ink = msx2art.palette_pair(msx2_highlight_ink)
        port_text_bg = msx2art.palette_pair(msx2_bg)
        art_root = os.path.join(gdir, "assets", "art")
        gen_dir = os.path.join(gdir, "assets", "gen")
        asm = ["; generated by tools/gen_port.py - do not edit"]
        for art in arts:
            path = scenefile.resolve_art_image(art_root, art, gen_dir)
            conv = scenefile.conversion_options(art, game, system)
            blob = None
            if path and os.path.exists(path):
                blob = msx2art.art_blob(path, conv, {"art_rows": art_rows},
                                        msx2_text_ink, msx2_highlight_ink,
                                        msx2_bg)
            if blob is None:
                blob = msx2art.blank_blob(art_rows, msx2_text_ink,
                                          msx2_highlight_ink, msx2_bg)
            palette = blob[:32]
            bitmap = blob[32:]
            packed = bytearray(palette)
            for off in range(0, len(bitmap), 2048):
                strip = gen_scenes.zx0_compress(bitmap[off:off + 2048], gdir)
                packed += len(strip).to_bytes(2, "little") + strip
            if len(packed) > 0x4000:
                sys.exit(f"art {art['id']!r}: compressed {len(packed)}B does "
                         "not fit one 16K MSX2 bank")
            bank = 2 + len(art_blobs)
            if bank > 0xFF:
                sys.exit("MSX2 art data needs more than 254 banks")
            out_bin = os.path.join(bdir, f"port_art_bank{bank}.bin")
            with open(out_bin, "wb") as f:
                f.write(packed)
            rel = os.path.relpath(out_bin, ROOT).replace(os.sep, "/")
            asm.append(f"SECTION BANK_{bank:02X}")
            asm.append(f'    BINARY "{rel}"')
            art_bank.append(bank)
            art_off.append(0)
            art_blobs.append(bytes(packed))
            art_ntiles.append(0)
        with open(os.path.join(bdir, "port_art.asm"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(asm) + "\n")
        if int(msx2_options.get("columns") or 64) == 64:
            msx2_font = _msx2_font8_bytes()
        else:
            msx2_font = _cpc_font_bytes()
        if song_packed:
            song_data, song_bank, song_off = _bank_pack(
                song_packed, 2 + len(arts))
            if max(song_data) > 0xFF:
                sys.exit("MSX2 song data needs more than 255 banks")
            _write_bank_asm(bdir, "port_song.asm", song_data,
                            "port_song_bank")
            msx2_font_bank = max(song_data) + 1
        else:
            with open(os.path.join(bdir, "port_song.asm"), "w",
                      encoding="utf-8") as f:
                f.write("; generated by tools/gen_port.py - do not edit\n")
            msx2_font_bank = 2 + len(arts)
        if msx2_font_bank > 0xFF:
            sys.exit("MSX2 font data needs more than 255 banks")
        font_bin = os.path.join(bdir, f"port_font_bank{msx2_font_bank}.bin")
        with open(font_bin, "wb") as f:
            f.write(msx2_font)
        rel = os.path.relpath(font_bin, ROOT).replace(os.sep, "/")
        with open(os.path.join(bdir, "port_font.asm"), "w",
                  encoding="utf-8") as f:
            f.write("; generated by tools/gen_port.py - do not edit\n")
            f.write("SECTION BANK_%02X\n" % msx2_font_bank)
            f.write('    BINARY "%s"\n' % rel)
    elif use_next:
        import nextart

        for name in os.listdir(bdir):
            if name.startswith("port_next_bank") and name.endswith(".bin"):
                os.remove(os.path.join(bdir, name))

        # Banks 8..15 hold Layer 2 palettes (32 per 16K bank).  Art starts at
        # bank 16; each art reserves three 16K banks so Layer 2 can always read
        # its full 48K window, even when only the top band is visible.
        PAL_BASE = 8
        ART_BASE = 16
        next_banks = {}
        palette_data = {}
        try:
            accent_src = open(os.path.join(gdir, "game.md"), encoding="utf-8").read()
        except OSError:
            accent_src = ""
        accent_chars = [ch for ch in gen_scenes.ACCENT_BYTES
                        if ch in accent_src]
        accent_chars.sort(key=lambda ch: gen_scenes.ACCENT_BYTES[ch])
        accent_slots = []
        accent_glyphs = []
        for ch in accent_chars:
            b = gen_scenes.ACCENT_BYTES[ch]
            accent_slots.append((b - 32) * 8)
            for nib in gen_scenes.ACCENT_GLYPHS[b]:
                accent_glyphs.append((nib << 4) | nib)
        art_root = os.path.join(gdir, "assets", "art")
        gen_dir = os.path.join(gdir, "assets", "gen")
        for i, art in enumerate(arts):
            path = scenefile.resolve_art_image(art_root, art, gen_dir)
            conv = scenefile.conversion_options(art, game, system)
            if path and os.path.exists(path):
                pixels, palette = nextart.art_blob(
                    path, conv, {"art_rows": art_rows})
            else:
                pixels, palette = nextart.blank_blob({"art_rows": art_rows})
            # Layer 2 row 0 is the screen's top line; the story band begins on
            # character row 1, so leave eight blank pixel rows before it.
            layer2 = bytes(256 * 8) + pixels
            for k in range(3):
                chunk = layer2[k * 0x4000:(k + 1) * 0x4000]
                if len(chunk) < 0x4000:
                    chunk += bytes(0x4000 - len(chunk))
                next_banks[ART_BASE + 3 * i + k] = chunk
            art_bank.append(ART_BASE + 3 * i)
            art_off.append(0)
            art_ntiles.append(0)
            art_blobs.append(layer2)
            pal_bank = PAL_BASE + i // 32
            pal_off = (i % 32) * 512
            data = palette_data.setdefault(pal_bank, bytearray())
            if len(data) < pal_off:
                data += bytes(pal_off - len(data))
            data[pal_off:pal_off + 512] = palette
            next_art_pal_bank.append(pal_bank)
            next_art_pal_off.append(pal_off)
        for bn, data in palette_data.items():
            if len(data) < 0x4000:
                data += bytes(0x4000 - len(data))
            next_banks[bn] = bytes(data[:0x4000])

        # Scene/inventory blobs are [u16 compressed length][ZX0 stream], so
        # plat_load can copy the exact stream into the staging buffer.
        packed_scenes = [gen_scenes.pack_blob(c) for c in scene_store]
        packed_inv = gen_scenes.pack_blob(inv_store) if inv_store else b""
        stage_sizes = [len(c) for c in scene_store]
        if inv_store:
            stage_sizes.append(len(inv_store))
        stage_sizes += [max(1, len(p) - 2) for p in song_packed]
        next_stage_ws_size = max(stage_sizes or [1])
        combined = ([packed_inv] if packed_inv else []) + packed_scenes
        font_bank = ART_BASE + 3 * len(arts)
        scene_start = font_bank + 1
        bank_data, banks, offs = _bank_pack(combined, scene_start)
        scene_pos = 1 if packed_inv else 0
        if packed_inv:
            next_inv_bank = banks[0]
            next_inv_off = offs[0]
        next_scene_bank = banks[scene_pos:]
        next_scene_off = offs[scene_pos:]
        song_start = (max(bank_data) + 1) if bank_data else scene_start
        if song_packed:
            song_data, song_bank, song_off = _bank_pack(song_packed,
                                                        song_start)
            bank_data.update(song_data)
        else:
            song_bank = []
            song_off = []
        next_banks.update({bn: bytes(data) for bn, data in bank_data.items()})
        if next_banks and max(next_banks) > 111:
            sys.exit("ZX Next data needs 16K bank %d; the .nex limit is 111"
                     % max(next_banks))
        _write_next_bank_asm(bdir, "port_next_data.asm", next_banks,
                             "port_next_bank")
        font = open(gen_scenes.BASE_FONT, "rb").read()
        slots_bin = b"".join(int(x).to_bytes(2, "little")
                             for x in accent_slots)
        glyphs_bin = bytes(accent_glyphs)
        font_bin = os.path.join(bdir, "port_next_font.bin")
        with open(font_bin, "wb") as f:
            f.write(font + slots_bin + glyphs_bin)
        font_rel = os.path.relpath(font_bin, ROOT).replace(os.sep, "/")
        with open(os.path.join(bdir, "port_next_font.asm"), "w",
                  encoding="utf-8") as f:
            f.write("; generated by tools/gen_port.py - do not edit\n")
            f.write("SECTION BANK_%d\n" % font_bank)
            f.write('    BINARY "%s"\n' % font_rel)
        if font_bank > 111:
            sys.exit("ZX Next font bank %d exceeds the .nex limit" % font_bank)

    elif use_gb:
        import gbart
        from PIL import Image

        # Remove banks left by an earlier GB/GBC generation so appmake cannot pick
        # up a stale higher bank after the game shrinks.
        for name in os.listdir(bdir):
            if name.endswith(".bin") and (
                    name.startswith("port_gb_scene_bank")
                    or name.startswith("port_gb_art_bank")
                    or name.startswith("port_gb_song_bank")):
                os.remove(os.path.join(bdir, name))

        # port_data.c lives in bank 0.  Scenes/inventory start at bank 1; pack
        # the inventory first, then the scenes, so the table is contiguous.
        combined = ([inv_store] if inv_store else []) + scene_store
        bank_data, banks, offs = _bank_pack(combined, 1)
        scene_pos = 1 if inv_store else 0
        if inv_store:
            gb_inv_bank = banks[0]
            gb_inv_off = offs[0]
        gb_scene_bank = banks[scene_pos:]
        gb_scene_off = offs[scene_pos:]
        _write_bank_asm(bdir, "port_gb_scene.asm", bank_data,
                        "port_gb_scene_bank")
        art_start = (max(bank_data) + 1) if bank_data else 1
        art_root = os.path.join(gdir, "assets", "art")
        gen_dir = os.path.join(gdir, "assets", "gen")
        art_data = {}
        art_bank = []
        art_off = []
        last_bank = art_start
        for art in arts:
            path = scenefile.resolve_art_image(art_root, art, gen_dir)
            conv = scenefile.conversion_options(art, game, system)
            if path and os.path.exists(path):
                blob, ntiles = gbart.art_blob(
                    Image.open(path).convert("RGB"), conv, art_rows,
                    gbart.MAX_ART_TILES, gbart.MAX_ART_PALETTES)
            else:
                blob, ntiles = gbart.blank_blob(art_rows), 0
            if len(blob) > 0x4000:
                sys.exit(f"art {art['id']!r}: {len(blob)}B does not fit one "
                         "16K Game Boy Color bank")
            if (last_bank not in art_data
                    or len(art_data[last_bank]) + len(blob) > 0x4000):
                last_bank = art_start + len(art_data)
            art_data.setdefault(last_bank, bytearray())
            art_bank.append(last_bank)
            art_off.append(len(art_data[last_bank]))
            art_data[last_bank] += blob
            art_blobs.append(blob)
            art_ntiles.append(ntiles)
        if art_data:
            _write_bank_asm(bdir, "port_gb_art.asm", art_data,
                            "port_gb_art_bank")
        else:
            with open(os.path.join(bdir, "port_gb_art.asm"), "w",
                      encoding="utf-8") as f:
                f.write("; generated by tools/gen_port.py - do not edit\n")
        used = set(bank_data) | set(art_data)
        song_start = (max(used) + 1) if used else 1
        if song_packed:
            song_data = {}
            bank = song_start
            for stream in song_packed:
                if not stream:
                    sys.exit("Game Boy song converted to an empty stream")
                song_bank.append(bank)
                song_off.append(0)
                for off in range(0, len(stream), 0x4000):
                    song_data[bank] = stream[off:off + 0x4000]
                    bank += 1
            if max(song_data) > 0x1F:
                sys.exit(
                    "Game Boy song data needs 16K bank %d; the MBC1 appmake "
                    "limit is bank 0x1F" % max(song_data))
            _write_bank_asm(bdir, "port_gb_song.asm", song_data,
                            "port_gb_song_bank")
        else:
            with open(os.path.join(bdir, "port_gb_song.asm"), "w",
                      encoding="utf-8") as f:
                f.write("; generated by tools/gen_port.py - do not edit\n")
        _write_gb_font(bdir)

    elif use_c64:
        import c64art
        art_root = os.path.join(gdir, "assets", "art")
        gen_dir = os.path.join(gdir, "assets", "gen")
        art_data = bytearray()
        for art in arts:
            path = scenefile.resolve_art_image(art_root, art, gen_dir)
            conv = scenefile.conversion_options(art, game, system)
            if path and os.path.exists(path):
                blob, ntiles = c64art.art_blob(
                    path, conv, art_rows, port_text_ink, port_text_bg)
            else:
                blob, ntiles = c64art.blank_blob(
                    art_rows, port_text_ink, port_text_bg), 0
            max_ws = 3 + c64art.MAX_ART_TILES * 8 + 2 * 40 * art_rows
            if len(blob) > max_ws:
                sys.exit(f"art {art['id']!r}: {len(blob)}B exceeds the "
                         f"{max_ws}B C64 art workspace")
            packed = gen_scenes.zx0_compress(blob, gdir)
            art_bank.append(0)
            art_off.append(len(art_data))
            art_data += packed
            art_blobs.append(blob)
            art_ntiles.append(ntiles)
        c64_art_data = bytes(art_data)

    elif use_nes:
        import nesart
        art_root = os.path.join(gdir, "assets", "art")
        gen_dir = os.path.join(gdir, "assets", "gen")
        font8 = open(gen_scenes.FONT8X8, "rb").read()
        fnormal, fhilite = nesart.font_tiles(
            font8, gen_scenes.ACCENT_GLYPHS_8X8)
        chr_banks = [nesart.chr_bank(fnormal, fhilite, [])]
        art_data = bytearray()
        for art in arts:
            path = scenefile.resolve_art_image(art_root, art, gen_dir)
            conv = scenefile.conversion_options(art, game, system)
            if path and os.path.exists(path):
                blob, ntiles, tiles = nesart.art_blob(
                    path, conv, art_rows, port_text_ink, port_text_bg)
            else:
                blob = nesart.blank_blob(
                    art_rows, port_text_ink, port_text_bg)
                ntiles, tiles = 0, []
            bank = len(chr_banks)
            if bank > 15:
                sys.exit("NES art data needs 8KB CHR bank %d; MMC1 8KB CHR "
                         "mode only addresses 16 banks" % bank)
            chr_banks.append(nesart.chr_bank(fnormal, fhilite, tiles))
            art_bank.append(bank)
            art_off.append(len(art_data))
            art_data += blob
            art_blobs.append(blob)
            art_ntiles.append(ntiles)
        nes_chr_data = b"".join(chr_banks)
        nes_art_data = bytes(art_data)
        with open(os.path.join(bdir, "port_nes_chr.bin"), "wb") as f:
            f.write(nes_chr_data)

    elif use_oric:
        import oricart
        art_root = os.path.join(gdir, "assets", "art")
        gen_dir = os.path.join(gdir, "assets", "gen")
        art_data = bytearray()
        for art in arts:
            path = scenefile.resolve_art_image(art_root, art, gen_dir)
            conv = scenefile.conversion_options(art, game, system)
            if path and os.path.exists(path):
                blob, _ = oricart.art_blob(path, conv, art_rows)
            else:
                blob, _ = oricart.blank_blob(art_rows)
            packed = gen_scenes.zx0_compress(blob, gdir)
            art_bank.append(0)
            art_off.append(len(art_data))
            art_data += bytes((oricart.INK, oricart.PAPER)) + packed
            art_blobs.append(blob)
            art_ntiles.append(0)
        oric_art_data = bytes(art_data)
    data = b"".join(scene_store)
    offs = []
    pos = 0
    for blob in scene_store:
        offs.append(pos)
        pos += len(blob)
    start_ids = [flag_map[n] for n in game.get("start", []) if n in flag_map]
    names = [item_names.get(n, n) for n in item_list]
    name_off = []
    name_bytes = bytearray()
    for name in names:
        name_off.append(len(name_bytes))
        name_bytes += gen_scenes.esc_bytes(name)
    if use_msx2:
        data_size = len(data) + len(inv_store or b"") + len(name_bytes) + 32
        if music_target and songs:
            data_size += len(scenes) + 3 * len(songs)
        if data_size > 0x4000:
            sys.exit(f"MSX2 scene/inventory data is {data_size}B but must fit "
                     "one 16K bank; shorten the game")
    h = []
    c = []
    have_art = (use_sms or use_cpc or use_msx2 or use_gb or use_next
                or use_c64 or use_nes or use_oric)
    port_cols = (40 if use_c64 or use_oric else
                 32 if use_nes else
                 20 if use_gb else
                 64 if use_next else
                 int(msx2_options.get("columns") or 64) if use_msx2 else
                 int(cpc_options.get("columns") or 32) if use_cpc else 32)
    port_art_mode = int(cpc_options.get("mode") or 0) if use_cpc else 0
    # SMS, Game Boy Color, C64, NES and CPC Mode 0 always use the dialog;
    # ZX/MSX2/Oric and CPC Modes 1/2 opt in with their system's `menu: popup`.
    overlay_menu = (use_sms or use_gb or use_c64 or use_nes
                    or (use_oric and bool(oric_options.get("menu")))
                    or (use_cpc and (port_art_mode == 0
                                     or bool(cpc_options.get("menu"))))
                    or (use_msx2 and bool(msx2_options.get("menu")))
                    or (use_next and bool(next_options.get("menu"))))
    if use_next:
        port_text_ink = next_text[0]
        port_highlight_ink = next_highlight[0]
        port_text_bg = next_bg[0]
    text_width = (38 if use_c64 else
                  40 if use_oric else
                  30 if use_nes else
                  62 if use_next else
                  20 if use_gb else (30 if use_sms else port_cols))
    opt_width = (36 if use_c64 else
                 38 if use_oric else
                 28 if use_nes else
                 62 if use_next else
                 18 if use_gb else (28 if use_sms else (port_cols - 2)))
    opt_indent = 1
    defines = [
        ("PORT_COLS", port_cols),
        ("N_SCENES", len(scenes)),
        ("N_ITEMS", len(item_list)),
        ("N_FLAGS", len(flag_map)),
        ("FLAG_BASE", scenefile.FLAG_BASE),
        ("ITEM_BASE", scenefile.ITEM_BASE),
        ("SCENE_NONE", scenefile.SCENE_NONE),
        ("FLAG_NONE", scenefile.FLAG_NONE),
        ("GAME_CARRY", int(game.get("carry", 0) or 0)),
        ("N_START", len(start_ids)),
        ("PORT_SCENE_WS", max(1, max(map(len, scene_raw), default=1))),
        ("PORT_INV_WS", max(1, len(inv_raw) if inv_raw else 1)),
        ("HAVE_ITEM_DESC", 1 if have_desc else 0),
        ("HAVE_ITEM_OPTS", 1 if have_opts else 0),
        ("HAVE_INV_BLOB", 1 if inv_raw else 0),
        ("HAVE_WORDS", 1 if any_words else 0),
        ("HAVE_MESSAGES", 1 if have_messages else 0),
        ("NEED_PASSWORD", 1 if (game.get("password") or "").strip() else 0),
        ("N_ART", len(arts)),
        ("HAVE_ART", 1 if have_art else 0),
        ("PORT_ART_ROWS", art_rows if have_art else 0),
        ("PORT_ART_MODE", port_art_mode),
        ("PORT_TEXT_INK", port_text_ink),
        ("PORT_HIGHLIGHT_INK", port_highlight_ink),
        ("PORT_TEXT_BG", port_text_bg),
        ("PORT_TEXT_TOP", (2 if use_nes else 1)
                          + (art_rows if have_art else 0)),
        ("PORT_ART_TOP", 2 if use_nes else 1),
        ("SMS_FONT_TILES", 98 if use_sms else 0),
        ("PORT_TEXT_WIDTH", text_width),
        ("PORT_OPT_WIDTH", opt_width),
        ("PORT_OPT_INDENT", opt_indent),
        ("PORT_DESC_WIDTH", 40 if use_oric else (opt_width if use_c64
                            else (30 if use_nes else port_cols))),
        ("PORT_SCROLL_UP", '"\\x01"' if (use_sms or use_gb) else '"^"'),
        ("PORT_SCROLL_DOWN", '"\\x02"' if (use_sms or use_gb) else '"v"'),
        ("PORT_SIMPLE_OPTIONS", 1 if (use_cpc or use_next) else 0),
        ("PORT_KEEP_ART", 1 if (use_msx2 or use_cpc or use_next
                                or use_c64 or use_nes or use_oric) else 0),
        ("PORT_ART_CLEARS_TEXT", 1 if use_cpc else 0),
        ("PORT_NO_TEXT_SCROLL", 1 if (use_msx2 or (use_next and not overlay_menu)) else 0),
        ("PORT_NO_DESC_SCROLL", 1 if (use_next and not overlay_menu) else 0),
        ("PORT_NO_ENTRY_WRAP", 1 if (use_next and not overlay_menu) else 0),
        ("PORT_MARKER_BODY", 1 if use_nes else 0),
        ("PORT_ATOMIC_MENU", 1 if use_nes else 0),
        ("PORT_OVERLAY_MENU", 1 if overlay_menu else 0),
        ("PORT_BANKED_SCENES", 1 if (use_gb or use_next) else 0),
        ("GB_ART_TILE_BASE", 96 if use_gb else 0),
        ("GB_MAX_ART_TILES", 158 if use_gb else 0),
        ("GB_TEXT_PAL", gb_text_pal),
        ("GB_TEXT_SEL_PAL", gb_text_sel_pal),
        ("GB_ART_PAL_BASE", gb_art_pal_base),
        ("N_SONGS", len(songs) if music_target else 0),
        ("PORT_MUSIC_PSG", 1 if use_sms else 0),
        ("PORT_MUSIC_GB", 1 if use_gb else 0),
        ("SONG_NONE", gen_scenes.SONG_NONE),
        ("SONG_WS_SIZE", song_ws_size if music_target else 0),
    ]
    if use_next:
        defines += [
            ("PORT_EXTERN_WS", 1),
            ("PORT_SCROLL_COL", 61),
            ("PORT_MARKER_MATCH_CELL", 1),
            ("PORT_INV_MARK_R", 62),
            ("PORT_INV_CONTENT_COLS", 60),
            ("PORT_TEXT_MACRO", 1),
            ("PORT_TEXT_BRIGHT", next_text[1]),
            ("PORT_HIGHLIGHT_BRIGHT", next_highlight[1]),
            ("PORT_TEXT_BG_BRIGHT", next_bg[1]),
            ("PORT_TITLE_INK", next_title[0]),
            ("PORT_TITLE_BRIGHT", next_title[1]),
            ("STAGE_WS_SIZE", next_stage_ws_size),
            ("N_ACCENT_GLYPHS", len(accent_slots)),
            ("NEED_ACCENT_FONT", 1 if accent_slots else 0),
            ("NEXT_FONT_BANK", font_bank),
        ]
        if not (game.get("password") or "").strip():
            defines.append(("PORT_BOOT_MACRO", 1))
    if use_c64:
        defines += [
            ("C64_FONT_TILES", 96),
            ("C64_ART_TILES", 160),
            ("C64_ART_WS_SIZE", 3 + 160 * 8 + 2 * 40 * art_rows),
        ]
    if use_nes:
        defines += [
            ("NES_FONT_TILES", 96),
            ("NES_HILITE_TILES", 96),
            ("NES_ART_BASE", 96),
            ("NES_ART_TILES", 160),
            ("NES_CHR_BANKS", 1 + len(arts)),
        ]
    if use_cpc:
        defines.append(("SONG_WS_ADDR", cpc_song_addr))
        defines.append(("CPC_WS_BASE", cpc_ws_base))
        defines.append(("PORT_EXTERN_WS", 1))
        defines.append(("PORT_INV_OVERWRITES_ART", 1))
        defines.append(("PORT_ART_FROM_DISK", 1 if use_cpc464 else 0))
        defines.append(("CPC_ART_LOAD_SIZE", cpc_art_load_size))
    if use_msx2:
        defines.append(("PORT_DATA_BANK", 1))
        defines.append(("MSX2_FONT_BANK", msx2_font_bank))
        defines.append(("MSX2_TEXT_8PX", 1 if port_cols == 64 else 0))
    elif use_gb:
        defines.append(("PORT_DATA_BANK", 0))
    h.append("/* generated by tools/gen_port.py - do not edit */")
    for key, val in defines:
        h.append(f"#define {key} {val}")
    h.append("")
    h.append("typedef struct { unsigned char line,col,len,flag; } PortWordHdr;")
    h.append("typedef struct { unsigned short label_off, cond_off, msg_off; "
             "unsigned char next,ncond,set,unset,pick,leave,clear; } PortOptHdr;")
    h.append("typedef struct { unsigned char art,nopt,ending; unsigned short title_off; "
             "unsigned short text_off[8]; PortOptHdr opts[6]; unsigned char nwords; "
             "unsigned short words_off; } PortSceneHdr;")
    h.append("typedef struct { unsigned short label_off, cond_off, msg_off; "
             "unsigned char scene,target,ncond,set,unset,pick,leave,clear; } "
             "PortItemOptHdr;")
    h.append("extern const unsigned short port_scene_off[N_SCENES];")
    h.append("#if PORT_BANKED_SCENES")
    h.append("extern const unsigned char port_scene_bank[N_SCENES];")
    h.append("extern const unsigned char port_inv_bank;")
    h.append("extern const unsigned short port_inv_off;")
    h.append("#else")
    h.append("extern const unsigned char port_scene_data[];")
    h.append("extern const unsigned char port_inv_data[];")
    h.append("#endif")
    h.append("extern const char port_item_names[];")
    h.append("extern const unsigned short port_item_name_off[];")
    h.append("extern const unsigned char port_start_flags[];")
    h.append("extern const char port_game_title[];")
    h.append("extern const char port_game_password[];")
    h.append("extern const char port_game_password_label[];")
    h.append("extern const char port_game_popup_hint[];")
    h.append("extern const unsigned char port_art_bank[];")
    h.append("extern const unsigned short port_art_off[];")
    h.append("extern const unsigned short port_art_ntiles[];")
    if use_c64 or use_nes or use_oric:
        h.append("extern const unsigned char port_art_data[];")
    if use_nes:
        h.append("extern const unsigned char port_nes_split_xy[];")
    if use_next:
        h.append("extern const unsigned char port_art_pal_bank[];")
        h.append("extern const unsigned short port_art_pal_off[];")

    if use_gb:
        h.append("extern const unsigned short gb_text_palette[8];")
    h.append("#if N_SONGS > 0")
    h.append("extern const unsigned char scene_song[N_SCENES];")
    h.append("extern const unsigned char song_bank[N_SONGS];")
    h.append("extern const unsigned short song_off[N_SONGS];")
    h.append("#endif")
    h.append("")
    if use_gb:
        c.append("#if PORT_BANKED_SCENES")
        _arr(c, "unsigned char", "port_scene_bank", gb_scene_bank, "%d")
        _arr(c, "unsigned short", "port_scene_off", gb_scene_off, "%d")
        c.append(f"const unsigned char port_inv_bank = {gb_inv_bank};")
        c.append(f"const unsigned short port_inv_off = {gb_inv_off};")
        c.append("#endif")
        _arr(c, "unsigned short", "gb_text_palette", gb_text_palette, "%d")
    elif use_next:
        c.append("#if PORT_BANKED_SCENES")
        _arr(c, "unsigned char", "port_scene_bank", next_scene_bank or [0], "%d")
        _arr(c, "unsigned short", "port_scene_off", next_scene_off or [0], "%d")
        c.append(f"const unsigned char port_inv_bank = {next_inv_bank};")
        c.append(f"const unsigned short port_inv_off = {next_inv_off};")
        c.append("#endif")
    else:
        c.append("#if !PORT_BANKED_SCENES")
        _bytes_arr(c, "port_scene_data", data)
        _arr(c, "unsigned short", "port_scene_off", offs, "%d")
        _bytes_arr(c, "port_inv_data", inv_store)
        c.append("#endif")
    _arr(c, "char", "port_item_names", list(name_bytes), "%d")
    _arr(c, "unsigned short", "port_item_name_off", name_off or [0], "%d")
    _arr(c, "unsigned char", "port_start_flags", start_ids or [0], "%d")
    _c_string(c, "port_game_title", game.get("title", ""))
    _c_string(c, "port_game_password", game.get("password", ""))
    _c_string(c, "port_game_password_label",
              game.get("password_label") or "Enter the password:")
    _c_string(c, "port_game_popup_hint", scenefile.popup_hint(game))
    if use_sms:
        banks = [2 + i for i in range(len(art_blobs))] or [0]
        offs_art = [0] * len(art_blobs) or [0]
    elif use_cpc:
        banks = art_bank or [0]
        offs_art = art_off or [0]
    elif use_msx2 or use_gb or use_next or use_c64 or use_nes or use_oric:
        banks = art_bank or [0]
        offs_art = art_off or [0]
    else:
        banks = [0]
        offs_art = [0]
    _arr(c, "unsigned char", "port_art_bank", banks, "%d")
    _arr(c, "unsigned short", "port_art_off", offs_art, "%d")
    _arr(c, "unsigned short", "port_art_ntiles", art_ntiles or [0], "%d")
    if use_c64:
        _bytes_arr(c, "port_art_data", c64_art_data)
    elif use_nes:
        _bytes_arr(c, "port_art_data", nes_art_data)
    elif use_oric:
        _bytes_arr(c, "port_art_data", oric_art_data)
    if use_nes:
        text_top = 2 + (art_rows if have_art else 0)
        target = (20 + 8 * text_top) * 113.667 + 90

        def flush_cycles(n):
            if n == 0:
                return 12
            cycles = 17
            rem = n
            while rem:
                k = min(rem, 5)
                cycles += k * 30
                if k == rem:
                    cycles += 1
                    break
                cycles += 8
                rem -= 5
            return cycles + 12

        def loop_cycles(x, y):
            inner = y * 256 if x == 0 else x + (y - 1) * 256
            return 5 * (inner + y)

        split_xy = []
        for count in range(69):
            delay = target - 116 - flush_cycles(count)
            best = (0, 0, 0)
            for y in range(40):
                for x in range(256):
                    cyc = loop_cycles(x, y)
                    if best[2] < cyc <= delay:
                        best = (x, y, cyc)
            split_xy += [best[0] & 0xFF, best[1] & 0xFF]
        _arr(c, "unsigned char", "port_nes_split_xy", split_xy, "0x%02X")
    if use_next:
        _arr(c, "unsigned char", "port_art_pal_bank",
             next_art_pal_bank or [0], "%d")
        _arr(c, "unsigned short", "port_art_pal_off",
             next_art_pal_off or [0], "%d")

    if music_target and songs:
        _arr(c, "unsigned char", "scene_song", scene_song, "%d")
        _arr(c, "unsigned char", "song_bank", song_bank or [0], "%d")
        _arr(c, "unsigned short", "song_off", song_off or [0], "%d")
    with open(os.path.join(bdir, "port_data.h"), "w", encoding="utf-8") as f:
        f.write("\n".join(h) + "\n")
    with open(os.path.join(bdir, "port_data.c"), "w", encoding="utf-8") as f:
        f.write("/* generated by tools/gen_port.py - do not edit */\n")
        f.write('#include "port_data.h"\n\n')
        if use_msx2:
            f.write("#pragma bank 1\n\n")
        f.write("\n".join(c) + "\n")
    label = "raw" if use_gb else "compressed"
    print(f"port: {len(scenes)} scenes, {len(data)}B {label}, "
          f"inv {len(inv_store)}B, scene_ws {max(map(len, scene_raw))}B, "
          f"art {len(art_blobs)} blobs, "
          f"{len(songs) if music_target else 0} songs")


if __name__ == "__main__":
    main()
