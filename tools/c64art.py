"""Commodore 64 art conversion helpers (VIC-II multicolor characters).

The editor preview and the ``.prg`` build share this module.  A game band is
``160 x (8 * art_rows)`` logical pixels (the C64 displays multicolor pixels
twice as wide, so the preview is rendered at 320 x ``8 * art_rows``).  Text
uses the shared 8x8 hi-res font; art cells use 4x8 multicolor characters.

A multicolor character cell has four colours: the global ``$D021``
background, the two global colours ``$D022``/``$D023`` shared by every
multicolor character on screen, and the per-cell colour RAM value (0..7).
The converter fixes ``$D021`` to the game's ``text_bg`` and chooses the two
globals from the image; each cell then adds one colour from the first eight
C64 palette entries.

Blob layout (one art, ZX0-compressed in the ``.prg``)::

    u8  ntiles
    u8  color22
    u8  color23
    u8  tiles[ntiles * 8]    2bpp multicolor patterns (4 pixels/row)
    u8  map[40 * art_rows]   tile indices (runtime adds 96)
    u8  colors[40 * art_rows] colour RAM value with the multicolor bit set

96 charset entries are reserved for text, so an art may use at most 160
distinct patterns (indices 96..255 in the 256-entry charset).  Excess cells
reuse the nearest kept pattern.
"""
from __future__ import annotations

import io

WIDTH = 160
COLS = 40
FONT_TILES = 96
MAX_ART_TILES = 160
DEFAULT_ART_ROWS = 8

# The standard Pepto C64 palette (indices 0..15).
C64_PALETTE = (
    (0x00, 0x00, 0x00), (0xFF, 0xFF, 0xFF), (0x88, 0x00, 0x00),
    (0xAA, 0xFF, 0xEE), (0xCC, 0x44, 0xCC), (0x00, 0xCC, 0x55),
    (0x00, 0x00, 0xAA), (0xEE, 0xEE, 0x77), (0xDD, 0x88, 0x55),
    (0x66, 0x44, 0x00), (0xFF, 0x77, 0x77), (0x33, 0x33, 0x33),
    (0x77, 0x77, 0x77), (0xAA, 0xFF, 0x66), (0x00, 0x88, 0xFF),
    (0xBB, 0xBB, 0xBB),
)

# `# Game` text token -> C64 palette index.  Multicolor character mode uses
# color-RAM bit 3 as its mode flag, so text foregrounds are limited to 0..7.
_TEXT_INDEX = {
    "black": 0, "white": 1, "red": 2, "cyan": 3,
    "magenta": 4, "green": 5, "blue": 6, "yellow": 7,
}
# Dim backgrounds may use the full 16-colour palette.
_DIM_BG = {
    "black": 0, "white": 11, "red": 9, "cyan": 3,
    "magenta": 4, "green": 5, "blue": 6, "yellow": 7,
}


def text_ink(token):
    """Map a scenefile colour token to one of the first eight C64 colours."""
    t = str(token or "").strip().lower()
    name = t[4:] if t.startswith("dim_") else t
    return _TEXT_INDEX.get(name, _TEXT_INDEX["white"])


def text_bg_index(token):
    """Map a scenefile background token to a full 16-colour C64 index."""
    t = str(token or "").strip().lower()
    if t.startswith("dim_"):
        return _DIM_BG.get(t[4:], 0)
    return _TEXT_INDEX.get(t, 0)


def text_colours(game, mono=False):
    """Resolve the ``# Game`` colours to ``(ink, highlight, bg)`` C64 indices."""
    if mono:
        return 1, 1, 0
    import scenefile
    text, highlight, bg = scenefile.text_tokens(game)
    return text_ink(text), text_ink(highlight), text_bg_index(bg)


def _fit(im, crop, art_rows):
    """Crop/scale a source to the 160 x (8*art_rows) logical band."""
    from PIL import Image
    import zxart
    art_rows = int(art_rows)
    height = 8 * art_rows
    w, h = im.size
    # The C64 displays the 160 logical columns as 320 physical pixels.
    box = im.crop(zxart.band_crop_rect(crop, w, h, (WIDTH * 2) / float(height)))
    target = (WIDTH, height)
    if box.size != target:
        box = box.resize(target, Image.LANCZOS)
    return box


def _palette_image():
    from PIL import Image
    img = Image.new("P", (1, 1))
    img.putpalette([c for rgb in C64_PALETTE for c in rgb])
    return img


def _dist2(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
            + (a[2] - b[2]) ** 2)


def _cell_pattern(codes):
    """Pack 32 2-bit codes (4 per row) into 8 C64 character bytes."""
    out = bytearray(8)
    for y in range(8):
        v = 0
        for x in range(4):
            v = (v << 2) | codes[y * 4 + x]
        out[y] = v
    return bytes(out)


def _nearest_pattern(pattern, kept):
    best, best_cost = 0, None
    for i, other in enumerate(kept):
        cost = sum(abs(a - b) for a, b in zip(pattern, other))
        if best_cost is None or cost < best_cost:
            best, best_cost = i, cost
    return best


