"""Nintendo Entertainment System art conversion helpers.

The editor preview and the ``.nes`` build share this module.  The NES PPU
shows 32x30 background tiles; a game band is ``256 x (8 * art_rows)`` pixels
and is drawn on rows 2..art_rows+1 (row 0 is the title, row 1 is blank, and the
text pane starts at ``art_rows + 2``).  The even start/height keeps the band
aligned with the PPU's 2x2-tile attribute quadrants.

Each art's 8KB CHR bank holds two 4KB pattern tables.  Table 0 (background in
the art/title region) has the 96 normal glyphs followed by up to 160 art
tiles.  Table 1 (background in the text pane) has the same normal glyphs and a
highlight copy at 96..191.  The runtime switches background tables at the
art/text boundary each frame.

The PPU has four background palettes of four colours; entry 0 is the shared
universal background.  Palette 0 is body text with entry 2 set to the highlight
colour; palettes 1..3 are art palettes (``text_bg`` plus three colours each).
Normal glyphs use pixel value 1 and highlighted glyphs pixel value 2, so a
word can be highlighted without changing the 2x2-tile attribute.

Blob layout (one art, uncompressed in PRG ROM)::

    u16 ntiles               (little-endian)
    u8  npalettes            (always 3)
    u8  palettes[3][4]       NES colour indices; entry 0 is the universal bg
    u16 map[32 * art_rows]   tile indices 0..ntiles-1 (runtime adds 96)
    u8  attrs[64]            full nametable attribute table
"""
from __future__ import annotations

import io
import itertools
import struct

WIDTH = 256
COLS = 32
HEIGHT_ROWS = 8
FONT_TILES = 96
ART_BASE = FONT_TILES
MAX_ART_TILES = 256 - ART_BASE          # 160 (one 4KB background pattern table)
TABLE_SIZE = 0x1000
ART_PALETTES = 3
DEFAULT_ART_ROWS = 10
ART_TOP = 2

# Common NES 2C02 RGB palette (indices 0x00..0x3F).  Exact values vary between
# NTSC decoders; this widely used table is for editor previews and colour
# matching only -- the PPU stores the 6-bit indices.
NES_PALETTE = (
    (84, 84, 84), (0, 30, 116), (8, 16, 144), (48, 0, 136),
    (68, 0, 100), (92, 0, 48), (84, 4, 0), (60, 24, 0),
    (32, 42, 0), (8, 58, 0), (0, 64, 0), (0, 60, 0),
    (0, 50, 60), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (152, 150, 152), (8, 76, 196), (48, 50, 236), (92, 30, 228),
    (136, 20, 176), (160, 20, 100), (152, 34, 32), (120, 60, 0),
    (84, 90, 0), (40, 114, 0), (8, 124, 0), (0, 118, 40),
    (0, 102, 120), (0, 0, 0), (0, 0, 0), (0, 0, 0),
    (236, 238, 236), (76, 154, 236), (120, 124, 236), (176, 98, 236),
    (228, 84, 236), (236, 88, 180), (236, 106, 100), (212, 136, 32),
    (160, 170, 0), (116, 196, 0), (76, 208, 32), (56, 204, 108),
    (56, 180, 204), (60, 60, 60), (0, 0, 0), (0, 0, 0),
    (236, 238, 236), (168, 204, 236), (188, 188, 236), (212, 178, 236),
    (236, 174, 236), (236, 174, 212), (236, 180, 176), (228, 196, 144),
    (204, 210, 120), (180, 222, 120), (168, 226, 144), (152, 226, 180),
    (160, 214, 228), (160, 162, 160), (0, 0, 0), (0, 0, 0),
)

_BASE = {
    "black": 0x0F, "white": 0x30, "red": 0x16, "cyan": 0x2C,
    "magenta": 0x24, "green": 0x1A, "blue": 0x12, "yellow": 0x28,
}
_DIM = {
    "black": 0x0F, "white": 0x00, "red": 0x06, "cyan": 0x0C,
    "magenta": 0x04, "green": 0x0A, "blue": 0x02, "yellow": 0x18,
}


def text_index(token):
    t = str(token or "").strip().lower()
    if t.startswith("dim_"):
        return _DIM.get(t[4:], 0x0F)
    return _BASE.get(t, 0x30)


