"""Nintendo Game Boy Color art conversion helpers.

The editor preview and the ``.gbc`` build share this module.  The Game Boy
Color shows the same 160x144, 20x18 tile screen as the DMG, but each background
tile may select one of eight four-colour palettes.  A game band is
160 x (8 * art_rows) pixels; the runtime keeps 96 font tiles and two scroll
arrow tiles in VRAM, so an art may use at most 158 distinct tile patterns.

Palettes 6 and 7 are reserved for body text and highlighted text, so the
picture uses palettes 0..5 (up to 24 adaptive colours).  Each palette is
ordered light-to-dark: on a monochrome Game Boy the built-in BGP mapping then
still shows the band as a sensible four-shade picture.

Blob layout (one art, stored raw in an MBC1 ROM bank)::

    u8  ntiles
    u8  npalettes
    u16 palettes[npalettes][4] RGB555, little-endian
    u8  tiles[ntiles * 16]     2bpp: per row a low plane then a high plane
    u8  map[20 * art_rows]     tile indices, already offset by 96
    u8  attrs[20 * art_rows]   GBC background attribute (palette index)

Index 0 is the lightest colour of its palette and 3 the darkest, matching the
DMG's default BGP mapping so the enhanced cartridge still renders on an
original Game Boy.
"""
from __future__ import annotations

import io

WIDTH = 160
COLS = WIDTH // 8
DEFAULT_ART_ROWS = 8
FONT_TILES = 96
ARROW_TILES = 254
MAX_ART_TILES = 256 - FONT_TILES - 2
MAX_ART_PALETTES = 6
TEXT_PALETTE = 6
TEXT_SEL_PALETTE = 7

# `# Game` text colour token -> bright 8-bit RGB values.
_TEXT_RGB = {
    "black": (0, 0, 0), "blue": (0, 0, 255), "green": (0, 255, 0),
    "cyan": (0, 255, 255), "red": (255, 0, 0), "magenta": (255, 0, 255),
    "yellow": (255, 255, 0), "white": (255, 255, 255),
}


def rgb555(r, g, b):
    """Pack 8-bit RGB components into a GBC RGB555 value."""
    return (((int(r) >> 3) & 31) | (((int(g) >> 3) & 31) << 5)
            | (((int(b) >> 3) & 31) << 10))


