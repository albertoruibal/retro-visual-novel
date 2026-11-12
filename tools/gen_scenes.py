#!/usr/bin/env python3
"""Convert a game's game.md into a ZX scene/art data store.

The 128K/Next build gets a banked scene+art store; the 48K build gets a
lower-RAM scene store plus monochrome art/inventory arrays in the main image.

The input is ``games/<slug>/game.md`` (or any path); the outputs are written
into the same game folder. Since the 128K build pages data in/out of 0xC000,
records cannot hold absolute pointers; every record is a self-contained blob.
Each blob is compressed with ZX0 (host tool ``z88dk-zx0``) and stored in the
bank as ``[u16 compressed length][zx0 stream]``. At runtime the length is used
to copy just the compressed bytes into an always-resident staging buffer
(``src/zx/paging.asm``), and the vendored decoder then expands them into the
caller's workspace with interrupts enabled.  Alongside ``scene_data.h`` it
writes ``port_data.h``, the shared-core view of the same bytes (no duplicate
storage): the ``port_*`` names, struct aliases and ZX layout/feature flags.

    Art blob (before compression):
        map[8*L]  row-major 16x(L/2) tile indices into the tile area
        tiles[N]  48-byte 16x16 bicolor btiles (N <= 8*L)
                  L = the active target's `art_rows` (even 8..16, default 10);
                  128K and 48K have independent `## zx128`/`## zx48` values
    Scene blob (before compression):
        SceneHdr (102 bytes):
            u8   art          art index (into the art directory)
            u8   nopt         number of options
            u8   ending       flag id set when this scene is shown (255=none)
            u16  title_off    offset from blob start to title string
            u16  text_off[8]  offsets to text lines (0 = empty); each line is
                              prefixed by [u8 ncond][(flag id, negated) * ncond]
                              (ncond=0 for a plain line); every condition must
                              hold
            struct { u16 label_off, cond_off, msg_off; u8 next, ncond,
                     set, unset, pick, leave, clear; } opts[6]
              `cond_off` points at `ncond` (flag/item id, negated) pairs;
              every condition must hold. `msg_off` points at an optional
              popup message string (0 = none). `clear` bit0 = explicit full reset.
            u8   nwords       selectable words in the scene (0 = none)
            u16  words_off    offset from blob start to the word table, or 0
        then NUL-terminated strings, then (if nwords) the word table:
            struct { u8 line, col, len, flag; } words[nwords]
        then each option's condition pairs:
            u8 flag_id, negated
        A selectable word is written `{{word}}` or `{{word|flag}}` in a text
        line: it is highlighted, joins the option cursor above the menu and, on
        ENTER, sets its flag (default the word, slugified). `col`/`len` are byte
        offsets in the rendered text line; once the flag is set the word renders
        as ordinary text and is no longer selectable.

An option's effects are four independent one-byte slots: ``set`` sets a flag,
``unset`` clears a flag, ``pick`` adds an inventory item (and hides the option
while held) and ``leave`` removes one. ``clear``, when bit0 is set, makes the
engine wipe every flag and inventory item and re-grant the ``start:`` names
before applying the option's own effects. It is how an ending's "Start again"
resets the run; plain first-scene navigation does not.

An option may carry up to ``scenefile.MAX_CONDITIONS`` ``if``/``unless`` tokens.
They are stored as ``(flag id, negated)`` pairs and all must hold. Conditions
naming a reserved ``system_*`` pseudo-flag (``SYSTEM_FLAGS`` in scenefile.py)
are evaluated for the target being generated instead: a true one is removed, a
false one drops the line/option, and no runtime flag id is allocated.

An option may end with ``msg <text>``. It consumes the rest of the line and is
stored as a popup message; the engine shows it in the text pane before applying
the option's effects and following its target.

Art, scene and song blobs (all ZX0-compressed) are packed into the same 16K
banks (Spectrum 128K banks 1,3,4,6,7; bank 5 is the screen). The home bank gets:
    art_bank[N_ART], art_off[N_ART]
    scene_bank[N_SCENES], scene_off[N_SCENES]
    song_bank[N_SONGS], song_off[N_SONGS]   (only when the game has songs)
    scene_song[N_SCENES]  (song index per scene, 255 = silence; songs only)
    inv_blob_bank[1], inv_blob_off[1]       (only when the inventory screen compiles)
    plus the SceneHdr layout used by the shared story engine.
No length arrays are emitted: the length prefix in each blob supplies it.

Songs
-----
`# Game songs:` lists ids backed by ``assets/music/<id>.pt3``. A scene's
``music:`` (or the ``# Game`` default) names one, ``off`` stops playback and
``on`` means the game default. Each module is stored ZX0-compressed and
decompressed straight into the resident ZX song workspace in lower RAM (after
``_stage_ws``) before the VT2 player plays it, so a larger *decompressed* module
is a build error. The buffer is sized per game to the largest module it ships
(``SONG_WS_SIZE``) and capped at 4158 bytes.

Flag ids
--------
Flags are ids 0..127 (32 game-state bytes, bit-packed) used for option
gating (`if`) and effects (`set`/`unset`) and endings. Ids 128..191 are
inventory items (`pick`/`leave`); each item has an ASCII id (its token in
game.md) and a display name (the `name:` of its `# Items` entry, else the id),
emitted as the home-bank ``item_names`` table. The engine renders the active
items left-to-right along the bottom inventory band line (row 23) ordered by
display name, and scrolls (marking hidden items with `<`/`>`) when they do not
fit. A `pick` option adds such an item and is hidden while it is held, so an item
cannot be picked twice; `leave` removes it again.

Accents
-------
The z88dk 4x8 console font has no accented glyphs, so ``esc_bytes`` maps
``Á Ñ á é í Ü ü ñ ó ú ¿`` onto ASCII codes whose font slots are otherwise
blank (0x5B..0x60, 0x7B..0x7F). ``scene_data.h`` emits the slot offsets and
hand-drawn 4x8 glyphs, and ``src/zx/plat_zx.c`` patches them into the CRT's own
``CRT_FONT_64`` table at startup, so no second 768-byte font is resident. Each
glyph is stored in both nibbles because 64-column printing uses the high nibble
on an even column and the low nibble on an odd one. Other non-ASCII punctuation
is still romanised (`—` -> `-`, curly quotes, `…`); anything else is an error.

Outputs:
    build/scene_data.h             home-bank macros + typedefs + extern arrays
    build/scene_data.c             the generated array definitions
    build/scene_banks/bankN.bin    raw bank images
    build/scene_bankN.asm          z80asm wrappers (SECTION BANK_N + BINARY)

game.md format (author-facing):
    # Game
    title: <game title>
    prompt: <common style prompt, prefixed to every art prompt>
                           # a prompt may span lines; 4-space-indented lines keep breaks
    start: <item, ...>     # inventory items held before the first scene
    flags: <flag, ...>     # optional: names that exist before any use
    items: <item, ...>     # optional: items that exist before any use
    songs: <id, ...>       # optional: assets/music/<id>.pt3
    music: off|<song-id>|on  # optional: default song (off if absent)
    password: <word>       # optional: boot screen before the first scene
    text_ink: <colour>     # optional: body/options/unselected-item colour (dim white)
    highlight_ink: <colour>  # optional: selection/word colour (green)
    text_bg: <colour>      # optional: text background/paper (black)
    seed/steps/cfg: <defaults>
    width/height: <output size, e.g. 512x256; `size` is a square fallback>

    # Systems              # each ## block selects a system; order = build order
    ## zx128
    art_rows: <even 8..16> # optional: art band height in 8px rows (10)
    dither: <scheme>       # optional: dither for this system (off)
    menu: popup            # optional: options/items in a SPACE dialog (inline)
    title_ink: <colour>    # optional: scene/item title (text = inherit text_ink)
    ## zx48
    art_rows: <even 8..16> # optional: independent 48K band height (10)
    ## sms
    art_rows: 8|10|12      # optional: SMS picture rows (12)
    dither: off|floyd      # optional: dither for this system (off)

    # Art
    ## <art-id>
    prompt: <subject prompt>  # may span lines; 4-space-indented lines keep breaks
    [seed/steps/cfg/width/height overrides]
    crop: <x> <y> <w> <h> # optional: source rect in % (default = centred band window)
    [match/palette/palette_colors/saturation/contrast/brightness/gamma]
                          # optional conversion overrides (else the # Game value)

    # Items                # optional: display names + inventory descriptions
    ## <item-id>
    name: <display name>   # shown in the item list; default the id (<= 58 cols)
    desc: <lines...>       # up to 4 logical lines; long lines wrap (per target)

    # Scenes               # story order; the first ## block is the start
    ## <scene-id>
    name: <title>          # optional: on-screen scene title
    art: <art-id>          # shared by any number of scenes
    ending: <flag>         # optional; set when this scene is shown
    music: off|<song-id>|on  # optional: overrides the # Game default
    text:                  # up to 8 logical lines per target; long lines wrap
      <line> -> if <flag> unless <flag>       # postfix conditions (all hold)
      ... {{selectable word|flag}} ...        # word sets its flag when chosen
    opt: <label max 62> -> <target-id|-> [if flag] [unless flag] [set flag]
                                       [unset flag] [pick item] [leave item]
                                       [clear]
                            # `-` re-enters this scene (effects apply)
"""
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamestore
import scenefile
import z88dkpath

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Spectrum 128K banks usable for paged data (0,2,5 are fixed; skip them).
BANKS = [1, 3, 4, 6, 7]
BANK_SIZE = 16384
HDR_SIZE = 1 + 1 + 1 + 2 + 16 + 6 * 13 + 1 + 2     # 102
# Selectable-word table (when a scene has any): one WordHdr (line, col, len,
# flag) per word, appended after the strings. The engine sets the word's flag
# when the player chooses it (see src/portable/core/); WORD_MAX bounds the table.
WORD_MAX = 8
# An inventory item's display name is printed straight into the band (and the
# item-screen title), so it must fit one band row: the engine indents past the
# scroll-marker column and stops short of the console's last cells, leaving 58
# columns for a name.
ITEM_NAME_COLS = 58