def text_colours(game, mono=False):
    """Resolve ``# Game`` colours to ``(ink, highlight, bg)`` NES indices."""
    if mono:
        return 0x30, 0x30, 0x0F
    import scenefile
    text, highlight, bg = scenefile.text_tokens(game)
    return text_index(text), text_index(highlight), text_index(bg)


def _reverse8(n):
    n = ((n & 0xF0) >> 4) | ((n & 0x0F) << 4)
    n = ((n & 0xCC) >> 2) | ((n & 0x33) << 2)
    n = ((n & 0xAA) >> 1) | ((n & 0x55) << 1)
    return n


def font_tiles(font8, accents=None):
    """Expand the 96 8x8 glyphs to normal and highlight 2bpp NES tiles."""
    if len(font8) != FONT_TILES * 8:
        raise ValueError(f"expected {FONT_TILES * 8} font bytes, got {len(font8)}")
    glyphs = [bytearray(font8[i * 8:(i + 1) * 8]) for i in range(FONT_TILES)]
    for code, rows in (accents or {}).items():
        index = code - 32
        if not 0 <= index < FONT_TILES or len(rows) != 8:
            raise ValueError(f"bad accent slot 0x{code:02X}")
        glyphs[index] = bytearray(rows)
    normal = bytearray()
    hilite = bytearray()
    for glyph in glyphs:
        lo = bytearray(8)
        hi = bytearray(8)
        for y, row in enumerate(glyph):
            lo[y] = _reverse8(row)
            hi[y] = 0
        normal += lo
        normal += hi
        lo = bytearray(8)
        hi = bytearray(8)
        for y, row in enumerate(glyph):
            lo[y] = 0
            hi[y] = _reverse8(row)
        hilite += lo
        hilite += hi
    return bytes(normal), bytes(hilite)


def chr_bank(normal_font, hilite_font, tiles):
    """Pack the two 4KB pattern tables of one art's 8KB CHR bank."""
    table0 = bytearray(normal_font)
    for tile in tiles:
        if len(tile) != 16:
            raise ValueError("NES tile is not 16 bytes")
        table0 += tile
    if len(table0) > TABLE_SIZE:
        raise ValueError(f"NES table 0 needs {len(table0)} bytes (max 4096)")
    table0 += bytes(TABLE_SIZE - len(table0))

    table1 = bytearray(normal_font) + bytearray(hilite_font)
    if len(table1) > TABLE_SIZE:
        raise ValueError(f"NES table 1 needs {len(table1)} bytes (max 4096)")
    table1 += bytes(TABLE_SIZE - len(table1))
    return bytes(table0 + table1)


def _fit(im, crop, art_rows):
    from PIL import Image
    import zxart
    art_rows = int(art_rows)
    height = 8 * art_rows
    w, h = im.size
    box = im.crop(zxart.band_crop_rect(crop, w, h, WIDTH / float(height)))
    target = (WIDTH, height)
    if box.size != target:
        box = box.resize(target, Image.LANCZOS)
    return box


def _palette_image():
    from PIL import Image
    img = Image.new("P", (1, 1))
    # Repeat the 64-colour table so every 0..255 index maps to a real NES
    # colour; the converter folds the index back with ``% 64``.
    img.putpalette([c for _ in range(4) for rgb in NES_PALETTE for c in rgb])
    return img


def _dist2(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
            + (a[2] - b[2]) ** 2)


_NES_DIST = None


def _nes_distance_table():
    global _NES_DIST
    if _NES_DIST is None:
        _NES_DIST = tuple(tuple(_dist2(a, b) for b in NES_PALETTE)
                          for a in NES_PALETTE)
    return _NES_DIST


def _palette_cost(hist, palette, bg):
    """Weighted error mapping one block histogram to ``bg + palette``."""
    table = _nes_distance_table()
    bg_row = table[bg]
    rows = tuple(table[c] for c in palette)
    total = 0
    for colour, count in hist.items():
        distance = bg_row[colour]
        for row in rows:
            if row[colour] < distance:
                distance = row[colour]
        total += count * distance
    return total


