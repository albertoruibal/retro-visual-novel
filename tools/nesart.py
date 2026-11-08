"""Nintendo Entertainment System art conversion helpers.

The editor preview and the ``.nes`` build share this module.  The NES PPU
shows 32x30 background tiles; the shared font occupies tile indices 0..95 and
a highlight copy 96..191, leaving 320 tiles (192..511) for a picture.  A game
band is ``256 x (8 * art_rows)`` pixels and is drawn on rows 2..art_rows+1
(row 0 is the title, row 1 is blank, and the text pane starts at
``art_rows + 2``).  The even start/height keeps the band aligned with the
PPU's 2x2-tile attribute quadrants.

The PPU has four background palettes of four colours; entry 0 is the shared
universal background.  Palette 0 is body text, palette 1 is highlighted text
(the attributes select them) and palettes 2..3 are art palettes (``text_bg``
plus three colours each).  A tile can select one of those palettes per
2x2-tile block through the attribute table.  The NES background pattern table
is only 256 tiles (4KB), so the normal 96-glyph font and up to 160 art tiles
share it; the highlight font is not duplicated (the attribute palette does
that job).

Blob layout (one art, uncompressed in PRG ROM)::

    u16 ntiles               (little-endian)
    u8  npalettes            (always 3)
    u8  palettes[3][4]       NES colour indices; entry 0 is the universal bg
    u16 map[32 * art_rows]   tile indices 0..ntiles-1 (runtime adds 96)
    u8  attrs[64]            full nametable attribute table

The tile patterns themselves live in the art's 8KB CHR ROM bank after the
normal font (96 * 16 = 1536 bytes); the second 4KB of the bank is padding.
"""
from __future__ import annotations

import io
import struct

WIDTH = 256
COLS = 32
HEIGHT_ROWS = 8
FONT_TILES = 96
ART_BASE = FONT_TILES
MAX_ART_TILES = 256 - ART_BASE          # 160 (one 4KB background pattern table)
ART_PALETTES = 2
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


def text_colours(game):
    """Resolve ``# Game`` colours to ``(ink, highlight, bg)`` NES indices."""
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


def chr_bank(normal_font, tiles):
    """Pack the normal font and one art's tiles into an 8KB CHR bank."""
    out = bytearray(normal_font)
    for tile in tiles:
        if len(tile) != 16:
            raise ValueError("NES tile is not 16 bytes")
        out += tile
    if len(out) > 0x2000:
        raise ValueError(f"CHR bank needs {len(out)} bytes (max 8192)")
    out += bytes(0x2000 - len(out))
    return bytes(out)


def _dither(mode):
    from PIL import Image
    m = str(mode or "off").strip().lower()
    return (Image.Dither.NONE if m in ("", "off", "none", "false", "0")
            else Image.Dither.FLOYDSTEINBERG)


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
    img.putpalette([c for rgb in NES_PALETTE for c in rgb])
    return img


def _dist2(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
            + (a[2] - b[2]) ** 2)


def _luma(c):
    return 299 * c[0] + 587 * c[1] + 114 * c[2]


def _block_palette(rgb_cell, bg):
    """Return three non-background colours for one 2x2-tile block."""
    from PIL import Image
    tile = Image.new("RGB", (16, 16))
    tile.putdata(rgb_cell)
    q = tile.quantize(colors=4, method=Image.Quantize.MEDIANCUT,
                      dither=Image.Dither.NONE)
    raw = q.getpalette()[:12]
    counts = q.getcolors(256) or [(1, 0)]
    counts.sort(key=lambda item: (-item[0], item[1]))
    colors = []
    for _n, idx in counts:
        if idx >= 4:
            continue
        c = (raw[idx * 3], raw[idx * 3 + 1], raw[idx * 3 + 2])
        if c not in colors:
            colors.append(c)
        if len(colors) == 4:
            break
    if not colors:
        colors = [bg]
    # Guarantee the universal background is in the block palette.
    if bg not in colors:
        nearest = min(range(len(colors)), key=lambda i: _dist2(colors[i], bg))
        colors[nearest] = bg
    while len(colors) < 4:
        colors.append(bg)
    rest = sorted([c for c in colors if c != bg], key=_luma)
    while len(rest) < 3:
        rest.append(bg)
    return tuple(rest[:3])


def _pal_dist(a, b):
    return sum(_dist2(x, y) for x, y in zip(a, b))


def _mean_palette(palettes):
    if not palettes:
        return ((0, 0, 0),) * 3
    out = []
    for i in range(3):
        r = sum(p[i][0] for p in palettes) / len(palettes)
        g = sum(p[i][1] for p in palettes) / len(palettes)
        b = sum(p[i][2] for p in palettes) / len(palettes)
        out.append((int(round(r)), int(round(g)), int(round(b))))
    return tuple(out)