SCENE_NONE = scenefile.SCENE_NONE
SONG_NONE = 0xFF         # scene_song[] entry meaning "play no song"
FLAG_NONE = scenefile.FLAG_NONE
FLAG_BASE = scenefile.FLAG_BASE
ITEM_BASE = scenefile.ITEM_BASE
MAX_FLAGS = scenefile.MAX_FLAGS
MAX_ITEMS = scenefile.MAX_ITEMS
assign_flags = scenefile.assign_flags
BANK_MAGIC = 0x5C        # first byte of every resident bank
# Blobs are stored compressed with ZX0 and decompressed directly from the paged
# bank into the runtime workspace (src/zx/paging.asm). `_scene_ws` is sized per
# game to the largest raw scene blob; the linked main-image check in
# tools/build.py is the real ceiling (it must stay below the NIRVANA+ engine).
# _art_ws (src/zx/paging.asm) is a single buffer sized per game (ART_WS_SIZE) to
# hold the largest art blob or the inventory blob, decoded into the same buffer
# while the item screen is open. On 128K/Next an art is map[8*L] + 48-byte
# bicolor tiles; on 48K it is a packed 1bpp 256 x 8*L band. A ZX tile row is
# 16px = 2 character rows, so L = the ZX `art_rows` option (default L=10 ->
# map[80], max 128K blob 80 + 80*48 = 3920; 48K band 256*8*L bytes).
# AY song module ceiling. The ZX workspace lives in lower RAM after _stage_ws
# (src/zx/plat_zx.c); CPC/MSX2 use their own resident buffers. A module larger
# than this is rejected before packing.
SONG_WS = 4158
# Always-resident staging buffer the runtime copies the compressed blob into
# before decoding (src/zx/paging.asm: _stage_ws @0x6000, free lower RAM up to
# 0x8000). Every compressed blob must fit here; checked below.
STAGE_WS_MAX = 0x8000 - 0x6000

# 48K flat build: the compressed scenes live in the lower-RAM window at
# 0x6000. The top 1 KB (0x7C00-0x7FFF) is reserved for the stack. Art and
# inventory are linked into the main image (there is no NIRVANA+ engine, so the
# image may use 0x8000-0xFFFF); tools/build.py checks both budgets.
FLAT_DATA_ADDR = 0x6000
FLAT_DATA_MAX = 0x1C00          # 7168 bytes, leaving 1 KB for the stack

# Home-bank arrays must fit alongside the engine. A full directory (256 scenes
# + 128 arts, 3 x 2-byte arrays each) is ~2.3KB, well inside the fixed region.
MAX_DIR_SCENES = 256
MAX_DIR_ARTS = 128
MAX_DIR_SONGS = 64


def scene_target_id():
    """The target being generated (``zx128`` or ``zx48``), canonicalised."""
    raw = os.environ.get("SCENE_TARGET") or "zx128"
    return scenefile.canonical_target_id(raw) or "zx128"


def scene_flat():
    """Whether to emit the non-paged 48K flat data layout."""
    return str(os.environ.get("SCENE_FLAT") or "").strip() == "1"


# Accented letters are stored one byte each by remapping them onto ASCII codes
# the z88dk 4x8 console font leaves blank (no game text uses those punctuation
# marks). The mapping lives in scenefile (shared with the editor's validator);
# ACCENT_GLYPHS defines the 4x8 bitmap the engine's custom font carries in each
# slot; ADVENTURE_FONT in src/zx/plat_zx.c installs it at startup.
ACCENT_BYTES = scenefile.ACCENT_BYTES
# Each bitmap is 8 rows; a nibble per row, high nibble = leftmost 4 pixels.
ACCENT_GLYPHS = {
    0x5B: [0x01, 0x02, 0x05, 0x05, 0x07, 0x05, 0x05, 0x00],   # A-acute
    0x5C: [0x0A, 0x07, 0x05, 0x05, 0x05, 0x05, 0x05, 0x00],   # N-tilde
    0x5D: [0x01, 0x02, 0x06, 0x01, 0x07, 0x05, 0x07, 0x00],   # a-acute
    0x5E: [0x01, 0x02, 0x02, 0x05, 0x06, 0x04, 0x03, 0x00],   # e-acute
    0x5F: [0x01, 0x02, 0x00, 0x06, 0x02, 0x02, 0x07, 0x00],   # i-acute
    0x60: [0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x07, 0x00],   # U-diaeresis
    0x7B: [0x05, 0x00, 0x05, 0x05, 0x05, 0x05, 0x07, 0x00],   # u-diaeresis
    0x7C: [0x05, 0x0A, 0x06, 0x05, 0x05, 0x05, 0x05, 0x00],   # n-tilde
    0x7D: [0x01, 0x02, 0x02, 0x05, 0x05, 0x05, 0x02, 0x00],   # o-acute
    0x7E: [0x01, 0x02, 0x05, 0x05, 0x05, 0x05, 0x07, 0x00],   # u-acute
    0x7F: [0x00, 0x02, 0x00, 0x02, 0x01, 0x05, 0x02, 0x00],   # inverted question
}
# The same accent slots as full 8x8 rows for the 8x8 portable font, extracted
# from Pixel Operator Mono 8 by tools/make_font8.py and kept keyed by the same
# byte codes as ACCENT_GLYPHS, so text encoding and glyph data cannot drift.
ACCENT_GLYPHS_8X8 = {
    0x5B: [0x10, 0x08, 0x1C, 0x22, 0x22, 0x3E, 0x22, 0x00],   # A-acute
    0x5C: [0x4C, 0x32, 0x22, 0x26, 0x2A, 0x32, 0x22, 0x00],   # N-tilde
    0x5D: [0x10, 0x08, 0x1C, 0x20, 0x3C, 0x22, 0x3C, 0x00],   # a-acute
    0x5E: [0x10, 0x08, 0x1C, 0x22, 0x3E, 0x02, 0x1C, 0x00],   # e-acute
    0x5F: [0x10, 0x08, 0x0E, 0x08, 0x08, 0x08, 0x3E, 0x00],   # i-acute
    0x60: [0x14, 0x00, 0x22, 0x22, 0x22, 0x22, 0x1C, 0x00],   # U-diaeresis
    0x7B: [0x14, 0x00, 0x22, 0x22, 0x22, 0x22, 0x1C, 0x00],   # u-diaeresis
    0x7C: [0x4C, 0x32, 0x1E, 0x22, 0x22, 0x22, 0x22, 0x00],   # n-tilde
    0x7D: [0x10, 0x08, 0x1C, 0x22, 0x22, 0x22, 0x1C, 0x00],   # o-acute
    0x7E: [0x10, 0x08, 0x22, 0x22, 0x22, 0x22, 0x1C, 0x00],   # u-acute
    0x7F: [0x00, 0x08, 0x00, 0x08, 0x04, 0x02, 0x22, 0x1C],   # inverted question
}
assert set(ACCENT_GLYPHS_8X8) == set(ACCENT_GLYPHS)
# Base 768-byte z88dk 4x8 font (CRT_FONT_64), vendored for reproducible builds.
BASE_FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "zx_font64.bin")
# 96 8x8 glyphs for the Game Boy Color, SMS and MSX2 64-column text, from the
# CC0 Pixel Operator Mono 8. Rows are LSB-left; the targets flip them as
# needed (gbart.font_tiles bit-reverses for the GB pattern table).
FONT8X8 = os.path.join(ROOT, "vendor", "pixeloperator8", "font8x8.bin")


def esc_bytes(s):
    """Map accented letters onto blank font slots, romanise the rest, encode."""
    repl = {c: chr(b) for c, b in ACCENT_BYTES.items()}
    repl.update(scenefile.ROMANISE)
    for k, v in repl.items():
        s = s.replace(k, v)
    assert all(ord(c) < 128 for c in s), f"non-ASCII in scene text: {s!r}"
    return s.encode("ascii") + b"\x00"


def parse(md):
    """Parse a game's game.md via the shared reader (see tools/scenefile.py)."""
    return scenefile.parse(md)


def text_cond_header(conds, fid, where):
    """Encode a line's postfix conditions as [ncond][(flag id, negated)...]."""
    if len(conds) > scenefile.MAX_CONDITIONS:
        sys.exit(f"{where}: more than {scenefile.MAX_CONDITIONS} conditions")
    out = bytearray((len(conds),))
    for kind, name in conds:
        out += bytes((fid(name), 1 if kind == "unless" else 0))
    return bytes(out)