def _candidate_palettes(hists, bg):
    counts = {}
    for hist in hists:
        for colour, n in hist.items():
            counts[colour] = counts.get(colour, 0) + n
    ranked = [c for c, _n in sorted(counts.items(),
                                    key=lambda item: (-item[1], item[0]))
              if c != bg]
    fill = ranked + [c for c in range(len(NES_PALETTE))
                     if c != bg and c not in ranked]
    candidates = {}
    for hist in hists:
        chosen = []
        for colour, _n in sorted(hist.items(),
                                 key=lambda item: (-item[1], item[0])):
            if colour != bg and colour not in chosen:
                chosen.append(colour)
            if len(chosen) == 3:
                break
        for colour in fill:
            if len(chosen) == 3:
                break
            if colour not in chosen:
                chosen.append(colour)
        candidates[tuple(sorted(chosen))] = True
    for combo in itertools.combinations(ranked[:8], 3):
        candidates[tuple(combo)] = True
    return list(candidates)


def _select_palettes(hists, bg, limit=ART_PALETTES):
    """Pick ``limit`` distinct-colour palettes minimising block error."""
    if not hists:
        alt = (bg + 1) % len(NES_PALETTE)
        return [tuple([alt] * 3) for _ in range(limit)]
    candidates = _candidate_palettes(hists, bg)
    if not candidates:
        alt = (bg + 1) % len(NES_PALETTE)
        return [tuple([alt] * 3) for _ in range(limit)]

    selected = []
    while len(selected) < limit:
        best = None
        best_cost = None
        for cand in candidates:
            if cand in selected:
                continue
            total = 0
            for hist in hists:
                cost = _palette_cost(hist, cand, bg)
                for pal in selected:
                    other = _palette_cost(hist, pal, bg)
                    if other < cost:
                        cost = other
                total += cost
            if best_cost is None or total < best_cost:
                best, best_cost = cand, total
        if best is None:
            break
        selected.append(best)

    for _ in range(4):
        if not selected:
            break
        assign = [min(range(len(selected)),
                      key=lambda i: _palette_cost(hist, selected[i], bg))
                  for hist in hists]
        new = list(selected)
        for i in range(len(selected)):
            members = [hist for hist, a in zip(hists, assign) if a == i]
            if not members:
                continue
            new[i] = min(candidates,
                         key=lambda pal: sum(_palette_cost(hist, pal, bg)
                                             for hist in members))
        seen = set()
        for i, pal in enumerate(new):
            if pal in seen:
                for alt in candidates:
                    if alt not in seen:
                        new[i] = alt
                        break
            seen.add(new[i])
        if new == selected:
            break
        selected = new

    while len(selected) < limit:
        selected.append(selected[-1])
    return selected[:limit]


def _pattern_codes(codes):
    """Map 64 four-colour codes to a 16-byte NES 2bpp planar tile."""
    out = bytearray(16)
    for y in range(8):
        lo = hi = 0
        for x in range(8):
            v = codes[y * 8 + x]
            if v & 1:
                lo |= 1 << (7 - x)
            if v & 2:
                hi |= 1 << (7 - x)
        out[y] = lo
        out[8 + y] = hi
    return bytes(out)


def _tile_codes(pattern):
    """Pack a 2bpp tile's 64 palette indices into 16 bytes (4 per byte)."""
    out = bytearray(16)
    for y in range(8):
        lo = pattern[y]
        hi = pattern[8 + y]
        for half in range(2):
            b = 0
            for x in range(4):
                px = half * 4 + x
                v = ((lo >> (7 - px)) & 1) | (((hi >> (7 - px)) & 1) << 1)
                b = (b << 2) | v
            out[y * 2 + half] = b
    return bytes(out)


_DIFF8 = None


def _diff_table():
    """Squared distance between two 2bpp index bytes (four pixels each)."""
    global _DIFF8
    if _DIFF8 is None:
        table = []
        for a in range(256):
            ac = ((a >> 6) & 3, (a >> 4) & 3, (a >> 2) & 3, a & 3)
            row = bytearray(256)
            for b in range(256):
                bc = ((b >> 6) & 3, (b >> 4) & 3, (b >> 2) & 3, b & 3)
                row[b] = sum((x - y) ** 2 for x, y in zip(ac, bc))
            table.append(bytes(row))
        _DIFF8 = table
    return _DIFF8


