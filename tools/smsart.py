"""Sega Master System art conversion helpers.

The editor preview and the .sms build share this module.  SMS mode 4 tiles are
8x8, 4bpp planar; a game band is 256 x (8 * art_rows) pixels and uses the
VDP's 16-colour background palette.  Palette entry 0 is the configured text
background, entry 1 the configured text ink, and the remaining 14 colours come
from the art.  The highlight ink lives in the sprite palette's entry 1 (entry 0
is the same background).

The build stores one art per ROM bank as
``[u16 ntiles][u8 palette[16]][u16 map[32*art_rows]][tiles[ntiles*32]]``.
Tile indices in the map are pre-offset by ``FONT_TILES`` (98): the 96 glyph
tiles plus the two scroll-arrow tiles the text layer uploads first.
"""
from __future__ import annotations

import io
import struct

FONT_TILES = 98          # 96 glyphs + up/down scroll arrows
MAX_TILES = 448 - FONT_TILES
SMS_LEVELS = (0, 85, 170, 255)


def sms_color(rgb):
    """Round an RGB triple to the SMS's 6-bit ``--BBGGRR`` CRAM value."""
    r = max(0, min(3, int(rgb[0]) >> 6))
    g = max(0, min(3, int(rgb[1]) >> 6))
    b = max(0, min(3, int(rgb[2]) >> 6))
    return r | (g << 2) | (b << 4)


def color_rgb(value):
    """Expand a 6-bit SMS CRAM value to an 8-bit preview colour."""
    return (SMS_LEVELS[value & 3], SMS_LEVELS[(value >> 2) & 3],
            SMS_LEVELS[(value >> 4) & 3])


# `# Game` text colour token -> (dim, bright) SMS CRAM values.  Dim colours use
# level 2 of the 0..3 channel scale, bright colours level 3.
_TEXT_INKS = {
    "black": (0x00, 0x00), "blue": (0x20, 0x30), "green": (0x08, 0x0C),
    "cyan": (0x28, 0x3C), "red": (0x02, 0x03), "magenta": (0x22, 0x33),
    "yellow": (0x0A, 0x0F), "white": (0x2A, 0x3F),
}


def text_ink(token):
    """Map a scenefile colour token to an SMS CRAM colour."""
    t = str(token or "").strip().lower()
    dim = t.startswith("dim_")
    name = t[4:] if dim else t
    pair = _TEXT_INKS.get(name, _TEXT_INKS["white"])
    return pair[0] if dim else pair[1]


def text_colours(game):
    """Resolve the ``# Game`` text colours to SMS CRAM colours.

    Returns ``(text_ink, highlight_ink, text_bg)``.
    """
    import scenefile
    text, highlight, bg = scenefile.text_tokens(game)
    return text_ink(text), text_ink(highlight), text_ink(bg)


def _fit(im, crop, art_rows, width=256):
    """Crop/scale a source to the SMS band (width x 8*art_rows)."""
    from PIL import Image
    import zxart
    art_rows = int(art_rows)
    height = 8 * art_rows
    w, h = im.size
    box = im.crop(zxart.band_crop_rect(crop, w, h, width / float(height)))
    target = (width, height)
    if box.size != target:
        box = box.resize(target, Image.LANCZOS)
    return box


def _dither(mode):
    from PIL import Image
    return (Image.Dither.NONE if str(mode or "off").lower() == "off"
            else Image.Dither.FLOYDSTEINBERG)


def band_indexed(im, conv=None, art_rows=12, text_ink=None, text_bg=None):
    """Return ``(indices, palette)`` for a 256 x (8*art_rows) SMS band.

    ``indices`` is a flat row-major list of 0..15 palette entries and
    ``palette`` is 16 6-bit CRAM values.  Entry 0 is the configured text
    background and entry 1 the text ink, so the text tiles stay readable; the
    rest are chosen from the image.
    """
    from PIL import Image
    import zxart

    conv = conv or {}
    if text_ink is None or text_bg is None:
        default_text, _default_hi, default_bg = text_colours(None)
        if text_ink is None:
            text_ink = default_text
        if text_bg is None:
            text_bg = default_bg
    text_ink = int(text_ink) & 0x3F
    text_bg = int(text_bg) & 0x3F
    art_rows = int(art_rows)
    im = _fit(im, conv.get("crop"), art_rows)
    adj = conv.get("adjust") or {}
    im = zxart.preprocess(im, adj.get("saturation", 1.0),
                          adj.get("contrast", 1.0),
                          adj.get("brightness", 1.0),
                          adj.get("gamma", 1.0))
    im = zxart.inset_band(im, conv.get("margin", 0), color_rgb(text_bg))
    dither = _dither(conv.get("dither"))
    q = im.quantize(colors=14, method=Image.Quantize.MEDIANCUT, dither=dither)
    raw = q.getpalette()[:42]
    palette = [text_bg, text_ink] + [sms_color(raw[i:i + 3])
                                     for i in range(0, 42, 3)]
    palette += [0x00] * (16 - len(palette))
    rgb = [c for value in palette for c in color_rgb(value)]
    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette(rgb)
    indexed = im.quantize(palette=pal_img, dither=dither)
    return list(indexed.getdata()), palette