def build_scene_blob(b, idmap, artmap, flag_map, system="zx128"):
    def fid(name):
        if not name:
            return FLAG_NONE
        if name not in flag_map:
            sys.exit(f"scene {b['id']}: unknown flag/item {name!r}")
        return flag_map[name]

    def conds_for(rest, raw_opt):
        if re.search(r"\bifgroup\b", rest):
            sys.exit(f"scene {b['id']}: ifgroup was removed; use repeated "
                     f"`if` tokens: {raw_opt!r}")
        conds = []
        for kind, name in scenefile.option_conditions(rest):
            holds = scenefile.system_condition_holds(kind, name, system)
            if holds is False:
                return None
            if holds is True:
                continue
            if len(conds) >= scenefile.MAX_CONDITIONS:
                sys.exit(f"scene {b['id']}: option has more than "
                         f"{scenefile.MAX_CONDITIONS} conditions: {raw_opt!r}")
            if name not in flag_map:
                sys.exit(f"scene {b['id']}: condition {name!r} is not a "
                         "flag or item")
            conds.append((flag_map[name], 1 if kind == "unless" else 0))
        return conds

    title = esc_bytes(b["title"])
    ending = fid(b.get("ending"))
    opts = []
    for o in b["opts"]:
        core, msg = scenefile.split_option_msg(o)
        m = re.match(r"(.+?)\s*->\s*(\S+)(.*)$", core)
        assert m, (b["id"], o)
        label, nxt, rest = m.groups()
        set_ = re.search(r"\bset\s+(\S+)", rest)
        unset = re.search(r"\bunset\s+(\S+)", rest)
        leave = re.search(r"\bleave\s+(\S+)", rest)
        pick = re.search(r"\bpick\s+(\S+)", rest)
        clear = re.search(r"\bclear\b", rest)
        nxt_id = (idmap[b["id"]] if nxt == "-"
                  else idmap.get(nxt, SCENE_NONE))
        conds = conds_for(rest, o)
        if conds is None:
            continue
        opts.append((esc_bytes(label), nxt_id, conds,
                     fid(set_.group(1) if set_ else None),
                     fid(unset.group(1) if unset else None),
                     fid(pick.group(1) if pick else None),
                     fid(leave.group(1) if leave else None),
                     1 if clear else 0, esc_bytes(msg) if msg else b""))
    if len(opts) > 6:
        sys.exit(f"scene {b['id']}: {len(opts)} options after system_* "
                 f"folding for {system} (max 6)")

    strings = bytearray()
    title_off = HDR_SIZE
    strings += title
    text_off = []
    words = []                  # (line, col, len, flag id), line then col order
    active_lines = []
    for raw in b["text"]:
        rendered, conds = scenefile.split_text_line(raw)
        conds = scenefile.filter_system_conditions(conds, system)
        if conds is None:
            continue
        active_lines.append((rendered, conds))
    if len(active_lines) > 8:
        sys.exit(f"scene {b['id']}: {len(active_lines)} text lines after "
                 f"system_* folding for {system} (max 8)")
    for li, (rendered, conds) in enumerate(active_lines):
        # every line is stored as: [ncond][(flag id, negated) * ncond] + text.
        # A plain line has ncond=0, so the header is unambiguous.
        control = text_cond_header(conds, fid, f"scene {b['id']}: text line")
        # Escape segment by segment so a word's column is an exact byte offset in
        # the stored line even when a multi-byte mapping (`...`) precedes it.
        line_bytes = bytearray()
        for seg, wflag in scenefile.word_segments(rendered):
            eb = esc_bytes(seg)[:-1]            # drop the NUL terminator
            if wflag is not None:
                if not eb:
                    sys.exit(f"scene {b['id']}: empty {{{{...}}}} word")
                words.append((li, len(line_bytes), len(eb), fid(wflag)))
            line_bytes += eb
        line_bytes += b"\x00"                   # terminate the rendered line
        text_off.append(HDR_SIZE + len(strings))
        strings += control + bytes(line_bytes)
    if len(words) > WORD_MAX:
        sys.exit(f"scene {b['id']}: {len(words)} selectable words (max "
                 f"{WORD_MAX})")
    while len(text_off) < 8:
        text_off.append(0)
    opt_blobs = []
    for (label, nxt, conds, set_, unset, pick, leave, clear, msg) in opts:
        label_off = HDR_SIZE + len(strings)
        strings += label
        msg_off = 0
        if msg:
            msg_off = HDR_SIZE + len(strings)
            strings += msg
        opt_blobs.append((label_off, msg_off, nxt, conds, set_, unset, pick,
                          leave, clear))
    while len(opt_blobs) < 6:
        opt_blobs.append((0, 0, SCENE_NONE, [], SCENE_NONE, SCENE_NONE,
                          SCENE_NONE, SCENE_NONE, 0))

    # Word table after the strings; the engine reads it from scene_ws+words_off.
    words_off = 0
    if words:
        words_off = HDR_SIZE + len(strings)
        for (li, col, ln, wid) in words:
            strings += bytes((li, col, ln, wid))

    # Per-option condition tables go after the strings/word table. Each option
    # stores an absolute offset to its (flag id, negated) pairs.
    cond_base = HDR_SIZE + len(strings)
    cond_bytes = bytearray()
    opt_hdrs = []
    for (lo, msg_off, nxt, conds, set_, unset, pick, leave, clear) in opt_blobs:
        cond_off = cond_base + len(cond_bytes) if conds else 0
        for cid, neg in conds:
            cond_bytes += bytes((cid, neg))
        opt_hdrs.append((lo, cond_off, msg_off, nxt, len(conds), set_, unset,
                         pick, leave, clear))

    art = artmap.get(b["art"], 0)
    hdr = bytearray()
    hdr.append(art & 0xFF)
    hdr.append(min(len(opts), 6))
    hdr.append(ending)
    hdr += title_off.to_bytes(2, "little")
    for x in text_off:
        hdr += x.to_bytes(2, "little")
    for (lo, cond_off, msg_off, nxt, ncond, set_, unset, pick, leave, clear) in opt_hdrs:
        hdr += lo.to_bytes(2, "little")
        hdr += cond_off.to_bytes(2, "little")
        hdr += msg_off.to_bytes(2, "little")
        hdr += bytes((nxt, ncond, set_, unset, pick, leave, clear))
    hdr.append(len(words))
    hdr += words_off.to_bytes(2, "little")
    assert len(hdr) == HDR_SIZE, len(hdr)
    return bytes(hdr) + bytes(strings) + bytes(cond_bytes)


def _parse_item_opt(raw, flag_map, idmap, system="zx128"):
    """Parse an item option into the blob's fields.

    Syntax ``<label> -> <target> [if f]... [unless f]... [inscene s] [set f]
    [unset f] [pick i] [leave i] [clear] [msg text]``. The target is ``-``
    (return to the current scene) or a scene id (navigate there after applying
    the effects). ``msg`` consumes the rest of the line and is shown in a
    popup before the effects and navigation run. Returns the tuple stored in
    the item's ``ItemOptHdr``: (label bytes, inscene id, target scene id,
    conditions, set, unset, pick, leave, clear, message bytes), where
    conditions is a list of (flag id, negated) pairs, or ``None`` when a
    build-time system condition excludes the option for ``system``.
    """
    core, msg = scenefile.split_option_msg(raw)
    m = re.match(r"(.+?)\s*->\s*(\S+)(.*)$", core)
    assert m, (raw,)
    label, target, rest = m.groups()
    if target == "-":
        target_scene = SCENE_NONE
    elif target in idmap:
        target_scene = idmap[target]
    else:
        sys.exit(f"item option target {target!r} is not a scene: {raw!r}")
    if re.search(r"\bifgroup\b", rest):
        sys.exit(f"item option: ifgroup was removed; use repeated `if` tokens: "
                 f"{raw!r}")
    conds = []
    for kind, name in scenefile.option_conditions(rest):
        holds = scenefile.system_condition_holds(kind, name, system)
        if holds is False:
            return None
        if holds is True:
            continue
        if len(conds) >= scenefile.MAX_CONDITIONS:
            sys.exit(f"item option has more than {scenefile.MAX_CONDITIONS} "
                     f"conditions: {raw!r}")
        if name not in flag_map:
            sys.exit(f"item option condition {name!r} is not a flag or item: "
                     f"{raw!r}")
        conds.append((flag_map[name], 1 if kind == "unless" else 0))
    inscene = re.search(r"\binscene\s+(\S+)", rest)
    scene_id = SCENE_NONE
    if inscene is not None:
        sid = inscene.group(1)
        if sid not in idmap:
            sys.exit(f"item option inscene {sid!r} is not a scene")
        scene_id = idmap[sid]

    def fid(x):
        if not x:
            return FLAG_NONE
        if x not in flag_map:
            sys.exit(f"item option: unknown flag/item {x!r}: {raw!r}")
        return flag_map[x]

    set_ = re.search(r"\bset\s+(\S+)", rest)
    unset = re.search(r"\bunset\s+(\S+)", rest)
    leave = re.search(r"\bleave\s+(\S+)", rest)
    pick = re.search(r"\bpick\s+(\S+)", rest)
    clear = re.search(r"\bclear\b", rest)
    return (esc_bytes(label), scene_id, target_scene, conds,
            fid(set_.group(1) if set_ else None),
            fid(unset.group(1) if unset else None),
            fid(pick.group(1) if pick else None),
            fid(leave.group(1) if leave else None),
            1 if clear else 0, esc_bytes(msg) if msg else b"")


def build_inv_blob(item_list, flag_map, item_meta, ui, carry, idmap,
                   system="zx128"):
    """Paged blob backing the inventory screen, or ``None`` when it never shows.

    The engine compiles the inventory screen only when ``carry:`` caps the pack,
    an item has a description, or an item has options, so the blob is emitted only
    then. Layout (decoded by the shared core into _art_ws on the inventory
    screen)::

        u16 ui_off[2]             offset to the drop/back strings
        u16 item_desc_off[N_ITEMS] offset to each item's first description line
        u8  item_nlines[N_ITEMS]   number of stored description lines (0 = none)
        [only when an item has options:]
        u16 item_opt_off[N_ITEMS]  offset to each item's first ItemOptHdr
        u8  item_nopt[N_ITEMS]     number of options (0 = none)
        strings                    UI strings, item lines, option labels,
                                   then option messages
        ItemOptHdr[]               option headers (label_off,cond_off,msg_off,
                                   scene,target,ncond,set,unset,pick,leave,
                                   clear), 14 bytes; scene is the `inscene`
                                   gate and msg_off is 0 when there is no popup
        condition pairs             (flag id, negated) for every item option

    Each stored description line is ``[ncond][(flag id, negated) * ncond]text\\0``
    (ncond=0 for a plain line); every condition must hold. The UI strings are
    always present (the engine reads them instead of hardcoded literals). Ids
    are item-name order (assign_flags), so the engine indexes ``id - ITEM_BASE``.
    Descriptions are capped at 4 logical lines (wrapped on screen);
    options at 6.
    """
    n = len(item_list)
    by_id = {flag_map[name]: name for name in item_list}
    desc_lines = []                    # per id: list of stored-line bytes
    opts_per_id = []                   # per id: list of parsed option tuples
    any_desc = False
    any_opts = False
    for i in range(n):
        name = by_id.get(ITEM_BASE + i)
        meta = (item_meta.get(name) or {}) if name else {}
        raw = [str(x).strip() for x in (meta.get("desc") or [])]
        raw = [x for x in raw if x]

        def desc_fid(cond_name):
            if cond_name not in flag_map:
                sys.exit(f"item {name!r}: description condition "
                         f"{cond_name!r} is not a flag")
            return flag_map[cond_name]

        lines = []
        for line in raw:
            rendered, conds = scenefile.split_text_line(line)
            conds = scenefile.filter_system_conditions(conds, system)
            if conds is None:
                continue
            control = text_cond_header(
                conds, desc_fid, f"item {name!r}: description line")
            lines.append(control + esc_bytes(rendered))
        if len(lines) > 4:
            sys.exit(f"item {name!r}: description has {len(lines)} lines "
                     f"after system_* folding for {system} (max 4)")
        if lines:
            any_desc = True
        desc_lines.append(lines)
        opts = [_parse_item_opt(o, flag_map, idmap, system)
                for o in (meta.get("opts") or [])]
        opts = [o for o in opts if o is not None]
        if len(opts) > 6:
            sys.exit(f"item {name!r}: {len(opts)} options (max 6)")
        if opts:
            any_opts = True
        opts_per_id.append(opts)
    if not any_desc and carry <= 0 and not any_opts:
        return None, False, False
    head = 4 + 3 * n + (3 * n if any_opts else 0)
    strings = bytearray()
    ui_offs = []
    for key in ("drop", "back"):
        ui_offs.append(head + len(strings))
        strings += esc_bytes(ui[key])
    desc_offs = []
    for lines in desc_lines:
        desc_offs.append(head + len(strings) if lines else 0)
        for line in lines:
            strings += line
    label_offs = []
    msg_offs = []
    for opts in opts_per_id:
        loffs, moffs = [], []
        for opt in opts:
            loffs.append(head + len(strings))
            strings += opt[0]
            msg = opt[9]
            if msg:
                moffs.append(head + len(strings))
                strings += msg
            else:
                moffs.append(0)
        label_offs.append(loffs)
        msg_offs.append(moffs)
    header_off = head + len(strings)
    total_opts = sum(len(opts) for opts in opts_per_id)
    cond_base = header_off + 14 * total_opts
    opt_offs = []
    opt_hdrs = bytearray()
    cond_bytes = bytearray()
    for i, opts in enumerate(opts_per_id):
        if not opts:
            opt_offs.append(0)
            continue
        opt_offs.append(header_off + len(opt_hdrs))
        for k, opt in enumerate(opts):
            (label, scene_id, target_scene, conds, set_id, unset_id, pick_id,
             leave_id, clear, _msg) = opt
            cond_off = cond_base + len(cond_bytes) if conds else 0
            for cid, neg in conds:
                cond_bytes += bytes((cid, neg))
            opt_hdrs += label_offs[i][k].to_bytes(2, "little")
            opt_hdrs += cond_off.to_bytes(2, "little")
            opt_hdrs += msg_offs[i][k].to_bytes(2, "little")
            opt_hdrs += bytes((scene_id, target_scene, len(conds), set_id,
                               unset_id, pick_id, leave_id, clear))
    blob = bytearray()
    for off in ui_offs:
        blob += off.to_bytes(2, "little")
    for off in desc_offs:
        blob += off.to_bytes(2, "little")
    blob += bytes(len(lines) for lines in desc_lines)
    if any_opts:
        for off in opt_offs:
            blob += off.to_bytes(2, "little")
        blob += bytes(len(opts) for opts in opts_per_id)
    blob += strings
    blob += opt_hdrs
    blob += cond_bytes
    return bytes(blob), any_desc, any_opts