def rgb555_rgb8(value):
    """Expand one GBC RGB555 value to an 8-bit preview colour."""
    return (((value & 31) * 255) // 31,
            (((value >> 5) & 31) * 255) // 31,
            (((value >> 10) & 31) * 255) // 31)


def text_ink(token):
    """Map a scenefile colour token to a GBC RGB555 colour."""
    t = str(token or "").strip().lower()
    dim = t.startswith("dim_")
    name = t[4:] if dim else t
    rgb = _TEXT_RGB.get(name, _TEXT_RGB["white"])
    if dim:
        rgb = tuple((v * 2) // 3 for v in rgb)
    return rgb555(*rgb)


def text_colours(game, mono=False):
    """Resolve the ``# Game`` text colours to GBC RGB555 values.

    Returns ``(text_ink, highlight_ink, text_bg)``.  ``mono`` forces white
    text on black.
    """
    if mono:
        white = rgb555(255, 255, 255)
        return white, white, rgb555(0, 0, 0)
    import scenefile
    text, highlight, bg = scenefile.text_tokens(game)
    return text_ink(text), text_ink(highlight), text_ink(bg)


def _fit(im, crop, art_rows):
    """Crop/scale a source to the 160 x (8*art_rows) Game Boy Color band."""
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


def _prepare(im, conv, art_rows, fill=(0, 0, 0)):
    import zxart

    conv = conv or {}
    im = _fit(im, conv.get("crop"), art_rows)
    adj = conv.get("adjust") or {}
    im = zxart.preprocess(im, adj.get("saturation", 1.0),
                          adj.get("contrast", 1.0),
                          adj.get("brightness", 1.0),
                          adj.get("gamma", 1.0))
    im = zxart.inset_band(im, conv.get("margin", 0), fill)
    if conv.get("mono"):
        im = zxart.to_mono_image(im, conv.get("dither"))
    return im


def _dither_on(conv):
    mode = str((conv or {}).get("dither") or "off").strip().lower()
    return mode not in ("off", "none", "false", "0")


def _luma(color):
    r, g, b = color
    return 299 * r + 587 * g + 114 * b


def _dist2(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
            + (a[2] - b[2]) ** 2)


def _palette4(tile):
    """Return a four-colour RGB555-aligned palette for one 8x8 tile."""
    from PIL import Image

    q = tile.quantize(colors=4, method=Image.Quantize.MEDIANCUT,
                      dither=Image.Dither.NONE)
    raw = q.getpalette()[:12]
    counts = q.getcolors(256) or [(1, 0)]
    counts.sort(key=lambda item: (-item[0], item[1]))
    colors = []
    for _count, index in counts:
        if index >= 4:
            continue
        colors.append((raw[index * 3], raw[index * 3 + 1],
                       raw[index * 3 + 2]))
        if len(colors) == 4:
            break
    if not colors:
        colors.append((0, 0, 0))
    while len(colors) < 4:
        colors.append(colors[-1])
    colors.sort(key=_luma, reverse=True)
    return tuple(rgb555_rgb8(rgb555(*c)) for c in colors)


def _pal_dist(a, b):
    return sum(_dist2(x, y) for x, y in zip(a, b))


def _pal_spread(pal):
    return sum(_dist2(pal[i], pal[j])
               for i in range(4) for j in range(i + 1, 4))


def _mean_palette(palettes):
    if not palettes:
        return None
    out = []
    for i in range(4):
        r = sum(p[i][0] for p in palettes) / len(palettes)
        g = sum(p[i][1] for p in palettes) / len(palettes)
        b = sum(p[i][2] for p in palettes) / len(palettes)
        out.append(rgb555_rgb8(rgb555(round(r), round(g), round(b))))
    out.sort(key=_luma, reverse=True)
    return tuple(out)


def _cluster_palettes(palettes, limit):
    """Cluster tile palettes into at most ``limit`` shared palettes."""
    if not palettes:
        return []
    limit = max(1, min(int(limit), len(palettes)))
    seed = max(range(len(palettes)), key=lambda i: _pal_spread(palettes[i]))
    centers = [palettes[seed]]
    while len(centers) < limit:
        best, bestd = None, -1
        for pal in palettes:
            dist = min(_pal_dist(pal, c) for c in centers)
            if dist > bestd:
                best, bestd = pal, dist
        if best is None or bestd == 0:
            break
        centers.append(best)
    for _ in range(2):
        groups = [[] for _ in centers]
        for pal in palettes:
            index = min(range(len(centers)),
                        key=lambda i: _pal_dist(pal, centers[i]))
            groups[index].append(pal)
        centers = [(_mean_palette(group) if group else centers[i])
                   for i, group in enumerate(groups)]
    return centers


def _nearest(color, palette):
    best, bestd = 0, None
    for i, ref in enumerate(palette):
        dist = _dist2(color, ref)
        if bestd is None or dist < bestd:
            best, bestd = i, dist
    return best, palette[best]


def _map_tile(tile, palette, dither):
    """Map one 8x8 tile to 0..3 indices, optionally with Floyd-Steinberg."""
    pixels = list(tile.convert("RGB").getdata())
    out = [0] * 64
    if not dither:
        for i, color in enumerate(pixels):
            out[i], _ = _nearest(color, palette)
        return out
    work = [[float(c) for c in color] for color in pixels]
    taps = ((1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1))
    for y in range(8):
        for x in range(8):
            i = y * 8 + x
            index, chosen = _nearest(work[i], palette)
            out[i] = index
            err = [work[i][k] - chosen[k] for k in range(3)]
            for dx, dy, weight in taps:
                nx, ny = x + dx, y + dy
                if 0 <= nx < 8 and 0 <= ny < 8:
                    ni = ny * 8 + nx
                    for k in range(3):
                        work[ni][k] += err[k] * weight / 16.0
    return out


def _tile_cost(tile, palette):
    return sum(min(_dist2(color, ref) for ref in palette)
               for color in tile.convert("RGB").getdata())


def band_plan(im, conv=None, art_rows=DEFAULT_ART_ROWS,
              max_palettes=MAX_ART_PALETTES, fill=(0, 0, 0)):
    """Plan the GBC band: palette list, per-tile palette and pixel indices."""
    art_rows = int(art_rows)
    im = _prepare(im, conv, art_rows, fill)
    tile_palettes = []
    tiles = []
    for ty in range(art_rows):
        for tx in range(COLS):
            tile = im.crop((tx * 8, ty * 8, tx * 8 + 8, ty * 8 + 8))
            tiles.append(tile)
            tile_palettes.append(_palette4(tile))
    centers = _cluster_palettes(tile_palettes, max_palettes)
    tile_pal = []
    for tile in tiles:
        tile_pal.append(min(range(len(centers)),
                            key=lambda i: _tile_cost(tile, centers[i])))
    used = sorted(set(tile_pal))
    remap = {old: new for new, old in enumerate(used)}
    palettes = [centers[i] for i in used]
    tile_pal = [remap[i] for i in tile_pal]
    dither = _dither_on(conv)
    grid = [0] * (WIDTH * 8 * art_rows)
    for index, tile in enumerate(tiles):
        ty, tx = divmod(index, COLS)
        values = _map_tile(tile, palettes[tile_pal[index]], dither)
        for y in range(8):
            row = (ty * 8 + y) * WIDTH + tx * 8
            for x in range(8):
                grid[row + x] = values[y * 8 + x]
    return {"grid": grid, "tile_pal": tile_pal, "palettes": palettes}


def _tile(grid, tx, ty):
    out = bytearray(16)
    for y in range(8):
        lo = hi = 0
        row = (ty * 8 + y) * WIDTH + tx * 8
        for x in range(8):
            v = grid[row + x]
            if v & 1:
                lo |= 1 << (7 - x)
            if v & 2:
                hi |= 1 << (7 - x)
        out[y * 2] = lo
        out[y * 2 + 1] = hi
    return bytes(out)


def _tile_pixels(grid, tx, ty):
    return tuple(grid[(ty * 8 + y) * WIDTH + tx * 8 + x]
                 for y in range(8) for x in range(8))


def _nearest_pattern(pixels, kept):
    best, best_cost = 0, None
    for i, other in enumerate(kept):
        cost = sum(abs(a - b) for a, b in zip(pixels, other))
        if best_cost is None or cost < best_cost:
            best, best_cost = i, cost
    return best


def art_blob(im, conv=None, art_rows=DEFAULT_ART_ROWS,
             max_tiles=MAX_ART_TILES, max_palettes=MAX_ART_PALETTES,
             fill=(0, 0, 0)):
    """Convert one source image to the Game Boy Color art blob."""
    from PIL import Image

    if isinstance(im, str):
        im = Image.open(im).convert("RGB")
    else:
        im = im.convert("RGB")
    art_rows = int(art_rows)
    plan = band_plan(im, conv, art_rows, max_palettes, fill)
    grid = plan["grid"]
    tile_pal = plan["tile_pal"]
    palettes = plan["palettes"]
    tiles = []
    pixels = []
    pixels_pal = []
    lookup = {}
    tilemap = []
    attrs = []
    for ty in range(art_rows):
        for tx in range(COLS):
            key = _tile_pixels(grid, tx, ty)
            index = lookup.get(key)
            attr = tile_pal[ty * COLS + tx]
            if index is None:
                if len(tiles) < max_tiles:
                    index = len(tiles)
                    lookup[key] = index
                    tiles.append(_tile(grid, tx, ty))
                    pixels.append(key)
                    pixels_pal.append(attr)
                else:
                    # The band has only two more cells than the tile cap.  Reuse
                    # a pattern and its own palette so the colours stay coherent.
                    same = [i for i, p in enumerate(pixels_pal) if p == attr]
                    if same:
                        index = same[_nearest_pattern(
                            key, [pixels[i] for i in same])]
                    else:
                        index = _nearest_pattern(key, pixels)
                    attr = pixels_pal[index]
            tilemap.append(FONT_TILES + index)
            attrs.append(attr)
    out = bytearray((len(tiles), len(palettes)))
    for palette in palettes:
        for color in palette:
            out += rgb555(*color).to_bytes(2, "little")
    for tile in tiles:
        out += tile
    out += bytes(tilemap)
    out += bytes(attrs)
    return bytes(out), len(tiles)


def blank_blob(art_rows=DEFAULT_ART_ROWS):
    """A blank art band; the runtime clears the band for zero tiles."""
    return bytes((0, 0))


def band(im, conv=None, art_rows=DEFAULT_ART_ROWS, fill=(0, 0, 0)):
    """Return the band as an RGB image using the GBC palettes."""
    from PIL import Image

    art_rows = int(art_rows)
    plan = band_plan(im, conv, art_rows, fill=fill)
    grid = plan["grid"]
    palettes = plan["palettes"]
    tile_pal = plan["tile_pal"]
    img = Image.new("RGB", (WIDTH, 8 * art_rows))
    data = []
    for y in range(8 * art_rows):
        ty = y // 8
        for x in range(WIDTH):
            tx = x // 8
            palette = palettes[tile_pal[ty * COLS + tx]]
            data.append(palette[grid[y * WIDTH + x]])
    img.putdata(data)
    return img


def preview_image(path, conv=None, options=None, game=None):
    from PIL import Image

    options = options or {}
    art_rows = int(options.get("art_rows") or DEFAULT_ART_ROWS)
    mono = bool((conv or {}).get("mono") or options.get("mono"))
    try:
        im = Image.open(path).convert("RGB")
    except Exception:                          # noqa: BLE001 - missing/corrupt
        return None
    _ink, _hi, text_bg = text_colours(game, mono)
    img = band(im, conv, art_rows, rgb555_rgb8(text_bg))
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


def _reverse8(n):
    n = ((n & 0xF0) >> 4) | ((n & 0x0F) << 4)
    n = ((n & 0xCC) >> 2) | ((n & 0x33) << 2)
    n = ((n & 0xAA) >> 1) | ((n & 0x55) << 1)
    return n


def font_tiles(font8, accents=None):
    """Expand 96 8x8 1bpp glyphs to Game Boy Color 2bpp tiles (colour 3).

    ``font8`` rows are LSB-left (the vendored font8x8 convention); the Game
    Boy pattern table is MSB-left, so every row is bit-reversed. ``accents``
    maps a byte code to eight replacement LSB-left rows.
    """
    if len(font8) != FONT_TILES * 8:
        raise ValueError(f"expected {FONT_TILES * 8} font bytes, "
                         f"got {len(font8)}")
    glyphs = [bytearray(font8[i * 8:(i + 1) * 8])
              for i in range(FONT_TILES)]
    for code, rows in (accents or {}).items():
        index = code - 32
        if not 0 <= index < FONT_TILES or len(rows) != 8:
            raise ValueError(f"bad accent slot 0x{code:02X}")
        glyphs[index] = bytearray(rows)
    out = bytearray()
    for glyph in glyphs:
        for row in glyph:
            bits = _reverse8(row)
            out += bytes((bits, bits))
    return bytes(out)