def _plan(im, conv, art_rows, text_bg):
    """Return ``(ntiles, c22, c23, tiles, map, colors)`` for one band."""
    from PIL import Image

    art_rows = int(art_rows)
    bg = int(text_bg) & 0x0F
    conv = conv or {}
    im = _fit(im, conv.get("crop"), art_rows)
    adj = conv.get("adjust") or {}
    import zxart
    im = zxart.preprocess(im, adj.get("saturation", 1.0),
                          adj.get("contrast", 1.0),
                          adj.get("brightness", 1.0),
                          adj.get("gamma", 1.0))
    im = zxart.inset_band(im, conv.get("margin", 0), C64_PALETTE[bg])
    if conv.get("mono"):
        im = zxart.to_mono_image(im, conv.get("dither"))
    indexed = list(im.quantize(palette=_palette_image(),
                               dither=Image.Dither.NONE).getdata())
    rgb = list(im.convert("RGB").getdata())

    counts = [0] * 16
    for value in indexed:
        counts[value] += 1
    counts[bg] = 0
    order = sorted(range(16), key=lambda i: (-counts[i], i))
    c22 = next((i for i in order if i != bg), 1)
    c23 = next((i for i in order if i != bg and i != c22), 0)

    cell_v = []
    cell_palettes = []
    for ty in range(art_rows):
        for tx in range(COLS):
            rgb_cell = []
            for y in range(8):
                row = (ty * 8 + y) * WIDTH + tx * 4
                rgb_cell.extend(rgb[row:row + 4])
            best_v = 0
            best_cost = None
            for v in range(8):
                palette = (C64_PALETTE[bg], C64_PALETTE[c22],
                           C64_PALETTE[c23], C64_PALETTE[v])
                cost = sum(min(_dist2(p, ref) for ref in palette)
                           for p in rgb_cell)
                if best_cost is None or cost < best_cost:
                    best_cost, best_v = cost, v
            cell_v.append(best_v)
            cell_palettes.append((C64_PALETTE[bg], C64_PALETTE[c22],
                                  C64_PALETTE[c23], C64_PALETTE[best_v]))

    def palette_at(x, y):
        return cell_palettes[(y // 8) * COLS + (x // 4)]

    codes = zxart.dither_grid(im, palette_at,
                              conv.get("dither", "off"))
    tiles = []
    pixels = []
    lookup = {}
    tilemap = []
    colors = []
    for ty in range(art_rows):
        for tx in range(COLS):
            cell_codes = []
            for y in range(8):
                row = (ty * 8 + y) * WIDTH + tx * 4
                cell_codes.extend(codes[row:row + 4])
            pattern = _cell_pattern(cell_codes)
            index = lookup.get(pattern)
            if index is None:
                if len(tiles) < MAX_ART_TILES:
                    index = len(tiles)
                    lookup[pattern] = index
                    tiles.append(pattern)
                    pixels.append(pattern)
                else:
                    index = _nearest_pattern(pattern, pixels)
            tilemap.append(index)
            colors.append(0x08 | cell_v[ty * COLS + tx])
    return len(tiles), c22, c23, tiles, tilemap, colors


def art_blob(im, conv=None, art_rows=DEFAULT_ART_ROWS, text_ink=None,
             text_bg=None):
    """Convert one source image to the C64 art blob; returns ``(blob, ntiles)``."""
    from PIL import Image

    if isinstance(im, str):
        im = Image.open(im).convert("RGB")
    else:
        im = im.convert("RGB")
    if text_bg is None:
        _ink, _hi, text_bg = text_colours(None)
    ntiles, c22, c23, tiles, tilemap, colors = _plan(
        im, conv, art_rows, text_bg)
    out = bytearray((ntiles, c22, c23))
    for tile in tiles:
        out += tile
    out += bytes(tilemap)
    out += bytes(colors)
    return bytes(out), ntiles


def blank_blob(art_rows=DEFAULT_ART_ROWS, text_ink=None, text_bg=None):
    """A blank band blob (the runtime clears the art rows for zero tiles)."""
    if text_bg is None:
        _ink, _hi, text_bg = text_colours(None)
    return bytes((0, 0, 0)) + bytes(2 * COLS * int(art_rows))


def band(im, conv=None, art_rows=DEFAULT_ART_ROWS, text_ink=None,
         text_bg=None):
    """Return the band as a 320 x (8*art_rows) RGB image."""
    from PIL import Image

    if text_bg is None:
        _ink, _hi, text_bg = text_colours(None)
    ntiles, c22, c23, tiles, tilemap, colors = _plan(
        im, conv, art_rows, text_bg)
    art_rows = int(art_rows)
    img = Image.new("RGB", (WIDTH * 2, 8 * art_rows))
    pixels = []
    for ty in range(art_rows):
        for y in range(8):
            for tx in range(COLS):
                idx = ty * COLS + tx
                pattern = tiles[tilemap[idx]] if ntiles else bytes(8)
                v = colors[idx] & 0x07
                palette = (C64_PALETTE[int(text_bg) & 0x0F],
                           C64_PALETTE[c22], C64_PALETTE[c23],
                           C64_PALETTE[v])
                byte = pattern[y]
                for x in range(4):
                    code = (byte >> (6 - 2 * x)) & 0x03
                    pixels.append(palette[code])
                    pixels.append(palette[code])
    img.putdata(pixels)
    return img


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
    img = band(im, conv, art_rows, text_ink, text_bg)
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