def load_art_blob(a, art_root, conv=None, rows=None, legacy_dir=None,
                  fill=(0, 0, 0)):
    """Convert an art's source PNG to a blob, or None if absent.

    The image is the art's ``image:`` candidate under ``art_root``/``<id>/``
    (``art_root`` is the game's ``assets/art``); absent (or an unmigrated game)
    uses the newest PNG in the folder, falling back to a flat legacy file under
    ``legacy_dir`` (``assets/gen``). ``conv`` is the art's resolved conversion
    settings (scenefile.conversion_options): the per-art ``crop`` rectangle
    selects the part of the source that maps to the art band (None = centred
    band-aspect window), the system's dither scheme assigns pixels, and match /
    palette / colour adjustments are applied before quantisation. ``rows`` is the band
    height in 16px tile rows (from the ZX `art_rows` option).

    The 128K build returns a NIRVANA+ (map+tiles) blob. The flat 48K build has
    no NIRVANA+ engine, so it returns a packed 1bpp monochrome band instead.
    """
    conv = conv or {}
    path = scenefile.resolve_art_image(art_root, a, legacy_dir)
    if path and os.path.exists(path):
        from PIL import Image
        import zxart
        im = Image.open(path).convert("RGB")
        if scene_flat():
            # The crop box follows the primary ZX band; re-fit it to this
            # target's aspect so the 48K picture is never squeezed vertically.
            flat_conv = conv
            if conv.get("crop"):
                im = zxart.crop_for_band(im, conv["crop"], rows)
                flat_conv = dict(conv)
                flat_conv["crop"] = None
            return zxart.mono_band(
                im, crop=flat_conv.get("crop"),
                dither=flat_conv.get("dither", "off"),
                rows=rows, adjust=flat_conv.get("adjust"),
                palette=flat_conv.get("palette", "none"),
                palette_colors=flat_conv.get("palette_colors"),
                margin=flat_conv.get("margin", 0), fill=fill), path
        if conv.get("mono"):
            mono = zxart.mono_image(
                im, crop=conv.get("crop"),
                dither=conv.get("dither", "off"), rows=rows,
                adjust=conv.get("adjust"),
                palette=conv.get("palette", "none"),
                palette_colors=conv.get("palette_colors"),
                margin=conv.get("margin", 0), fill=fill)
            grid = zxart.nirvana_band(mono, rows=rows, dither="off",
                                      match="rgb", palette="none")
        else:
            grid = zxart.nirvana_band(
                im, crop=conv.get("crop"), dither=conv.get("dither", "off"),
                rows=rows, match=conv.get("match", "rgb"),
                adjust=conv.get("adjust"),
                palette=conv.get("palette", "none"),
                palette_colors=conv.get("palette_colors"),
                margin=conv.get("margin", 0), fill=fill)
        return zxart.band_to_art(grid, rows=rows)[2], path
    return None, None


def load_song_blob(song_id, music_dir):
    """Read assets/music/<id>.pt3, or exit if missing / too large.

    A song is ZX0-compressed into its bank and decompressed straight into the
    target's resident player workspace at runtime; its *decompressed* size must
    fit that buffer or the engine would be overwritten.
    """
    path = os.path.join(music_dir, f"{song_id}.pt3")
    if not os.path.exists(path):
        sys.exit(f"song {song_id!r}: no such module {os.path.relpath(path, ROOT)}; "
                 "add assets/music/%s.pt3" % song_id)
    blob = open(path, "rb").read()
    if len(blob) > SONG_WS:
        sys.exit(f"song {song_id!r}: {len(blob)}B exceeds the resident "
                 f"{SONG_WS}B player buffer; shorten the module")
    return blob


def song_setup(doc):
    """Return ``(songs, songmap)`` and validate every ``music:`` reference.

    Shared by the ZX generator and the portable targets so both resolve and
    reject the same song ids; ``songmap`` maps a declared id to its index.
    """
    songs = doc["game"].get("songs", [])
    assert len(songs) <= MAX_DIR_SONGS, f"too many songs ({len(songs)})"
    songmap = {s: i for i, s in enumerate(songs)}
    for b in doc.get("scenes") or []:
        tok = b.get("music")
        if tok and str(tok).strip().lower() not in ("on", "off") \
                and str(tok).strip() not in songmap:
            sys.exit(f"scene {b['id']}: music {tok!r} is not a declared song "
                     f"(# Game songs: {', '.join(songs) or 'none'})")
    game_music = doc["game"].get("music")
    if game_music and str(game_music).strip().lower() not in ("on", "off") \
            and str(game_music).strip() not in songmap:
        sys.exit(f"# Game music {game_music!r} is not a declared song")
    return songs, songmap


def load_song_blobs(songs, music_dir):
    """Load every declared song module (decompressed size checked per song)."""
    return [load_song_blob(s, music_dir) for s in songs]


def max_song_size(song_blobs):
    """Largest decompressed module this game ships (0 without songs)."""
    return max((len(b) for b in song_blobs), default=0)


def scene_song_array(scenes, doc, songmap):
    """Resolve each scene's ``music:`` into a song index (SONG_NONE=255)."""
    def song_for(b):
        name = scenefile.resolve_song(b, doc["game"])
        return songmap[name] if name is not None else SONG_NONE
    return [song_for(b) for b in scenes]


def _zx0_tool():
    """Locate the z88dk-zx0 host compressor, or ``None`` when it is missing.

    Prefers the checkout's ``$Z88DK/bin`` (the build sets it) and falls back to
    ``PATH`` (which honours ``PATHEXT`` on Windows, so ``.exe`` is found). When
    ``Z88DK`` points at the toolchain root, its ``bin`` directory is checked;
    the directory holding the ``zcc`` on PATH is checked as a last resort for
    installs that keep the host tools together.  A missing tool is not fatal:
    ``zx0_compress`` then uses the built-in encoder, so a C64/NES/Oric-only build
    does not need z88dk at all.
    """
    from shutil import which
    z88dk = os.environ.get("Z88DK") or z88dkpath.default_root()
    names = (["z88dk-zx0.exe", "z88dk-zx0"] if os.name == "nt"
             else ["z88dk-zx0"])
    for base in (os.path.join(z88dk, "bin"), z88dk):
        for name in names:
            cand = os.path.join(base, name)
            if os.path.exists(cand):
                return cand
    found = which("z88dk-zx0")
    if found:
        return found
    zcc = which("zcc")
    if zcc:
        for name in names:
            cand = os.path.join(os.path.dirname(zcc), name)
            if os.path.exists(cand):
                return cand
    return None


def zx0_decompress(data):
    """Decode a standard ZX0 stream (the format ``z88dk-zx0`` emits).

    Mirrors the vendored Z80 decoder byte-for-byte. Used only to round-trip
    every blob at build time: a compressor that silently emits corrupt data
    would otherwise produce a TAP that loads but crashes before the first
    scene, which is very hard to diagnose.
    """
    data = bytes(data)
    ip = 0
    bit_mask = 0
    bit_value = 0
    backtrack = False
    last_byte = 0
    out = bytearray()
    last_offset = 1

    def read_byte():
        nonlocal ip, last_byte
        if ip >= len(data):
            raise ValueError("truncated input")
        last_byte = data[ip]
        ip += 1
        return last_byte

    def read_bit():
        nonlocal backtrack, bit_mask, bit_value
        if backtrack:
            backtrack = False
            return last_byte & 1
        bit_mask >>= 1
        if bit_mask == 0:
            bit_mask = 128
            bit_value = read_byte()
        return 1 if bit_value & bit_mask else 0

    def elias():
        value = 1
        while not read_bit():
            value = (value << 1) | read_bit()
        return value

    def copy(offset, length):
        if offset > len(out):
            raise ValueError("back-reference before output start")
        while length:
            out.append(out[-offset])
            length -= 1

    state = "literals"
    while True:
        if state == "literals":
            for _ in range(elias()):
                out.append(read_byte())
            state = "new" if read_bit() else "last"
        elif state == "last":
            copy(last_offset, elias())
            state = "new" if read_bit() else "literals"
        else:
            last_offset = elias()
            if last_offset == 256:
                if ip != len(data):
                    raise ValueError("trailing bytes after end marker")
                return bytes(out)
            last_offset = ((last_offset - 1) << 7) + 128 - (read_byte() >> 1)
            backtrack = True
            copy(last_offset, elias() + 1)
            state = "new" if read_bit() else "literals"