def _tile(grid, width, tx, ty):
    # SMS mode 4 stores four plane bytes per row: [p0 p1 p2 p3] * 8 rows.
    tile = [0] * 32
    for y in range(8):
        row = (ty * 8 + y) * width + tx * 8
        for x in range(8):
            v = grid[row + x]
            for plane in range(4):
                if v & (1 << plane):
                    tile[y * 4 + plane] |= 1 << (7 - x)
    return tile


def _tile_pixels(grid, width, tx, ty):
    return [grid[(ty * 8 + y) * width + tx * 8 + x]
            for y in range(8) for x in range(8)]


def _nearest(pixels, kept):
    best = 0
    best_cost = None
    for i, other in enumerate(kept):
        cost = 0
        for a, b in zip(pixels, other):
            cost += abs(a - b)
            if best_cost is not None and cost >= best_cost:
                break
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best = i
    return best


def art_blob(im, conv=None, art_rows=12, max_tiles=MAX_TILES,
             text_ink=None, text_bg=None):
    """Convert one source image to the SMS bank blob.

    ``im`` is a PIL image or a path.  Returns ``(blob, ntiles)``.  Tile
    patterns are deduplicated; when a band has more than ``max_tiles`` unique
    tiles the excess cells reuse the nearest kept tile so the art plus the 96
    text glyphs always fit the VDP's 448 patterns.
    """
    from PIL import Image

    if isinstance(im, str):
        im = Image.open(im).convert("RGB")
    else:
        im = im.convert("RGB")
    art_rows = int(art_rows)
    width = 256
    grid, palette = band_indexed(im, conv, art_rows, text_ink, text_bg)
    tiles = []
    pixels = []
    lookup = {}
    tilemap = []
    for ty in range(art_rows):
        for tx in range(width // 8):
            key = tuple(_tile_pixels(grid, width, tx, ty))
            index = lookup.get(key)
            if index is None:
                if len(tiles) < max_tiles:
                    index = len(tiles)
                    lookup[key] = index
                    tiles.append(bytes(_tile(grid, width, tx, ty)))
                    pixels.append(key)
                else:
                    index = _nearest(key, pixels)
            tilemap.append(FONT_TILES + index)
    out = bytearray()
    out += struct.pack("<H", len(tiles))
    out += bytes(palette)
    for value in tilemap:
        out += struct.pack("<H", value)
    for tile in tiles:
        out += tile
    return bytes(out), len(tiles)


def blank_blob(art_rows=12, text_ink=None, text_bg=None):
    """A blob for an art with no source image (palette + empty map)."""
    if text_ink is None or text_bg is None:
        default_text, _default_hi, default_bg = text_colours(None)
        if text_ink is None:
            text_ink = default_text
        if text_bg is None:
            text_bg = default_bg
    out = bytearray(struct.pack("<H", 0))
    out += bytes([int(text_bg) & 0x3F, int(text_ink) & 0x3F] + [0x00] * 14)
    out += bytes(32 * int(art_rows) * 2)
    return bytes(out)


def band(im, conv=None, art_rows=12, text_ink=None, text_bg=None):
    """Return the band as an RGB image using the SMS hardware palette."""
    from PIL import Image
    grid, palette = band_indexed(im, conv, art_rows, text_ink, text_bg)
    rgb = [color_rgb(value) for value in palette]
    img = Image.new("RGB", (256, 8 * int(art_rows)))
    img.putdata([rgb[v] for v in grid])
    return img


def preview_image(path, conv=None, options=None, text_ink=None, text_bg=None):
    """Return a PIL image of the SMS band, or None if Pillow cannot read it."""
    from PIL import Image

    options = options or {}
    art_rows = int(options.get("art_rows") or 12)
    im = Image.open(path).convert("RGB")
    return band(im, conv, art_rows, text_ink, text_bg)


def preview_bytes(path, conv=None, options=None, text_ink=None, text_bg=None):
    img = preview_image(path, conv, options, text_ink, text_bg)
    if img is None:
        return None
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