def _select_tiles(patterns):
    """Choose up to ``MAX_ART_TILES`` representatives spread over the art.

    Keeping the first N unique patterns biases the budget to the top of the
    picture; farthest-point selection reserves representatives across the
    whole image, then one medoid pass snaps each cluster to a real pattern.
    """
    unique = {}
    order = []
    for pattern in patterns:
        if pattern not in unique:
            unique[pattern] = 0
            order.append(pattern)
        unique[pattern] += 1
    if len(order) <= MAX_ART_TILES:
        return order, {pattern: i for i, pattern in enumerate(order)}

    diff = _diff_table()
    codes = [_tile_codes(pattern) for pattern in order]
    n = len(order)
    dist = [[0] * n for _ in range(n)]
    for i in range(n):
        ci = codes[i]
        for j in range(i + 1, n):
            cj = codes[j]
            d = sum(diff[a][b] for a, b in zip(ci, cj))
            dist[i][j] = dist[j][i] = d
    counts = [unique[pattern] for pattern in order]

    sel = [max(range(n), key=lambda i: counts[i])]
    mind = [dist[i][sel[0]] for i in range(n)]
    while len(sel) < MAX_ART_TILES:
        j = max(range(n), key=lambda i: mind[i])
        if mind[j] <= 0:
            break
        sel.append(j)
        for i in range(n):
            if dist[i][j] < mind[i]:
                mind[i] = dist[i][j]

    assign = [min(range(len(sel)), key=lambda s: dist[i][sel[s]])
              for i in range(n)]
    medoids = []
    for s in range(len(sel)):
        members = [i for i, a in enumerate(assign) if a == s]
        if not members:
            medoids.append(sel[s])
            continue
        medoids.append(min(members,
                           key=lambda i: sum(dist[i][j] for j in members)))
    sel = medoids
    assign = [min(range(len(sel)), key=lambda s: dist[i][sel[s]])
              for i in range(n)]
    tiles = [order[sel[s]] for s in range(len(sel))]
    index = {order[i]: assign[i] for i in range(n)}
    return tiles, index