class _ZX0Writer:
    """Bit/byte writer for the standard (non-backwards) ZX0 format."""

    def __init__(self):
        self.out = bytearray()
        self.bit_mask = 0
        self.bit_index = 0
        self.backtrack = False

    def byte(self, value):
        self.out.append(value & 0xFF)

    def bit(self, value):
        if self.backtrack:
            if value:
                self.out[-1] |= 1
            self.backtrack = False
            return
        if not self.bit_mask:
            self.bit_mask = 0x80
            self.bit_index = len(self.out)
            self.out.append(0)
        if value:
            self.out[self.bit_index] |= self.bit_mask
        self.bit_mask >>= 1

    def elias(self, value):
        i = 2
        while i <= value:
            i <<= 1
        i >>= 1
        while True:
            i >>= 1
            if i <= 0:
                break
            self.bit(0)
            self.bit(1 if value & i else 0)
        self.bit(1)


def _elias_bits(value):
    bits = 1
    while value > 1:
        bits += 2
        value >>= 1
    return bits


def zx0_compress_py(data):
    """Greedy ZX0 encoder used when the host compressor is unusable.

    It is deliberately simple (longest recent match, one-byte lazy matching)
    and usually a few percent larger than ``z88dk-zx0 -q``. The output is a
    valid standard ZX0 stream, so the vendored runtime decoder can read it.
    """
    from collections import defaultdict

    data = bytes(data)
    n = len(data)
    if not n:
        raise ValueError("empty input")
    out = _ZX0Writer()
    pos = 0
    pending = bytearray()
    last_offset = 1
    first_block = True
    after_match = False
    chains = defaultdict(list)
    max_offset = 32640

    def add_positions(start, end):
        for p in range(start, min(end, n - 1)):
            key = data[p:p + 2]
            chain = chains[key]
            chain.append(p)
            if len(chain) > 96:
                del chain[:-96]

    add_positions(0, 0)

    def find(index):
        if index >= n:
            return 0, 0, 0
        best = (0, 0, 0)             # bits saved, offset, length
        if not after_match:
            off = last_offset
            if 0 < off <= index:
                length = 0
                while (index + length < n
                       and data[index + length] == data[index + length - off]):
                    length += 1
                if length >= 2:
                    saved = 8 * length - (1 + _elias_bits(length))
                    if saved > best[0]:
                        best = (saved, off, length)
        key = data[index:index + 2]
        for p in reversed(chains.get(key, ())):
            off = index - p
            if off <= 0 or off > max_offset:
                continue
            length = 0
            while (index + length < n
                   and data[p + length] == data[index + length]):
                length += 1
            if length >= 3:
                cost = (1 + _elias_bits((off - 1) // 128 + 1) + 8
                        + _elias_bits(length - 1))
                saved = 8 * length - cost
                if saved > best[0] or (saved == best[0] and length > best[2]):
                    best = (saved, off, length)
        return best

    def flush_literals():
        nonlocal pending, first_block, after_match
        if not pending:
            return
        if not first_block:
            out.bit(0)              # after a match: switch to literals
        out.elias(len(pending))
        for value in pending:
            out.byte(value)
        pending.clear()
        first_block = False
        after_match = False

    while pos < n:
        saved, off, length = find(pos)
        if first_block and not pending and saved > 0:
            pending.append(data[pos])
            add_positions(pos, pos + 1)
            pos += 1
            continue
        if saved > 0 and pos + 1 < n:
            saved2, _off2, length2 = find(pos + 1)
            if length2 > length + 1 and saved2 > saved:
                pending.append(data[pos])
                add_positions(pos, pos + 1)
                pos += 1
                continue
        if saved > 0:
            flush_literals()
            if off == last_offset and not after_match:
                out.bit(0)          # copy from last offset
                out.elias(length)
            else:
                out.bit(1)          # copy from a new offset
                out.elias((off - 1) // 128 + 1)
                out.byte((255 - ((off - 1) % 128)) << 1)
                out.backtrack = True
                out.elias(length - 1)
                last_offset = off
            add_positions(pos, pos + length)
            pos += length
            after_match = True
        else:
            pending.append(data[pos])
            add_positions(pos, pos + 1)
            pos += 1
    flush_literals()
    out.bit(1)
    out.elias(256)
    return bytes(out.out)


def _zx0_roundtrip(compressed, blob):
    try:
        return zx0_decompress(compressed) == blob
    except ValueError:
        return False


_ZX0_QUICK_WARNED = False
_ZX0_BUILTIN_WARNED = False


def zx0_compress(blob, tmpdir=None):
    """Compress one blob with ZX0; returns the compressed bytes.

    The compressor is a host tool; the decoder is vendored (vendor/zx0). The
    packed on-disk form adds a u16 length prefix (see ``pack_blob``) because the
    runtime copies a fixed count into the staging buffer before decoding.

    Some z88dk builds ship a broken ``z88dk-zx0`` (the Snap one has been seen
    to emit invalid streams). Every result is round-tripped; a bad quick-mode
    result falls back to optimal mode, then to the built-in greedy encoder, so
    the build still produces a TAP that can boot instead of silently shipping
    corrupt scene data.
    """
    global _ZX0_QUICK_WARNED, _ZX0_BUILTIN_WARNED
    tool = _zx0_tool()
    if tool is None:
        if not _ZX0_BUILTIN_WARNED:
            sys.stderr.write(
                "WARNING: z88dk-zx0 not found; using the built-in ZX0 "
                "compressor\n")
            _ZX0_BUILTIN_WARNED = True
        return zx0_compress_py(blob)
    for options in (["-f", "-q"], ["-f"]):
        try:
            with tempfile.TemporaryDirectory(dir=tmpdir) as td:
                src = os.path.join(td, "blob")
                dst = src + ".zx0"
                with open(src, "wb") as f:
                    f.write(blob)
                subprocess.run([tool, *options, src, dst], check=True,
                               capture_output=True, timeout=120)
                compressed = open(dst, "rb").read()
        except (OSError, subprocess.SubprocessError):
            continue
        if _zx0_roundtrip(compressed, blob):
            return compressed
        if not _ZX0_QUICK_WARNED:
            sys.stderr.write(
                "WARNING: z88dk-zx0 quick mode produced an invalid stream; "
                "trying optimal mode\n")
            _ZX0_QUICK_WARNED = True
    if not _ZX0_BUILTIN_WARNED:
        sys.stderr.write(
            "WARNING: z88dk-zx0 output failed ZX0 validation; using the "
            "built-in compressor (possibly larger output)\n")
        _ZX0_BUILTIN_WARNED = True
    compressed = zx0_compress_py(blob)
    if not _zx0_roundtrip(compressed, blob):
        sys.exit("the built-in ZX0 compressor produced invalid data")
    return compressed


def pack_blob(compressed):
    """Prefix a compressed blob with its u16 little-endian length.

    The runtime reads the length to know how many bytes to copy into _stage_ws,
    then decodes from there. ``off`` in the directory points at the prefix.
    """
    return len(compressed).to_bytes(2, "little") + compressed


def _arr(h, name, typ, vals, fmt):
    h.append(f"const {typ} {name}[{len(vals)}] = {{")
    for i in range(0, len(vals), 16):
        h.append("    " + ",".join(fmt % v for v in vals[i:i + 16]) + ",")
    h.append("};")


def _exact_dir_arrays(h, name, directory):
    """Emit bank/off arrays sized exactly to ``directory``.

    The engine indexes songs with the compile-time ``N_SONGS`` (unlike art and
    scenes, which the generator may grow past a fixed engine stride), so no
    padding is needed. Lengths live in the blob itself (a u16 prefix), so no
    length array is emitted.
    """
    if not directory:
        h.append(f"const unsigned char {name}_bank[1] = {{ 0 }};")
        h.append(f"const unsigned short {name}_off[1] = {{ 0 }};")
        return
    _arr(h, f"{name}_bank", "unsigned char", [d[0] for d in directory],
         "0x%02X")
    _arr(h, f"{name}_off", "unsigned short", [d[1] for d in directory], "%d")


def write_scene_data(header, out_h):
    """Write ``scene_data.h`` (declarations) and its ``scene_data.c`` definitions.

    Splitting the generated arrays out of the header lets several C modules
    include the header without each emitting a duplicate definition.
    """
    import re as _re
    decls = []
    defs = ['/* scene_data.c - generated by tools/gen_scenes.py - do not edit */',
            '#include "scene_data.h"', ""]
    i = 0
    while i < len(header):
        line = header[i]
        m = _re.match(r"^const\s+(.+?)\s+(\w+)\[([^\]]*)\]\s*=\s*\{", line)
        if not m:
            decls.append(line)
            i += 1
            continue
        block = [line]
        while not block[-1].rstrip().endswith("};"):
            i += 1
            block.append(header[i])
        i += 1
        typ, name, size = m.group(1), m.group(2), m.group(3)
        decls.append(f"extern const {typ} {name}[{size}];")
        defs.extend(block)
        defs.append("")
    open(out_h, "w", encoding="utf-8").write("\n".join(decls) + "\n")
    out_c = os.path.splitext(out_h)[0] + ".c"
    open(out_c, "w", encoding="utf-8").write("\n".join(defs) + "\n")


def target_art_lines(doc):
    """The active ZX target's art-band height in character rows (even 8..16).

    The 48K keeps its own `## zx48 art_rows`; the 128K reads its `art_rows`
    (stored as the legacy shared `# Game art_lines`), so each build uses its
    own band rather than whichever system block was parsed last.
    """
    try:
        import targets
        target = targets.get_target(scene_target_id())
        if target is not None:
            rows = targets.target_options(doc, target).get("art_rows")
            if rows is not None and str(rows).strip() != "":
                return scenefile.art_lines({"art_lines": int(rows)})
    except Exception:               # noqa: BLE001 - optional build registry
        pass
    return scenefile.art_lines(doc.get("game") or {})


def zx_mono(doc):
    """Whether the active ZX target's Black and white option is enabled."""
    try:
        import targets
        target = targets.get_target(scene_target_id())
        if target is not None:
            return bool(targets.target_options(doc, target).get("mono"))
    except Exception:               # noqa: BLE001 - optional build registry
        pass
    return False


def zx_popup_menu(doc):
    """Whether the active ZX system enables its optional pop-up dialog."""
    try:
        import targets
        target = targets.get_target(scene_target_id())
        if target is not None:
            return bool(targets.target_options(doc, target).get("menu"))
    except Exception:               # noqa: BLE001 - optional build registry
        pass
    return False


def zx_title_colours(doc):
    """Resolve the ZX `title_ink` option to an ``(ink, bright)`` pair.

    The default (``text``) inherits the resolved body-text colour, so existing
    games keep the title matching the text. Any of the shared colour tokens
    selects an exact Spectrum ink.
    """
    game = doc.get("game") or {}
    text = scenefile.text_colours(game)["text"]
    try:
        import targets
        target = targets.get_target(scene_target_id())
        token = (targets.target_options(doc, target).get("title_ink")
                 if target is not None else None)
    except Exception:               # noqa: BLE001 - optional build registry
        token = None
    if not token or token == scenefile.TITLE_INK_INHERIT:
        return text
    return scenefile.WORD_INKS.get(str(token).strip().lower(), text)


def write_port_data_h(path, title_ink, title_bright, have_inv_blob=False,
                      overlay_menu=False):
    """Write the shared-core view of scene_data.h.

    The portable engine reads its data through port_data.h.  On the Spectrum
    the bytes stay in scene_data.c, so this header aliases those symbols and
    supplies the layout/feature flags that keep the ZX behaviour (NIRVANA+ art,
    wrapping text, pinned options with the row-23 inventory band or the optional
    pop-up dialog, whose overflowing text scrolls).  No storage is duplicated.
    """
    lines = [
        "/* port_data.h - generated by tools/gen_scenes.py - do not edit */",
        "#ifndef ZX_PORT_DATA_H",
        "#define ZX_PORT_DATA_H",
        '#include "scene_data.h"',
        "",
        "#define PORT_COLS 64",
        "#define PLAT_ROWS 24",
        f"#define TITLE_INK {title_ink}",
        f"#define TITLE_BRIGHT {title_bright}",
        "#define PORT_TEXT_TOP (1 + ART_LINES)",
        "#define PORT_TEXT_WIDTH 62",
        "#define PORT_DESC_WIDTH 62",
        "#define PORT_OPT_WIDTH 62",
        "#define PORT_OPT_INDENT 1",
        "#define PORT_KEEP_ART 1",
        "#define PORT_SIMPLE_OPTIONS 1",
        f"#define PORT_NO_TEXT_SCROLL {0 if overlay_menu else 1}",
        f"#define PORT_NO_DESC_SCROLL {0 if overlay_menu else 1}",
        "#define PORT_NO_WRAP 0",
        f"#define PORT_NO_ENTRY_WRAP {0 if overlay_menu else 1}",
        "/* Keep the marker clear of the last cell: printing there makes the ZX",
        "   ROM scroll the whole screen and shift the NIRVANA+ band. */",
        "#define PORT_SCROLL_COL 61",
        "#define PORT_MARKER_MATCH_CELL 1",
        "#define PORT_INV_MARK_R 62",
        "#define PORT_INV_CONTENT_COLS 60",
        "#define PORT_TEXT_MACRO 1",
        "#if !NEED_PASSWORD",
        "#define PORT_BOOT_MACRO 1",
        "#endif",
        f"#define PORT_OVERLAY_MENU {1 if overlay_menu else 0}",
        "#define PORT_ART_CLEARS_TEXT 0",
        "#if PORT_OVERLAY_MENU",
        "#define PORT_ITEM_BOTTOM PLAT_ROWS",
        "#else",
        "#define PORT_ITEM_BOTTOM (PLAT_ROWS - 1)",
        "#endif",
        "#define PORT_EXTERN_WS 1",
        "#define PORT_INV_OVERWRITES_ART 1",
        "#define PORT_BANKED_SCENES 1",
        "#define PORT_SCENE_WS SCENE_WS_SIZE",
        "#define PORT_INV_WS ART_WS_SIZE",
        "#define PORT_SCROLL_UP \"^\"",
        "#define PORT_SCROLL_DOWN \"v\"",
        "",
        "typedef SceneHdr PortSceneHdr;",
        "typedef OptHdr PortOptHdr;",
        "typedef WordHdr PortWordHdr;",
        "typedef ItemOptHdr PortItemOptHdr;",
        "",
        "extern unsigned char art_ws[];",
        "#define inv_ws art_ws",
        "#define port_scene_bank scene_bank",
        "#define port_scene_off scene_off",
        "#define port_item_names item_names",
        "#define port_item_name_off item_name_off",
        "#define port_start_flags start_flags",
        "#define port_game_popup_hint game_popup_hint",
    ]
    if have_inv_blob:
        lines += [
            "#define port_inv_bank inv_blob_bank[0]",
            "#define port_inv_off inv_blob_off[0]",
        ]
    lines += ["", "#endif", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    # First argument may be a game slug ("the-arousa-job"), a game directory
    # ("games/the-arousa-job") or a game.md path. The optional second
    # argument overrides the output header path (used by tests).
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg and os.path.isfile(arg):
        md = arg
        gdir = os.path.dirname(os.path.abspath(arg))
    elif arg and gamestore.is_game_dir(arg):
        gdir = os.path.abspath(arg)
        md = os.path.join(gdir, "game.md")
    else:
        slug = os.path.basename(os.path.normpath(arg)) if arg else None
        g = gamestore.resolve(slug)
        if g is None:
            sys.exit(f"no such game: {arg!r} (see 'games/')")
        md = os.path.join(g["dir"], "game.md")
        gdir = g["dir"]
    out_h = (sys.argv[2] if len(sys.argv) > 2
             else os.path.join(gdir, gamestore.BUILD_NAME, "scene_data.h"))
    bdir = os.path.join(gdir, gamestore.BUILD_NAME)
    os.makedirs(bdir, exist_ok=True)
    max_bank = int(os.environ.get("SCENE_MAX_BANK", BANK_SIZE))
    gen_dir = os.path.join(gdir, "assets", "gen")
    art_root = os.path.join(gdir, scenefile.ART_ROOT)
    banks_dir = os.path.join(bdir, "scene_banks")
    asm_dir = bdir
    try:
        rel_banks = os.path.relpath(banks_dir, ROOT)
    except ValueError:          # different drive (Windows): use an absolute path
        rel_banks = banks_dir
    rel_banks = rel_banks.replace("\\", "/")
    os.makedirs(banks_dir, exist_ok=True)

    doc = parse(md)
    target_id = scene_target_id()
    flat = scene_flat()
    scenes, arts = doc["scenes"], doc["arts"]
    item_meta = doc.get("item_meta") or {}
    have_messages = any(scenefile.split_option_msg(o)[1]
                        for b in scenes for o in b.get("opts") or [])
    have_messages = have_messages or any(
        scenefile.split_option_msg(o)[1]
        for meta in item_meta.values() for o in meta.get("opts") or [])

    # The accent patch is only needed for the glyphs z88dk's built-in CRT font
    # (already in the image) lacks. An all-ASCII game skips it; a game with any
    # accented letter patches just those slots at startup.
    try:
        accent_src = open(md, encoding="utf-8").read()
    except OSError:
        accent_src = ""
    accent_slots = sorted(ACCENT_BYTES[c] for c in ACCENT_BYTES
                          if c in accent_src)
    accent_used = bool(accent_slots)
    # Selectable words compile the engine's word cursor (src/zx/); a
    # game without any pays nothing (HAVE_WORDS = 0).
    any_words = any(scenefile.parse_words(
                        scenefile.split_text_line(raw)[0])[1]
                    for s in scenes for raw in s.get("text", []))
    assert scenes, "no scenes found"
    assert len(scenes) <= MAX_DIR_SCENES, f"too many scenes ({len(scenes)})"
    assert len(arts) <= MAX_DIR_ARTS, f"too many arts ({len(arts)})"

    idmap = {b["id"]: i for i, b in enumerate(scenes)}
    artmap = {a["id"]: i for i, a in enumerate(arts)}
    start = doc["game"].get("start", [])
    declared_flags = doc["game"].get("flags", [])
    declared_items = scenefile.declared_items(doc["game"], item_meta)
    songs, songmap = song_setup(doc)
    if flat and songs:
        sys.stderr.write(
            "WARNING: 48K has no AY sound chip; songs are ignored by this "
            "build (" + ", ".join(songs) + ")\n")
        songs, songmap = [], {}
    # Each item's display name (the `name:` of its `# Items` entry, else the
    # id). It is what the inventory band and item screen show; the id stays the
    # token in `pick`/`leave`/`if`. Validated here because the engine prints it
    # straight into the 64-column text band.
    item_names = scenefile.item_display_names(doc["game"], item_meta)
    for iid, disp in item_names.items():
        if not scenefile.text_printable(disp):
            sys.exit(f"item {iid!r}: display name {disp!r} has characters the "
                     "Spectrum font cannot print")
        if len(disp) > ITEM_NAME_COLS:
            sys.exit(f"item {iid!r}: display name is {len(disp)} columns "
                     f"(max {ITEM_NAME_COLS})")
    try:
        flag_map, item_list, flag_order = assign_flags(
            scenes, start, declared_flags, declared_items,
            item_names=item_names, item_meta=item_meta)
    except ValueError as e:
        sys.exit(f"flag/item error: {e}")

    # Flags/items set at game start (`start:` in the # Game section). Unknown
    # names are errors: a start flag the game never sets is almost always a
    # typo, and silently ignoring it changes the story.
    start_ids = []
    for name in start:
        if name not in flag_map:
            sys.exit(f"game start: unknown flag/item {name!r}")
        start_ids.append(flag_map[name])

    for b in scenes:
        assert b["art"] in artmap, f"scene {b['id']}: unknown art {b['art']!r}"

    for a in arts:
        assert a["id"] not in ("game", ""), f"bad art id {a['id']!r}"

    # Art band height: this target's `art_rows` option (even 8..16, default 10)
    # character rows. A NIRVANA+ tile row is 16px = 2 character rows, so the
    # engine races `lines` attribute rows (1..lines) and the tile map is
    # 8*lines bytes. The 48K has its own setting, independent of the 128K.
    lines = target_art_lines(doc)
    tile_rows = lines // 2
    art_map_len = 8 * lines

    # --- load art + song blobs -------------------------------------------
    # Each art resolves its own conversion settings against the `# Game`
    # defaults (colour match, palette pre-reduction, source colour adjustments)
    # via the shared scenefile resolver, and its dither comes from this system's
    # block, so a per-art override and the editor's preview agree with the build.
    art_blobs, art_dither, missing = [], [], []
    fill = (0, 0, 0)
    if not flat:
        import zxart
        fill = zxart.background_rgb(doc["game"])
    for i, a in enumerate(arts):
        conv = scenefile.conversion_options(a, doc["game"], target_id)
        art_dither.append(conv.get("dither", "off"))
        blob, path = load_art_blob(a, art_root, conv, tile_rows, gen_dir, fill)
        if blob is None:
            missing.append(a["id"])
            blob = bytes(256 * lines) if flat else bytes(art_map_len)
        art_blobs.append(blob)

    music_dir = os.path.join(gdir, "assets", "music")
    song_blobs = [] if flat else load_song_blobs(songs, music_dir)
    # The resident player buffer only has to hold the largest module this game
    # actually ships, not the 4158-byte ceiling: sizing it per game frees the
    # slack in the crowded home bank. 0 for a game with no songs.
    song_ws_size = max_song_size(song_blobs)

    # The inventory screen (opened per item) draws every item's title,
    # description and options from one paged blob, decoded into _art_ws when it
    # opens (src/zx/); it shares that buffer with the art, so both must
    # fit ART_WS_SIZE (sized below). It exists only when that screen compiles
    # (`carry:`, some item description or some item option).
    ui_strings = scenefile.inventory_strings(doc["game"])
    inv_blob, have_item_desc, have_item_opts = build_inv_blob(
        item_list, flag_map, item_meta, ui_strings,
        int(doc["game"].get("carry", 0) or 0), idmap, target_id)

    raw_art = [len(b) for b in art_blobs]
    max_art = max(raw_art, default=0)
    scene_blobs = [build_scene_blob(b, idmap, artmap, flag_map, target_id)
                   for b in scenes]
    raw_scene = [len(b) for b in scene_blobs]
    max_scene = max(raw_scene)
    ws_size = max(max_art, max_scene)
    tile_peak = 0 if flat else max(
        ((len(b) - art_map_len) // 48) for b in art_blobs)
    art_blob_peak = max_art
    # _art_ws (src/zx/paging.asm) must hold the largest raw art blob and the
    # inventory blob (both decoded into it); sized per game so a small band does
    # not reserve the old fixed 4096, and a tall one can grow.
    art_ws_size = max(max_art, len(inv_blob) if inv_blob is not None else 0)
    # The engine decompresses each blob into the per-game home-bank workspace
    # before use (src/zx/paging.asm: _scene_ws, _art_ws). `_scene_ws` grows with
    # the largest scene blob; tools/build.py then rejects a main image that would
    # overlap the NIRVANA+ engine, so there is no fixed per-scene size cap here.
    if inv_blob is not None and len(inv_blob) > art_ws_size:
        sys.exit(f"inventory strings + item descriptions {len(inv_blob)}B "
                 f"exceed the {art_ws_size}B _art_ws workspace; shorten them")

    # --- compress every blob with ZX0 -------------------------------------
    # Each packed blob is [u16 compressed length][zx0 stream]. The runtime copies
    # the compressed bytes into _stage_ws, then decodes with interrupts enabled,
    # so packing uses the compressed sizes and songs no longer need a stored
    # decompressed length (song blobs decode into the lower-RAM workspace).
    art_comp = [zx0_compress(b, bdir) for b in art_blobs]
    scene_comp = [zx0_compress(b, bdir) for b in scene_blobs]
    song_comp = [zx0_compress(b, bdir) for b in song_blobs]
    inv_comp = (zx0_compress(inv_blob, bdir)
                if inv_blob is not None else b"")
    art_packed = [pack_blob(c) for c in art_comp]
    scene_packed = [pack_blob(c) for c in scene_comp]
    song_packed = [pack_blob(c) for c in song_comp]
    inv_packed = pack_blob(inv_comp) if inv_blob is not None else b""
    for a, raw, packed, dmode in zip(arts, raw_art, art_packed, art_dither):
        if flat:
            import zxart
            sys.stderr.write("art %s: %dB mono (%s) -> %dB compressed\n"
                             % (a["id"], raw, zxart.mono_dither(dmode),
                                len(packed) - 2))
        else:
            sys.stderr.write("art %s: %dB -> %dB compressed (%d tiles)\n"
                             % (a["id"], raw, len(packed) - 2,
                                (raw - art_map_len) // 48))
    biggest = max((max((len(c) for c in art_comp), default=0),
                   max((len(c) for c in scene_comp), default=0),
                   max((len(c) for c in song_comp), default=0),
                   len(inv_comp)))
    if flat:
        # No staging buffer: the whole flat store is resident at 0x6000 and
        # decoded straight into the main-image workspaces.
        stage_ws_size = 0
    else:
        # _stage_ws (src/zx/paging.asm @0x6000) is free lower RAM up to 0x8000;
        # every compressed blob must fit or the copy would overwrite the screen.
        if biggest > STAGE_WS_MAX:
            sys.exit(f"a compressed blob is {biggest}B, exceeding the "
                     f"{STAGE_WS_MAX}B _stage_ws staging buffer "
                     "(src/zx/paging.asm)")
        stage_ws_size = max(biggest, 64)
        # The ZX staging buffer (0x6000) and the song workspace that follows it
        # share the 8K lower-RAM window up to 0x8000.
        if stage_ws_size + song_ws_size > STAGE_WS_MAX:
            sys.exit(f"stage ({stage_ws_size}B) + song ({song_ws_size}B) "
                     f"workspaces exceed the {STAGE_WS_MAX}B lower-RAM window "
                     "at 0x6000; shorten the module or a compressed blob")

    art_dir = [None] * len(arts)
    scene_dir = [None] * len(scenes)
    song_dir = [None] * len(songs)
    inv_dir = [None]
    used = []
    flat_used = 0
    art_data = b""
    inv_data = b""

    if flat:
        # --- flat 48K store: scenes resident at 0x6000 -------------------
        # The 48K has no NIRVANA+ engine and no paging. Scene blobs stay in
        # the 7 KB lower-RAM store and decode from FLAT_DATA_ADDR + off + 2.
        # Art and inventory blobs are compiled into the main image instead:
        # monochrome art is too large for the lower window, and removing the
        # 0xDC03 engine reservation frees the high memory for it.
        parts = bytearray()

        def place(blobs, directory):
            for i, blob in enumerate(blobs):
                directory[i] = (0, len(parts))
                parts.extend(blob)

        place(scene_packed, scene_dir)
        flat_used = len(parts)
        if flat_used > FLAT_DATA_MAX:
            sys.exit(
                f"48K build does not fit: compressed scene data is "
                f"{flat_used}B but only {FLAT_DATA_MAX}B fits at "
                "0x6000-0x7BFF (the top 1 KB of lower RAM is the stack). "
                "Shorten scene text or options, remove scenes, or use the "
                "128K target.")
        with open(os.path.join(bdir, "scene_flat.bin"), "wb") as f:
            f.write(bytes(parts) + bytes(FLAT_DATA_MAX - flat_used))
        # Art and inventory live in the linked image; offsets are relative to
        # their own arrays (the banks are unused on 48K).
        art_parts = bytearray()
        for i, blob in enumerate(art_packed):
            art_dir[i] = (0, len(art_parts))
            art_parts.extend(blob)
        art_data = bytes(art_parts)
        if inv_blob is not None:
            inv_dir[0] = (0, 0)
            inv_data = inv_packed
        # Remove bank wrappers from an earlier 128K run so a flat build never
        # links stale paged data.
        for name in ["scene_banks.asm"] + [
                n for bn in BANKS for n in (
                    f"scene_bank{bn}.asm",
                    os.path.join("scene_banks", f"bank{bn}.bin"))]:
            try:
                os.remove(os.path.join(bdir, name))
            except OSError:
                pass
    else:
        # --- pack blobs into banks (nothing straddles a boundary) --------
        # Arts, scenes and songs share the same bank pool; each blob is placed
        # whole. Best-fit-decreasing: largest blobs first into the emptiest
        # bank that still fits, which keeps the banks evenly filled and
        # recovers the slack a greedy next-fit pass would strand between large
        # art blobs.
        bank_img = {n: bytearray([BANK_MAGIC]) for n in BANKS}
        work = [(art_packed[i], art_dir, i) for i in range(len(arts))] + \
               [(scene_packed[i], scene_dir, i) for i in range(len(scenes))] + \
               [(song_packed[i], song_dir, i) for i in range(len(songs))]
        if inv_blob is not None:
            work.append((inv_packed, inv_dir, 0))
        for blob, directory, idx in sorted(work, key=lambda w: len(w[0]),
                                           reverse=True):
            placed = False
            for bn in sorted(BANKS, key=lambda n: len(bank_img[n])):
                if len(bank_img[bn]) + len(blob) <= max_bank:
                    off = len(bank_img[bn])
                    bank_img[bn] += blob
                    directory[idx] = (bn, off)
                    placed = True
                    break
            if not placed:
                sys.exit("scene/art/song/item data exceeds available banks")

        # --- write bank images + asm wrappers ----------------------------
        for bn in BANKS:
            if len(bank_img[bn]) <= 1:
                continue
            used.append(bn)
            with open(os.path.join(banks_dir, f"bank{bn}.bin"), "wb") as f:
                f.write(bank_img[bn])
            with open(os.path.join(asm_dir, f"scene_bank{bn}.asm"), "w") as f:
                f.write(
                    "; generated by tools/gen_scenes.py - do not edit\n"
                    f"SECTION BANK_{bn}\n"
                    f"PUBLIC _scene_bank{bn}\n"
                    f"_scene_bank{bn}:\n"
                    f'    BINARY "{rel_banks}/bank{bn}.bin"\n')

    # --- home-bank header ------------------------------------------------
    h = ["/* scene_data.h - generated by tools/gen_scenes.py - do not edit */",
         "",
         f"#define SCENE_NONE {SCENE_NONE}",
         f"#define FLAG_NONE {FLAG_NONE}",
         f"#define FLAG_BASE {FLAG_BASE}",
         f"#define ITEM_BASE {ITEM_BASE}",
         f"#define N_FLAGS {len(flag_map)}",
         f"#define N_ITEMS {len(item_list)}",
         f"#define N_SCENES {len(scenes)}",
         f"#define N_ART {len(arts)}",
         f"#define N_SONGS {len(songs)}",
         f"#define SONG_NONE {SONG_NONE}",
         f"#define GAME_CARRY {int(doc['game'].get('carry', 0) or 0)}",
         f"#define NEED_ACCENT_FONT {1 if accent_used else 0}",
         f"#define N_ACCENT_GLYPHS {len(accent_slots)}",
         f"#define NEED_PASSWORD {1 if (doc['game'].get('password') or '').strip() else 0}",
         f"#define SONG_WS_SIZE {song_ws_size}",
         f"#define ART_LINES {lines}",
         f"#define ART_MAP_LEN {art_map_len}",
         f"#define ART_WS_SIZE {art_ws_size}",
         f"#define STAGE_WS_SIZE {stage_ws_size}",
         f"#define SCENE_HDR_SIZE {HDR_SIZE}",
         f"#define SCENE_WS_SIZE {max_scene}",
         f"#define ART_BLOB_PEAK {art_blob_peak}",
         f"#define TILE_PEAK {tile_peak}",
         f"#define N_START {len(start_ids)}",
         f"#define HAVE_ITEM_DESC {1 if have_item_desc else 0}",
         f"#define HAVE_ITEM_OPTS {1 if have_item_opts else 0}",
         f"#define HAVE_INV_BLOB {1 if inv_blob is not None else 0}",
         f"#define HAVE_WORDS {1 if any_words else 0}",
         f"#define HAVE_MESSAGES {1 if have_messages else 0}",
         ""]
    if flat:
        h += [f"#define FLAT_DATA_ADDR {FLAT_DATA_ADDR}",
              f"#define FLAT_DATA_SIZE {FLAT_DATA_MAX}",
              f"#define FLAT_DATA_USED {flat_used}",
              ""]
    h += ["typedef struct { unsigned short label_off, cond_off, msg_off; "
         "unsigned char next,ncond,set,unset,pick,leave,clear; } OptHdr;",
         "typedef struct { unsigned short label_off, cond_off, msg_off; "
         "unsigned char scene,target,ncond,set,unset,pick,leave,clear; } "
         "ItemOptHdr;",
         "typedef struct { unsigned char line,col,len,flag; } WordHdr;",
         "typedef struct {",
         "    unsigned char art, nopt, ending;",
         "    unsigned short title_off;",
         "    unsigned short text_off[8];",
         "    OptHdr opts[6];",
         "    unsigned char nwords;",
         "    unsigned short words_off;",
         "} SceneHdr;",
         ""]
    colours = scenefile.text_colours(doc["game"])
    if zx_mono(doc):
        colours = {"text": (7, 1), "highlight": (7, 1), "bg": (0, 0)}
    bg_ink, bg_bright = colours["bg"]
    if not (bg_ink & 7):
        bg_bright = 0          # black is black whether or not BRIGHT is set
    h += [f"#define TEXT_INK {colours['text'][0]}",
          f"#define TEXT_BRIGHT {colours['text'][1]}",
          f"#define HIGHLIGHT_INK {colours['highlight'][0]}",
          f"#define HIGHLIGHT_BRIGHT {colours['highlight'][1]}",
          f"#define TEXT_BG {bg_ink}",
          f"#define TEXT_BG_BRIGHT {bg_bright}",
          ""]
    if any_words:
        h += [f"#define WORD_MAX {WORD_MAX}", ""]
    # Exact-length directories: the engine only ever indexes these with an id it
    # bounds against N_ART/N_SCENES/N_SONGS, so the old zero-padding to a fixed
    # stride only wasted resident bytes in the crowded home bank.
    _exact_dir_arrays(h, "art", art_dir)
    _exact_dir_arrays(h, "scene", scene_dir)
    if songs:
        _exact_dir_arrays(h, "song", song_dir)
    if inv_blob is not None:
        _exact_dir_arrays(h, "inv_blob", inv_dir)
    if flat:
        if art_data:
            _arr(h, "art_data", "unsigned char", list(art_data), "%d")
        else:
            h.append("const unsigned char art_data[1] = { 0 };")
        if inv_data:
            _arr(h, "inv_data", "unsigned char", list(inv_data), "%d")
        else:
            h.append("const unsigned char inv_data[1] = { 0 };")

    # Per-scene song index: the scene's own `music:` override, else the
    # `# Game` default, else SONG_NONE (silence). Emitted only when the game has
    # songs (src/zx/ guards set_music/scene_song on N_SONGS > 0).
    if songs:
        _arr(h, "scene_song", "unsigned char",
             scene_song_array(scenes, doc, songmap), "%d")

    # Flags/items the game sets before the first scene (from `start:`).
    if start_ids:
        _arr(h, "start_flags", "unsigned char", start_ids, "%d")
    else:
        h.append("const unsigned char start_flags[1] = { 0 };")

    # Game title + optional boot-screen password (src/zx/). Both are
    # NUL-terminated C strings; an empty password means no boot screen is shown
    # and the game starts straight at the first scene. The prompt label is only
    # emitted when a password exists (the engine guards it on NEED_PASSWORD).
    gt = esc_bytes(doc["game"].get("title", ""))
    gp = esc_bytes(doc["game"].get("password", "") or "")
    ph = esc_bytes(scenefile.popup_hint(doc["game"]))
    _arr(h, "game_title", "char", list(gt), "%d")
    _arr(h, "game_password", "char", list(gp), "%d")
    _arr(h, "game_popup_hint", "char", list(ph), "%d")
    if (doc["game"].get("password") or "").strip():
        pl = esc_bytes(scenefile.password_label(doc["game"]))
        _arr(h, "game_password_label", "char", list(pl), "%d")

    # Inventory name table: NAMES[id - ITEM_BASE], id-ordered, NUL-separated,
    # with a u16 offset per item (the engine flows them along row 23). These are
    # the items' display names, not their ids (see item_names above).
    by_id = {flag_map[n]: n for n in item_list}
    names = []
    for i in range(len(item_list)):
        iid = by_id.get(ITEM_BASE + i)
        disp = item_names.get(iid, iid) if iid is not None else "item%d" % i
        names.append(esc_bytes(disp)[:-1])
    blob = bytearray()
    offsets = []
    for n in names:
        offsets.append(len(blob))
        blob += n + b"\x00"
    if not blob:
        blob = b"\x00"
        offsets = [0]
    h.append("")
    h.append(f"const char item_names[{len(blob)}] = {{")
    for i in range(0, len(blob), 16):
        h.append("    " + ",".join("%d" % b for b in blob[i:i + 16]) + ",")
    h.append("};")
    # Exact length: the engine indexes item_name_off[id - ITEM_BASE] only for
    # held ids < ITEM_BASE + N_ITEMS, so padding to MAX_ITEMS is wasted RAM.
    _arr(h, "item_name_off", "unsigned short", offsets, "%d")
    h.append("")

    # Patch only the blank slots of the CRT's own 4x8 font at startup. The
    # classic console indexes the font as (ch - 32) * 8 and prints one 4-pixel
    # half per 64-column cell, so each row's glyph sits in both nibbles (see
    # ACCENT_GLYPHS). Shipping a second 768-byte font table would not fit the
    # home bank on text-heavy games.
    if accent_used:
        slots, glyphs = [], []
        for ch in accent_slots:
            slots.append((ch - 32) * 8)
            for nib in ACCENT_GLYPHS[ch]:
                glyphs.append((nib << 4) | nib)
        _arr(h, "adventure_font_slots", "unsigned short", slots, "%d")
        _arr(h, "adventure_font_glyphs", "unsigned char", glyphs, "%d")
        h.append("")
    write_scene_data(h, out_h)
    if zx_mono(doc):
        title_ink, title_bright = 7, 1
    else:
        title_ink, title_bright = zx_title_colours(doc)
    write_port_data_h(os.path.join(os.path.dirname(out_h), "port_data.h"),
                      title_ink, title_bright,
                      have_inv_blob=(inv_blob is not None),
                      overlay_menu=zx_popup_menu(doc))

    # --- flag legend (for the editor) ------------------------------------
    legend = ["# generated by tools/gen_scenes.py - id legend (do not edit)"]
    for name in flag_order:
        kind = "item" if name in item_list else "flag"
        legend.append(f"{kind} {flag_map[name]}\t{name}")
    open(os.path.join(bdir, "scene_flags.txt"), "w").write(
        "\n".join(legend) + "\n")

    # --- bank manifest for the tape loader -------------------------------
    if not flat:
        a = ["; generated by tools/gen_scenes.py - do not edit",
             "SECTION code_user",
             "PUBLIC _scene_bank_list",
             "PUBLIC _scene_bank_count",
             "_scene_bank_count:",
             f"    defb {len(used)}",
             "_scene_bank_list:"]
        for bn in used:
            a.append(f"    defb {bn}")
        a.append("    defb 0xFF")
        open(os.path.join(bdir, "scene_banks.asm"), "w").write(
            "\n".join(a) + "\n")

    if missing:
        sys.stderr.write(
            f"WARNING: no PNG for art(s) {', '.join(missing)}; using blank\n")
        sys.stderr.write(
            "  generate with: python3 tools/gen_images.py  (or the editor)\n")
    raw_total = sum(raw_art) + sum(raw_scene) + sum(len(b) for b in song_blobs)
    packed_total = sum(len(b) for b in art_packed) + \
        sum(len(b) for b in scene_packed) + sum(len(b) for b in song_packed)
    if flat:
        sys.stderr.write(
            "scenes: %d scenes, %d arts, 0 songs, %d flags, %d items, "
            "art_lines=%d flat; ws=%dB art_peak=%dB scene_flat=%dB/%dB "
            "lower RAM, art=%dB inv=%dB main image\n"
            % (len(scenes), len(arts), len(flag_map), len(item_list), lines,
               ws_size, art_blob_peak, flat_used, FLAT_DATA_MAX,
               len(art_data), len(inv_data)))
    else:
        sys.stderr.write(
            "scenes: %d scenes, %d arts, %d songs, %d flags, %d items, "
            "art_lines=%d in banks %s; ws=%dB art_peak=%dB tiles=%d "
            "compressed=%dB/%dB\n"
            % (len(scenes), len(arts), len(songs), len(flag_map),
               len(item_list), lines, used, ws_size, art_blob_peak, tile_peak,
               packed_total, raw_total))


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