def _cluster_palettes(palettes, limit=ART_PALETTES):
    if not palettes:
        return []
    limit = max(1, min(int(limit), len(palettes)))
    seed = max(range(len(palettes)),
               key=lambda i: sum(_pal_dist(palettes[i], palettes[j])
                                 for j in range(len(palettes))))
    centers = [palettes[seed]]
    while len(centers) < limit:
        best, bestd = None, -1
        for pal in palettes:
            d = min(_pal_dist(pal, c) for c in centers)
            if d > bestd:
                best, bestd = pal, d
        if best is None or bestd == 0:
            break
        centers.append(best)
    for _ in range(2):
        groups = [[] for _ in centers]
        for pal in palettes:
            groups[min(range(len(centers)),
                       key=lambda i: _pal_dist(pal, centers[i]))].append(pal)
        centers = [_mean_palette(g) if g else centers[i]
                   for i, g in enumerate(groups)]
    return centers


def _nearest(color, palette):
    best, bestd = 0, None
    for i, ref in enumerate(palette):
        d = _dist2(color, ref)
        if bestd is None or d < bestd:
            best, bestd = i, d
    return best


def _tile_pattern(pixels, palette):
    """Map 64 RGB pixels to a 16-byte NES 2bpp planar tile."""
    codes = [_nearest(c, palette) for c in pixels]
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


def _nearest_pattern(pattern, kept):
    best, best_cost = 0, None
    for i, other in enumerate(kept):
        cost = sum(abs(a - b) for a, b in zip(pattern, other))
        if best_cost is None or cost < best_cost:
            best, best_cost = i, cost
    return best


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
    dither = _dither(conv.get("dither"))
    indexed = im.quantize(palette=_palette_image(), dither=dither)
    rgb = list(im.convert("RGB").getdata())

    blocks = []
    block_pals = []
    block_rows = art_rows // 2
    for by in range(block_rows):
        for bx in range(16):
            cell = []
            for y in range(16):
                row = (by * 16 + y) * WIDTH + bx * 16
                cell.extend(rgb[row:row + 16])
            pal = _block_palette(cell, bg_rgb)
            blocks.append(cell)
            block_pals.append(pal)
    centers = _cluster_palettes(block_pals, ART_PALETTES)
    if not centers:
        centers = [((0, 0, 0),) * 3]
    while len(centers) < ART_PALETTES:
        centers.append(centers[-1])
    block_choice = [min(range(len(centers)),
                        key=lambda i: _pal_dist(pal, centers[i]))
                    for pal in block_pals]

    tiles = []
    pixels = []
    lookup = {}
    tilemap = [[0] * COLS for _ in range(art_rows)]
    for by in range(block_rows):
        for bx in range(16):
            bi = by * 16 + bx
            palette = (bg_rgb,) + centers[block_choice[bi]]
            for ty in range(2):
                for tx in range(2):
                    txpix = bx * 2 + tx
                    typix = by * 2 + ty
                    cell = []
                    for y in range(8):
                        row = (typix * 8 + y) * WIDTH + txpix * 8
                        cell.extend(rgb[row:row + 8])
                    pattern = _tile_pattern(cell, palette)
                    idx = lookup.get(pattern)
                    if idx is None:
                        if len(tiles) < MAX_ART_TILES:
                            idx = len(tiles)
                            lookup[pattern] = idx
                            tiles.append(pattern)
                            pixels.append(pattern)
                        else:
                            idx = _nearest_pattern(pattern, pixels)
                    tilemap[typix][txpix] = idx
    tilemap = [idx for row in tilemap for idx in row]

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
                        pal = block_choice[local_row * 16 + local_col] + 2
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
            out.append(_nearest(c, NES_PALETTE))
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
    text_ink, _hi, text_bg = text_colours(game)
    try:
        im = Image.open(path).convert("RGB")
    except Exception:                          # noqa: BLE001 - missing/corrupt
        return None
    plan = _plan(im, conv, art_rows, text_bg)
    palettes = []
    for pal in plan["palettes"]:
        palettes.append(tuple(NES_PALETTE[c] for c in
                              (plan["bg"],) + tuple(
                                  _nearest(c, NES_PALETTE) for c in pal)))
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
                colors = palettes[pal - 2] if pal >= 2 else (NES_PALETTE[plan["bg"]],)
                lo = pattern[y]
                hi = pattern[8 + y]
                for x in range(8):
                    v = ((lo >> (7 - x)) & 1) | (((hi >> (7 - x)) & 1) << 1)
                    pixels.append(colors[v] if v < len(colors) else colors[0])
    img.putdata(pixels)
    return img


def preview_bytes(path, conv=None, options=None, game=None):
    img = preview_image(path, conv, options, game)
    if img is None:
        return None
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