def _plan(im, conv, art_rows, text_bg):
    from PIL import Image
    import zxart

    art_rows = int(art_rows)
    if art_rows % 2:
        raise ValueError("NES art_rows must be even")
    bg = int(text_bg) & 0x3F
    bg_rgb = NES_PALETTE[bg]
    conv = conv or {}
    im = _fit(im, conv.get("crop"), art_rows)
    adj = conv.get("adjust") or {}
    im = zxart.preprocess(im, adj.get("saturation", 1.0),
                          adj.get("contrast", 1.0),
                          adj.get("brightness", 1.0),
                          adj.get("gamma", 1.0))
    im = zxart.inset_band(im, conv.get("margin", 0), bg_rgb)
    if conv.get("mono"):
        im = zxart.to_mono_image(im, conv.get("dither"))
    indexed = im.quantize(palette=_palette_image(),
                          dither=Image.Dither.NONE)
    indices = [i % len(NES_PALETTE) for i in indexed.getdata()]

    hists = []
    block_rows = art_rows // 2
    for by in range(block_rows):
        for bx in range(16):
            hist = {}
            for y in range(16):
                row = (by * 16 + y) * WIDTH + bx * 16
                for x in range(16):
                    idx = indices[row + x]
                    hist[idx] = hist.get(idx, 0) + 1
            hists.append(hist)
    centers = _select_palettes(hists, bg, ART_PALETTES)
    block_choice = [min(range(len(centers)),
                        key=lambda i: _palette_cost(hist, centers[i], bg))
                    for hist in hists]

    block_palettes = [(bg_rgb,) + tuple(
        NES_PALETTE[c] for c in centers[block_choice[bi]])
        for bi in range(len(block_choice))]

    def palette_at(x, y):
        return block_palettes[(y // 16) * 16 + x // 16]

    codes = zxart.dither_grid(im, palette_at, conv.get("dither", "off"))
    pattern_grid = [[None] * COLS for _ in range(art_rows)]
    for by in range(block_rows):
        for bx in range(16):
            for ty in range(2):
                for tx in range(2):
                    txpix = bx * 2 + tx
                    typix = by * 2 + ty
                    cell = []
                    for y in range(8):
                        row = (typix * 8 + y) * WIDTH + txpix * 8
                        cell.extend(codes[row:row + 8])
                    pattern_grid[typix][txpix] = _pattern_codes(cell)
    flat = [pattern for row in pattern_grid for pattern in row]
    tiles, index = _select_tiles(flat)
    tilemap = [index[pattern] for pattern in flat]

    attrs = bytearray(64)
    for by in range(8):
        for bx in range(8):
            quads = []
            for half in range(4):
                r0 = by * 4 + (2 if half >= 2 else 0)
                c0 = bx * 4 + (2 if half in (1, 3) else 0)
                pal = 0
                if (r0 >= ART_TOP and r0 + 1 <= art_rows + ART_TOP - 1
                        and c0 + 1 < COLS):
                    local_row = (r0 - ART_TOP) // 2
                    local_col = c0 // 2
                    if 0 <= local_row < block_rows and 0 <= local_col < 16:
                        pal = block_choice[local_row * 16 + local_col] + 1
                quads.append(pal & 0x03)
            attrs[by * 8 + bx] = (quads[0] | (quads[1] << 2)
                                  | (quads[2] << 4) | (quads[3] << 6))

    return {
        "ntiles": len(tiles), "bg": bg, "palettes": centers,
        "tiles": tiles, "map": tilemap, "attrs": bytes(attrs),
    }


def art_blob(im, conv=None, art_rows=DEFAULT_ART_ROWS, text_ink=None,
             text_bg=None):
    """Convert one source image; returns ``(blob, ntiles, tiles)``."""
    from PIL import Image

    if isinstance(im, str):
        im = Image.open(im).convert("RGB")
    else:
        im = im.convert("RGB")
    if text_bg is None:
        _ink, _hi, text_bg = text_colours(None)
    plan = _plan(im, conv, art_rows, text_bg)
    out = bytearray(struct.pack("<H", plan["ntiles"]))
    out.append(len(plan["palettes"]))
    for pal in plan["palettes"]:
        out.append(plan["bg"])
        for c in pal:
            out.append(int(c) & 0x3F)
    for value in plan["map"]:
        out += struct.pack("<H", value)
    out += plan["attrs"]
    return bytes(out), plan["ntiles"], plan["tiles"]


def blank_blob(art_rows=DEFAULT_ART_ROWS, text_ink=None, text_bg=None):
    if text_bg is None:
        _ink, _hi, text_bg = text_colours(None)
    bg = int(text_bg) & 0x3F
    out = bytearray(struct.pack("<H", 0))
    out.append(ART_PALETTES)
    for _ in range(ART_PALETTES):
        out += bytes((bg, bg, bg, bg))
    out += bytes(2 * COLS * int(art_rows))
    out += bytes(64)
    return bytes(out)


def preview_image(path, conv=None, options=None, game=None):
    from PIL import Image

    options = options or {}
    art_rows = int(options.get("art_rows") or DEFAULT_ART_ROWS)
    mono = bool((conv or {}).get("mono") or options.get("mono"))
    text_ink, _hi, text_bg = text_colours(game, mono)
    try:
        im = Image.open(path).convert("RGB")
    except Exception:                          # noqa: BLE001 - missing/corrupt
        return None
    plan = _plan(im, conv, art_rows, text_bg)
    palettes = []
    for pal in plan["palettes"]:
        palettes.append((NES_PALETTE[plan["bg"]],)
                        + tuple(NES_PALETTE[c] for c in pal))
    img = Image.new("RGB", (WIDTH, 8 * art_rows))
    pixels = []
    for row in range(art_rows):
        for y in range(8):
            for col in range(COLS):
                idx = plan["map"][row * COLS + col]
                pattern = plan["tiles"][idx] if plan["ntiles"] else bytes(16)
                # Attribute palette for the 2x2 block containing this tile.
                by = (row + ART_TOP) // 4
                bx = col // 4
                quad = ((row + ART_TOP) % 4 >= 2) * 2 + ((col % 4) >= 2)
                attr = plan["attrs"][by * 8 + bx]
                pal = (attr >> (quad * 2)) & 0x03
                colors = (palettes[pal - 1] if pal >= 1
                          else (NES_PALETTE[plan["bg"]],))
                lo = pattern[y]
                hi = pattern[8 + y]
                for x in range(8):
                    v = ((lo >> (7 - x)) & 1) | (((hi >> (7 - x)) & 1) << 1)
                    pixels.append(colors[v] if v < len(colors) else colors[0])
    img.putdata(pixels)
    import zxart
    return zxart.preview_margin_crop(img, (conv or {}).get("margin"), WIDTH,
                                     8 * art_rows)


def preview_bytes(path, conv=None, options=None, game=None):
    img = preview_image(path, conv, options, game)
    if img is None:
        return None
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
