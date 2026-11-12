#!/usr/bin/env python3
"""ZX Spectrum bicolor tile conversion shared by the adventure toolchain.

NIRVANA+ tile format (verified against the engine's asm_NIRVANAP_drawT): a
16x16 bicolor tile is 48 bytes:

    32 bytes bitmap : 16 pixel rows x 2 bytes (8 px each)
    16 bytes attr   : column-major; bytes 0..7 = left 8px column, rows 0..7
                      (one attr per 2px line-pair), bytes 8..15 = right
                      column. attr byte = INK | (PAPER<<3) | (BRIGHT<<6)

The engine computes the tile address as base + index*48, so the blob must be
16x16 tiles at that stride. A 256x80 art band is 16x5 tiles (80 tiles max), so
a per-art tile index always fits one byte with no clustering. The band height is
per game (the ZX ``## zx128 art_rows``): most functions take an optional ``rows`` (16px
tile rows) that defaults to the 256x80 band's 5.
"""
import hashlib

# ZX Spectrum palette; 0..7 normal, 8..15 bright (RGB repeated).
SPEC = [
    (0, 0, 0), (0, 0, 192), (192, 0, 0), (192, 0, 192),
    (0, 192, 0), (0, 192, 192), (192, 192, 0), (192, 192, 192),
    (0, 0, 0), (0, 0, 255), (255, 0, 0), (255, 0, 255),
    (0, 255, 0), (0, 255, 255), (255, 255, 0), (255, 255, 255),
]

BAND_W, BAND_H = 256, 80
COLS, ROWS = 16, 5
TILE_BYTES = 48
MAP_LEN = COLS * ROWS          # 80 bytes


def tile_rows(rows):
    """Tile rows for an optional band-height override (default ``ROWS``)."""
    return ROWS if rows is None else int(rows)


def band_h(rows):
    """Band height in pixels for ``rows`` 16px tile rows."""
    return 16 * tile_rows(rows)


def map_len(rows):
    """Tile-map length in bytes for ``rows`` 16px tile rows."""
    return COLS * tile_rows(rows)


# One margin unit is one 8x8 tile cell (8 pixels). The margin is added on the
# left and right only; the picture is scaled uniformly to fit the inner width.
MARGIN_CELL = 8

# `text_bg` colour token -> Spectrum ink index (attribute colour order).
_BG_INDEX = {"black": 0, "blue": 1, "red": 2, "magenta": 3, "green": 4,
             "cyan": 5, "yellow": 6, "white": 7}


def _margin_px(margin, band_width):
    """Pixels per side for a margin in 8x8 cells, clamped to the band width."""
    try:
        cells = max(0, int(margin))
    except (TypeError, ValueError):
        cells = 0
    return min(cells * MARGIN_CELL, max(0, int(band_width) // 2 - 1))


def _margin_rect(margin, band_width, band_height):
    """``(left, top, right, bottom)`` bars for a scaled side margin."""
    px = _margin_px(margin, band_width)
    if px <= 0:
        return 0, 0, 0, 0
    inner_w = max(1, band_width - 2 * px)
    inner_h = max(1, int(round(band_height * inner_w / float(band_width))))
    top = (band_height - inner_h) // 2
    bottom = band_height - inner_h - top
    return px, top, px, bottom


def preview_margin_crop(im, margin=0, band_width=BAND_W, band_height=None):
    """Crop the blank bars off a rendered preview image.

    Previews show the picture that sits inside the margins, not the border (or
    the small vertical gap left by keeping its aspect ratio). ``band_width``
    and ``band_height`` are the converter's internal band dimensions; the
    preview may have been scaled (e.g. the C64's 320-pixel preview of a
    160-pixel band), so each side is scaled by the output's actual size.
    """
    if band_height is None:
        band_height = im.height
    left, top, right, bottom = _margin_rect(margin, band_width, band_height)
    if not (left or top or right or bottom):
        return im
    sx = im.width / float(band_width)
    sy = im.height / float(band_height)
    x0 = int(round(left * sx))
    x1 = im.width - int(round(right * sx))
    y0 = int(round(top * sy))
    y1 = im.height - int(round(bottom * sy))
    if x1 <= x0 or y1 <= y0:
        return im
    return im.crop((x0, y0, x1, y1))


def background_rgb(game=None):
    """Resolve a game's ``text_bg`` token to an exact Spectrum RGB triple."""
    import scenefile
    token = scenefile.text_tokens(game)[2]
    dim = token.startswith("dim_")
    name = token[4:] if dim else token
    return SPEC[_BG_INDEX.get(name, 0) + (0 if dim else 8)]


def inset_band(im, margin=0, fill=(0, 0, 0)):
    """Add background bars on the left and right sides of ``im``.

    ``margin`` is in 8x8 cells (0 leaves the band untouched). The picture is
    scaled uniformly to the narrower inner width (preserving its aspect) and
    centred vertically; any small vertical remainder is filled with ``fill``.
    Applied after source adjustments but before quantisation, so a margin-0
    band is unchanged.
    """
    from PIL import Image

    px = _margin_px(margin, im.width)
    if px <= 0:
        return im
    w, h = im.size
    inner_w = max(1, w - 2 * px)
    inner_h = max(1, int(round(h * inner_w / float(w))))
    content = im.resize((inner_w, inner_h), Image.LANCZOS)
    out = Image.new("RGB", (w, h), tuple(fill))
    out.paste(content, (px, (h - inner_h) // 2))
    return out

# Selectable dithering schemes shared by every colour converter. After a
# palette or cell's colours are fixed, a pointwise scheme inks each pixel when
# its ink fraction db/(da+db) exceeds a threshold at its absolute (x,y); an
# error-diffusion scheme instead diffuses each pixel's error to its
# not-yet-visited neighbours. `off` is the hard nearest-colour snap and the
# default. See ``dither_grid`` and ``nirvana_band``.
#   bayer2   - 2x2 ordered (Bayer): coarsest, chunkiest texture
#   bayer4   - 4x4 ordered (Bayer): visible fine texture
#   bayer8   - 8x8 ordered (Bayer): finer gradients, slightly stronger texture
#   noise    - fixed white noise: smooth gradients, no ordered pattern, grainier
#   floyd    - Floyd-Steinberg error diffusion: smoothest, but may raise the
#              unique-tile count (watch the paged-bank budget)
#   atkinson - Atkinson: diffuses only 6/8 of the error, higher contrast / crisp
#   jarvis   - Jarvis-Judice-Ninke: 3-row diffusion, very smooth
#   stucki   - Stucki: like Jarvis with lighter weights, a little crisper
#   sierra   - Sierra (3-line): smooth, lighter than Jarvis
DITHER_MODES = ("off", "bayer2", "bayer4", "bayer8", "noise", "floyd",
                "atkinson", "jarvis", "stucki", "sierra")
DEFAULT_DITHER = "off"
# A 1-bit monochrome screen has no mid-tone, so `off` would hard-threshold the
# luminance and throw the shading away. Monochrome converters substitute this
# ordered scheme when the resolved mode is `off`; an explicit scheme still
# applies. The coarsest ordered matrix packs best in the resident blobs; error
# diffusion can overflow the Oric's tight memory.
DEFAULT_MONO_DITHER = "bayer2"

# Error-diffusion kernels sharing one table: (divisor, [(dx, dy, weight)]).
# The tap order matters for exact numpy/pure-Python parity; ``floyd`` keeps the
# original tap order so existing art is unchanged. ``atkinson`` disperses only
# 6/8 of the error (divisor 8), which raises contrast.
_DIFFUSE = {
    "floyd": (16, [(1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)]),
    "atkinson": (8, [(1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1),
                     (1, 1, 1), (0, 2, 1)]),
    "jarvis": (48, [(1, 0, 7), (2, 0, 5),
                    (-2, 1, 3), (-1, 1, 5), (0, 1, 7), (1, 1, 5), (2, 1, 3),
                    (-2, 2, 1), (-1, 2, 3), (0, 2, 5), (1, 2, 3), (2, 2, 1)]),
    "stucki": (42, [(1, 0, 8), (2, 0, 4),
                    (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4), (2, 1, 2),
                    (-2, 2, 1), (-1, 2, 2), (0, 2, 4), (1, 2, 2), (2, 2, 1)]),
    "sierra": (32, [(1, 0, 5), (2, 0, 3),
                    (-2, 1, 2), (-1, 1, 4), (0, 1, 5), (1, 1, 4), (2, 1, 2),
                    (-1, 2, 2), (0, 2, 3), (1, 2, 2)]),
}
DIFFUSE_MODES = tuple(_DIFFUSE)

# How the cell search / pixel snap measures the distance between a source pixel
# and a Spectrum colour. ``rgb`` is the plain squared RGB error (default,
# unchanged); ``perceptual`` is the integer "redmean" approximation, which
# weights the red and blue terms by the pair's mean red so hues the eye reads
# as more different cost more.
MATCH_MODES = ("rgb", "perceptual")
DEFAULT_MATCH = "rgb"

# Optional source-palette pre-reduction before the cell search. ``none``
# (default) feeds the scaled source straight in; ``spectrum`` snaps every pixel
# to the nearest of the 16 Spectrum colours first; ``adaptive`` median-cuts the
# source to ``palette_colors`` colours. It changes nothing about the 48-byte
# tile encoding -- only which colours the search sees.
PALETTE_MODES = ("none", "spectrum", "adaptive")
DEFAULT_PALETTE = "none"
DEFAULT_PALETTE_COLORS = 16

# A crop is a rectangle of the source, given as four percentages
# ``[x, y, w, h]`` (0..100) of the source dimensions. ``None`` (the default)
# uses the largest band-aspect window, centred: the whole frame for a source
# that already matches the 256x80 3.2:1 band, otherwise a full-width or
# full-height strip. The editor's resizable box keeps the 3.2:1 aspect, so the
# cropped region scales to the band undistorted. Baked at conversion time, so
# this is purely a build/editor setting (per `# Art`).
DEFAULT_CROP = None

# Ordered dither thresholds in [0,1); a larger matrix resolves finer gradients.
BAYER2 = [[(v + 0.5) / 4.0 for v in row] for row in (
    (0, 2),
    (3, 1),
)]
BAYER4 = [[(v + 0.5) / 16.0 for v in row] for row in (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)]
BAYER8 = [[(v + 0.5) / 64.0 for v in row] for row in (
    (0, 32, 8, 40, 2, 34, 10, 42),
    (48, 16, 56, 24, 50, 18, 58, 26),
    (12, 44, 4, 36, 14, 46, 6, 38),
    (60, 28, 52, 20, 62, 30, 54, 22),
    (3, 35, 11, 43, 1, 33, 9, 41),
    (51, 19, 59, 27, 49, 17, 57, 25),
    (15, 47, 7, 39, 13, 45, 5, 37),
    (63, 31, 55, 23, 61, 29, 53, 21),
)]


def dither_mode(d):
    """Normalise a dither request (bool legacy or mode string) to a mode name.

    ``True``/``None`` select the default, ``False`` is the hard snap (``off``),
    an unknown string falls back to the default.
    """
    if d is False:
        return "off"
    if d is True or d is None:
        return DEFAULT_DITHER
    return d if d in DITHER_MODES else DEFAULT_DITHER


def mono_dither(d):
    """Normalise a dither request for a 1-bit target, never returning ``off``.

    A monochrome picture needs dithering to resolve tones above two levels, so
    ``off`` (the default) becomes ``DEFAULT_MONO_DITHER``.
    """
    mode = dither_mode(d)
    return DEFAULT_MONO_DITHER if mode == "off" else mode


def _noise_value(x, y):
    """Deterministic white-noise sample in [0,1) for pixel (x, y)."""
    h = (x * 0x1f1f1f1f) ^ (y * 0x3b9aca07) ^ 0x9e3779b9
    h &= 0xffffffff
    h ^= h >> 15
    h = (h * 0x2545f491) & 0xffffffff
    h ^= h >> 13
    return (h & 0xffffff) / float(0x1000000)


def threshold_at(mode, x, y):
    """Dither threshold in [0,1) at absolute pixel ``(x, y)``.

    Ordered modes tile their matrix across the image; ``noise`` uses a fixed
    pseudo-random field.
    """
    if mode == "noise":
        return _noise_value(x, y)
    m = {"bayer2": BAYER2, "bayer8": BAYER8}.get(mode, BAYER4)
    n = len(m)
    return m[y % n][x % n]


_THRESH_CACHE = {}


def _threshold_grid(mode, rows=None):
    """A band-height x BAND_W nested list of dither thresholds, or None for ``off``.

    Ordered modes tile their matrix across the band; ``noise`` uses a fixed
    pseudo-random field. The full-size grid keeps the numpy and pure-Python
    paths byte-for-byte identical without duplicating the hash arithmetic.
    """
    if mode == "off" or mode in _DIFFUSE:   # not pointwise threshold schemes
        return None
    h = band_h(rows)
    key = (mode, h)
    if key in _THRESH_CACHE:
        return _THRESH_CACHE[key]
    grid = [[threshold_at(mode, x, y) for x in range(BAND_W)]
            for y in range(h)]
    _THRESH_CACHE[key] = grid
    return grid


def rgb(i):
    return SPEC[i]


def crop_rect(crop, w, h, rows=None, width=BAND_W):
    """Resolve a crop spec to source pixel bounds ``(x0, y0, x1, y1)``.

    ``crop`` is ``None`` (the band-aspect window of the source, centred) or a
    four-item ``[x, y, w, h]`` of percentages of the source dimensions. ``rows``
    is the band height in 16px tile rows (default the 256x80 band's 5), which
    sets the window aspect; ``width`` is the band width in pixels (default the
    Spectrum's 256). The result is clamped to the image so a hand-written
    or stale value can never produce an empty or out-of-bounds crop.
    """
    if not crop:
        ar = width / band_h(rows)
        if w / h > ar:                    # source wider than the band
            cw, ch = h * ar, h
        else:                             # source taller than the band
            cw, ch = w, w / ar
        x = (w - cw) / 2.0
        y = (h - ch) / 2.0
    else:
        px, py, pw, ph = (float(t) for t in crop)
        x, y = px / 100.0 * w, py / 100.0 * h
        cw, ch = pw / 100.0 * w, ph / 100.0 * h
    x0 = max(0, min(w - 1, int(round(x))))
    y0 = max(0, min(h - 1, int(round(y))))
    x1 = max(x0 + 1, min(w, int(round(x + cw))))
    y1 = max(y0 + 1, min(h, int(round(y + ch))))
    return x0, y0, x1, y1


def band_crop_rect(crop, w, h, aspect):
    """Resolve an art crop to a target-aspect source rect at full width.

    Used by the non-ZX targets, whose band aspect differs from the ZX crop
    box's. ``crop`` is ``None`` (a centred target-aspect window, which fills
    the band) or an explicit ``[x, y, w, h]`` percentage rectangle. An
    explicit rectangle keeps its full width and x; its height is re-centred
    and scaled to ``aspect`` (width/height) around the rectangle's centre,
    clamped to the source. Only when the source cannot provide enough height
    does it fall back to the full source height and a narrower width. The
    crop is therefore never stretched or cropped sideways in normal use.
    """
    aspect = float(aspect)
    if aspect <= 0:
        aspect = 1.0
    if crop:
        x0, y0, x1, y1 = crop_rect(crop, w, h)
        cw = max(1, x1 - x0)
        ch = cw / aspect
        if ch <= h:
            nh = max(1, min(h, int(round(ch))))
            cy = (y0 + y1) / 2.0
            ny0 = int(round(cy - nh / 2.0))
            ny0 = max(0, min(h - nh, ny0))
            return x0, ny0, x1, ny0 + nh
        nw = max(1, min(w, int(round(h * aspect))))
        cx = (x0 + x1) / 2.0
        nx0 = int(round(cx - nw / 2.0))
        nx0 = max(0, min(w - nw, nx0))
        return nx0, 0, nx0 + nw, h
    if w / float(h) > aspect:
        cw, ch = h * aspect, h
    else:
        cw, ch = w, w / aspect
    x = (w - cw) / 2.0
    y = (h - ch) / 2.0
    x0 = max(0, min(w - 1, int(round(x))))
    y0 = max(0, min(h - 1, int(round(y))))
    x1 = max(x0 + 1, min(w, int(round(x + cw))))
    y1 = max(y0 + 1, min(h, int(round(y + ch))))
    return x0, y0, x1, y1


def crop_for_band(im, crop, rows=None, width=BAND_W):
    """Crop an explicit art rectangle to the target band aspect.

    Unlike ``_fit_band`` this never stretches a mismatched crop: the width and
    x are kept and the height is re-centred to the band aspect (clamped to the
    source), exactly like the non-ZX converters use ``band_crop_rect``. It lets
    a crop authored for the 128K band be reused by a 48K band of another height.
    """
    if not crop:
        return im
    w, h = im.size
    box = band_crop_rect(crop, w, h, width / float(band_h(rows)))
    return im.crop(box)


def _fit_band(im, crop=None, rows=None):
    """Return the source cropped to its ``crop`` rectangle, scaled to the band.

    The rectangle (see ``crop_rect``) is scaled to 256px by ``16*rows`` with
    LANCZOS. Because the editor's box keeps the band aspect, the result is
    undistorted; a hand-authored rectangle of another aspect is stretched to
    fit.
    """
    from PIL import Image
    w, h = im.size
    if w and h:
        box = im.crop(crop_rect(crop, w, h, rows))
    else:
        box = im
    target = (BAND_W, band_h(rows))
    if box.size != target:
        return box.resize(target, Image.LANCZOS)
    return box


def _dist_py(c, ref, match=DEFAULT_MATCH):
    """Squared colour distance for two 3-tuples (pure-Python path).

    ``rgb`` is the plain sum of squared channel differences; ``perceptual`` is
    the integer "redmean" formula. The same arithmetic is used by the numpy
    path so the two stay byte-for-byte identical.
    """
    dr = c[0] - ref[0]
    dg = c[1] - ref[1]
    db = c[2] - ref[2]
    if match == "perceptual":
        rmean = (c[0] + ref[0]) // 2
        return (((512 + rmean) * dr * dr) / 256 + 4 * dg * dg
                + ((767 - rmean) * db * db) / 256)
    return dr * dr + dg * dg + db * db


def _dist_rgb(a, b, match=DEFAULT_MATCH):
    """``_dist_py`` over numpy arrays whose last axis is the 3 channels.

    ``a``/``b`` broadcast to a common shape; the result drops that last axis.
    Integer inputs keep the ``rgb`` result integral; ``perceptual`` is float,
    matching ``_dist_py``.
    """
    dr = a[..., 0] - b[..., 0]
    dg = a[..., 1] - b[..., 1]
    db = a[..., 2] - b[..., 2]
    if match == "perceptual":
        rmean = (a[..., 0] + b[..., 0]) // 2
        return (((512 + rmean) * dr * dr) / 256 + 4 * dg * dg
                + ((767 - rmean) * db * db) / 256)
    return dr * dr + dg * dg + db * db


def preprocess(im, saturation=1.0, contrast=1.0, brightness=1.0, gamma=1.0):
    """Apply optional source colour adjustments before quantisation.

    Saturation/contrast/brightness use PIL's enhancers (1.0 = unchanged); gamma
    is a ``1/gamma`` power curve. Raising them pushes muted AI art closer to
    the Spectrum's flat, saturated palette, so less colour is lost in the cell
    search. Applied to the already-scaled band, so it is deterministic and
    shared by the numpy and pure-Python paths.
    """
    from PIL import Image, ImageEnhance
    if saturation != 1.0:
        im = ImageEnhance.Color(im).enhance(saturation)
    if contrast != 1.0:
        im = ImageEnhance.Contrast(im).enhance(contrast)
    if brightness != 1.0:
        im = ImageEnhance.Brightness(im).enhance(brightness)
    if gamma != 1.0:
        inv = 1.0 / gamma
        lut = [max(0, min(255, int(round(255.0 * ((i / 255.0) ** inv)))))
               for i in range(256)]
        im = im.point(lut * 3 if im.mode == "RGB" else lut)
    return im


def _apply_palette(im, mode=DEFAULT_PALETTE, colors=None):
    """Optionally reduce ``im`` to a fixed palette before the cell search.

    ``spectrum`` snaps every pixel to the nearest of the 16 Spectrum colours;
    ``adaptive`` median-cuts to ``colors`` colours. PIL does the mapping, so the
    numpy and pure-Python paths see the identical reduced image.
    """
    from PIL import Image
    if mode == "spectrum":
        pal = Image.new("P", (1, 1))
        flat = [c for rgb_ in SPEC for c in rgb_]
        pal.putpalette(flat + [0] * (768 - len(flat)))
        return im.quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")
    if mode == "adaptive":
        n = int(colors or DEFAULT_PALETTE_COLORS)
        n = max(2, min(256, n))
        return im.quantize(colors=n, method=Image.Quantize.MEDIANCUT,
                           dither=Image.Dither.NONE).convert("RGB")
    return im


def _prepare_band(im, crop, rows, adjust, palette, palette_colors,
                  margin=0, fill=(0, 0, 0)):
    """Fit to the band, adjust, inset by the margin, then reduce the palette."""
    im = _fit_band(im, crop, rows)
    a = adjust or {}
    im = preprocess(im, a.get("saturation", 1.0), a.get("contrast", 1.0),
                    a.get("brightness", 1.0), a.get("gamma", 1.0))
    im = inset_band(im, margin, fill)
    return _apply_palette(im, palette or DEFAULT_PALETTE, palette_colors)


def mono_band(im, crop=None, dither=DEFAULT_DITHER, rows=None, *,
              adjust=None, palette=DEFAULT_PALETTE, palette_colors=None,
              margin=0, fill=(0, 0, 0), **_ignored):
    """Convert an image to a packed 1bpp monochrome band.

    The source is fitted, colour-adjusted and palette-reduced like the colour
    converters, then reduced to luminance and dithered. The band is BAND_W x
    ``16*rows`` pixels (the same geometry as a NIRVANA+ band), packed row-major
    with the most significant bit leftmost. ``off`` becomes the ordered
    ``DEFAULT_MONO_DITHER`` (see ``mono_dither``); ordered and error-diffusion
    schemes share the colour converters' tables.
    """
    im = _prepare_band(im, crop, rows, adjust, palette, palette_colors,
                       margin, fill)
    gray = im.convert("L")
    w, h = gray.size
    px = gray.load()
    mode = mono_dither(dither)
    bits = bytearray((w * h + 7) // 8)
    if mode in _DIFFUSE:
        err = [[float(px[x, y]) for x in range(w)] for y in range(h)]
        wdiv, taps = _DIFFUSE[mode]
        for y in range(h):
            for x in range(w):
                value = err[y][x]
                ink = 255 if value >= 128 else 0
                if ink:
                    i = y * w + x
                    bits[i >> 3] |= 1 << (7 - (i & 7))
                delta = value - ink
                for dx, dy, weight in taps:
                    x2, y2 = x + dx, y + dy
                    if 0 <= x2 < w and 0 <= y2 < h:
                        err[y2][x2] += delta * weight / wdiv
        return bytes(bits)
    grid = _threshold_grid(mode, rows)
    for y in range(h):
        row = grid[y]
        for x in range(w):
            if px[x, y] / 255.0 > row[x]:
                i = y * w + x
                bits[i >> 3] |= 1 << (7 - (i & 7))
    return bytes(bits)


def mono_image(im, crop=None, dither=DEFAULT_DITHER, rows=None, *,
               adjust=None, palette=DEFAULT_PALETTE, palette_colors=None,
               margin=0, fill=(0, 0, 0)):
    """Render ``mono_band`` as a black/white RGB image for editor previews."""
    from PIL import Image
    data = mono_band(im, crop=crop, dither=dither, rows=rows, adjust=adjust,
                     palette=palette, palette_colors=palette_colors,
                     margin=margin, fill=fill)
    h, w = band_h(rows), BAND_W
    img = Image.new("RGB", (w, h), (0, 0, 0))
    px = img.load()
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if data[i >> 3] & (1 << (7 - (i & 7))):
                px[x, y] = (255, 255, 255)
    return img


def to_mono_image(im, dither=DEFAULT_DITHER):
    """Reduce an already-fitted RGB image to a dithered black/white image.

    Unlike ``mono_band`` (which fits a source to the Spectrum's 256x16*rows
    band) this keeps the caller's dimensions, so every target's converter can
    apply the Black and white system option after its own crop/scale/margin.
    """
    from PIL import Image
    gray = im.convert("L")
    w, h = gray.size
    src = gray.load()
    out = Image.new("RGB", (w, h))
    dst = out.load()
    mode = mono_dither(dither)
    if mode in _DIFFUSE:
        err = [[float(src[x, y]) for x in range(w)] for y in range(h)]
        wdiv, taps = _DIFFUSE[mode]
        for y in range(h):
            for x in range(w):
                value = err[y][x]
                white = value >= 128.0
                dst[x, y] = (255, 255, 255) if white else (0, 0, 0)
                delta = value - (255.0 if white else 0.0)
                for dx, dy, weight in taps:
                    x2, y2 = x + dx, y + dy
                    if 0 <= x2 < w and 0 <= y2 < h:
                        err[y2][x2] += delta * weight / wdiv
        return out
    matrix = {"bayer2": BAYER2, "bayer8": BAYER8}.get(mode, BAYER4)
    n = len(matrix)
    for y in range(h):
        for x in range(w):
            threshold = (_noise_value(x, y) if mode == "noise"
                         else matrix[y % n][x % n])
            dst[x, y] = ((255, 255, 255)
                         if src[x, y] / 255.0 > threshold else (0, 0, 0))
    return out


def _quant_image(im):
    """Nearest-Spectrum-colour grid for an already prepared band image."""
    grid = []
    px = im.load()
    w, h = im.size
    for y in range(h):
        row = []
        for x in range(w):
            r, g, b = px[x, y]
            best, bd = 0, 1 << 30
            for k, (pr, pg, pb) in enumerate(SPEC):
                d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
                if d < bd:
                    bd, best = d, k
            row.append(best)
        grid.append(row)
    return grid


def quant(im, crop=None, rows=None, adjust=None, palette=DEFAULT_PALETTE,
          palette_colors=None, margin=0, fill=(0, 0, 0)):
    """Quantise a PIL image to a BAND_W x band-height grid of SPEC indices.

    The source is cropped to its ``crop`` rectangle (``None`` = the centred
    band-aspect window), scaled to the band (``rows`` 16px tile rows; default
    5 = 256x80) and optionally colour-adjusted / palette-reduced. See
    ``_fit_band`` and ``_prepare_band``.
    """
    return _quant_image(_prepare_band(im, crop, rows, adjust, palette,
                                      palette_colors, margin, fill))


def _nearest_rgb(color, palette, match=DEFAULT_MATCH):
    """Index of the nearest RGB colour in ``palette``."""
    best, bestd = 0, None
    for k, ref in enumerate(palette):
        d = _dist_py(color, ref, match)
        if bestd is None or d < bestd:
            best, bestd = k, d
    return best


def _two_nearest_rgb(color, palette, match=DEFAULT_MATCH):
    """Two nearest distinct colours: ``(ia, ib, da, db)``."""
    ia = ib = 0
    da = db = None
    for k, ref in enumerate(palette):
        if da is not None and ref == palette[ia]:
            continue
        d = _dist_py(color, ref, match)
        if da is None or d < da:
            db, ib = da, ia
            da, ia = d, k
        elif db is None or d < db:
            db, ib = d, k
    if db is None:
        return ia, ia, da or 0.0, da or 0.0
    return ia, ib, da, db


def _dither_python(im, palette, mode, match):
    w, h = im.size
    px = im.load()
    out = [0] * (w * h)
    fixed = not callable(palette)
    if mode in _DIFFUSE:
        err = [[list(px[x, y]) for x in range(w)] for y in range(h)]
        wdiv, taps = _DIFFUSE[mode]
        for y in range(h):
            for x in range(w):
                pal = palette if fixed else palette(x, y)
                value = err[y][x]
                k = _nearest_rgb(value, pal, match)
                out[y * w + x] = k
                kr, kg, kb = pal[k]
                er, eg, eb = value[0] - kr, value[1] - kg, value[2] - kb
                for ox, oy, wgt in taps:
                    x2, y2 = x + ox, y + oy
                    if 0 <= x2 < w and 0 <= y2 < h:
                        q = err[y2][x2]
                        q[0] += er * wgt / wdiv
                        q[1] += eg * wgt / wdiv
                        q[2] += eb * wgt / wdiv
        return out
    for y in range(h):
        for x in range(w):
            pal = palette if fixed else palette(x, y)
            color = px[x, y]
            if mode == "off":
                out[y * w + x] = _nearest_rgb(color, pal, match)
                continue
            ia, ib, da, db = _two_nearest_rgb(color, pal, match)
            total = da + db
            frac = db / total if total else 0.5
            out[y * w + x] = ib if frac > threshold_at(mode, x, y) else ia
    return out


def _dither_fixed_numpy(im, palette, mode, match, np):
    px = np.asarray(im, dtype=np.int32)
    h, w, _ = px.shape
    # Pointwise schemes choose between the two nearest distinct colours, so
    # duplicated palette entries are collapsed first (the first index wins).
    seen = {}
    unique = []
    unique_index = []
    for i, color in enumerate(palette):
        key = tuple(int(v) for v in color)
        if key not in seen:
            seen[key] = len(unique)
            unique.append(key)
            unique_index.append(i)
    upal = np.asarray(unique, dtype=np.int32)
    if mode in _DIFFUSE:
        err = px.astype(np.float64)
        out = np.empty((h, w), dtype=np.intp)
        wdiv, taps = _DIFFUSE[mode]
        pal = np.asarray(palette, dtype=np.float64)
        for y in range(h):
            for x in range(w):
                value = err[y, x]
                k = int(np.argmin(((pal - value) ** 2).sum(axis=1)))
                out[y, x] = k
                delta = value - pal[k]
                for ox, oy, wgt in taps:
                    x2, y2 = x + ox, y + oy
                    if 0 <= x2 < w and 0 <= y2 < h:
                        err[y2, x2] += delta * (wgt / wdiv)
        return out.ravel().tolist()
    best_d = np.full((h, w), 1 << 30, dtype=np.int32)
    best_i = np.zeros((h, w), dtype=np.intp)
    second_d = np.full((h, w), 1 << 30, dtype=np.int32)
    second_i = np.zeros((h, w), dtype=np.intp)
    for k, ref in enumerate(upal):
        d = ((px - ref) ** 2).sum(axis=2)
        better = d < best_d
        second_d[better] = best_d[better]
        second_i[better] = best_i[better]
        best_d[better] = d[better]
        best_i[better] = k
        other = (~better) & (d < second_d)
        second_d[other] = d[other]
        second_i[other] = k
    if mode == "off":
        chosen = best_i
    else:
        thr = np.empty((h, w), dtype=np.float64)
        for y in range(h):
            for x in range(w):
                thr[y, x] = threshold_at(mode, x, y)
        total = best_d.astype(np.float64) + second_d.astype(np.float64)
        frac = np.where(total > 0,
                        second_d.astype(np.float64) / np.maximum(total, 1.0),
                        0.5)
        chosen = np.where(frac > thr, second_i, best_i)
    mapping = np.asarray(unique_index, dtype=np.intp)
    return mapping[chosen].ravel().tolist()


def dither_grid(im, palette, dither=DEFAULT_DITHER, match=DEFAULT_MATCH):
    """Map an RGB image to palette indices with ``dither``.

    ``palette`` is a sequence of RGB colours or a callable ``(x, y)`` returning
    the palette allowed at that pixel (for attribute cells, tiles or blocks).
    ``off`` snaps to the nearest colour; ordered/noise schemes choose between
    the two nearest distinct colours by the ink fraction ``db/(da+db)``; the
    error-diffusion kernels raster the whole image with the shared ``_DIFFUSE``
    tables. Returns a flat row-major list of indices.
    """
    mode = dither_mode(dither)
    if callable(palette):
        return _dither_python(im, palette, mode, match)
    palette = [tuple(int(v) for v in color) for color in palette]
    try:
        import numpy as np
    except ImportError:
        return _dither_python(im, palette, mode, match)
    return _dither_fixed_numpy(im, palette, mode, match, np)


def nirvana_band(im, crop=None, dither=DEFAULT_DITHER, rows=None, *,
                 match=DEFAULT_MATCH, adjust=None, palette=DEFAULT_PALETTE,
                 palette_colors=None, margin=0, fill=(0, 0, 0)):
    """Quantise to a BAND grid with cell-exact NIRVANA+ bicolor attributes.

    Unlike ``quant()``, which snaps every pixel to its nearest Spectrum colour
    in isolation and only then picks ink/paper per 8x2 cell, this chooses each
    cell's two colours by an exhaustive search over all 64 (ink,paper) pairs
    drawn from a single bright bank, minimising the total error of the 16 source
    pixels against the nearer of the two. Both colours therefore share the
    cell's BRIGHT bit, so the 48-byte btile encoding stays valid.

    ``crop`` is the source rectangle (``[x, y, w, h]`` percentages, or ``None``
    for the centred band-aspect window; see ``crop_rect``). ``rows`` is the band
    height in 16px tile rows (default 5 = 256x80). ``dither`` selects how each
    pixel is assigned to the cell's two colours (see ``DITHER_MODES``): ``"off"``
    (default) hard-snaps to the nearer colour; the ordered modes ``"bayer2"``,
    ``"bayer4"`` and ``"bayer8"``, plus ``"noise"``, are pointwise schemes inked
    where the ink fraction db/(da+db) exceeds a threshold; ``"floyd"`` and the
    other ``DIFFUSE_MODES`` diffuse the RGB error.

    ``match`` picks the colour-distance metric (``MATCH_MODES``); ``adjust`` is
    an optional ``{"saturation","contrast","brightness","gamma"}`` dict applied
    to the source before quantisation; ``palette``/``palette_colors`` optionally
    pre-reduce the source (``PALETTE_MODES``). All are baked in, so the engine
    carries no conversion state. Returns a band-height x BAND_W grid of SPEC
    indices.
    """
    im = _prepare_band(im, crop, rows, adjust, palette, palette_colors,
                       margin, fill)
    mode = dither_mode(dither)
    match = match if match in MATCH_MODES else DEFAULT_MATCH
    try:
        import numpy as np
    except ImportError:
        return _nirvana_band_python(im, mode, rows, match)
    return _nirvana_band_numpy(im, np, mode, rows, match)


def _nirvana_band_numpy(im, np, mode=DEFAULT_DITHER, rows=None,
                        match=DEFAULT_MATCH):
    px = np.asarray(im, dtype=np.int32)
    h, w, _ = px.shape
    cr, cc = h // 2, w // 8                     # attribute cell rows/cols
    # (CR,2,CC,8,3) -> (N,16,3): each cell's 16 pixels in dy-major order.
    cells = px.reshape(cr, 2, cc, 8, 3).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 3)
    n = cells.shape[0]
    spec = np.asarray(SPEC, dtype=np.int32)
    best_cost = np.full(n, 1 << 30, dtype=np.float64)
    best = np.zeros((n, 2), dtype=np.intp)      # absolute SPEC indices (ink, paper)
    for bank in (0, 1):
        off = 8 if bank else 0
        pal = spec[off:off + 8]
        # (n,16,8): distance from each cell pixel to each pair colour.
        dist = _dist_rgb(cells[:, :, None, :], pal[None, None, :, :], match)
        for a in range(8):
            da = dist[:, :, a]
            for b in range(8):
                cost = np.minimum(da, dist[:, :, b]).sum(1)
                m = cost < best_cost
                if m.any():
                    best_cost[m] = cost[m]
                    best[m, 0] = off + a
                    best[m, 1] = off + b
    ia, ib = best[:, 0], best[:, 1]
    da = _dist_rgb(cells, spec[ia][:, None, :], match)
    db = _dist_rgb(cells, spec[ib][:, None, :], match)
    if mode in DIFFUSE_MODES:
        # Error diffusion over the whole band: diffuse each pixel's RGB error to
        # its not-yet-visited neighbours, snapping to the cell's chosen pair.
        out = px.astype(np.float64).copy()
        chosen = np.empty((n, 16), dtype=np.intp)
        wdiv, taps = _DIFFUSE[mode]
        for cy in range(cr):
            for cx in range(cc):
                ci = cy * cc + cx
                iaa, ibb = int(ia[ci]), int(ib[ci])
                ca = spec[iaa].astype(np.float64)
                cb = spec[ibb].astype(np.float64)
                for dy in range(2):
                    y = cy * 2 + dy
                    for dx in range(8):
                        x = cx * 8 + dx
                        v = out[y, x]
                        k = (iaa if _dist_rgb(v, ca, match)
                             <= _dist_rgb(v, cb, match) else ibb)
                        chosen[ci, dy * 8 + dx] = k
                        err = v - spec[k]
                        for ox, oy, wgt in taps:
                            x2, y2 = x + ox, y + oy
                            if 0 <= x2 < w and 0 <= y2 < h:
                                out[y2, x2] += err * (wgt / wdiv)
    elif mode == "off":
        chosen = np.where(da <= db, ia[:, None], ib[:, None])   # (n,16)
    else:
        # Pointwise dither within the cell's two colours: ink where the ink
        # fraction db/(da+db) beats the threshold at the pixel's position.
        idx = np.arange(n)
        yy = (idx // cc)[:, None] * 2 + (np.arange(16) // 8)[None, :]
        xx = (idx % cc)[:, None] * 8 + (np.arange(16) % 8)[None, :]
        thr = np.asarray(_threshold_grid(mode, rows))[yy, xx]     # (n,16)
        tot = da + db
        frac = np.where(tot > 0, db / np.maximum(tot, 1), 0.5)    # ink fraction
        chosen = np.where(frac > thr, ia[:, None], ib[:, None])  # (n,16)
    grid = chosen.reshape(cr, cc, 2, 8).transpose(0, 2, 1, 3).reshape(h, w)
    return grid.tolist()


def _nirvana_band_python(im, mode=DEFAULT_DITHER, rows=None,
                         match=DEFAULT_MATCH):
    px = im.load()
    spec = SPEC
    bw, bh = im.size
    out = [[0] * bw for _ in range(bh)]
    thresh = _threshold_grid(mode, rows)     # None for "off"/diffusion modes
    kernel = _DIFFUSE.get(mode)              # (divisor, taps) or None
    if kernel:
        err = [[list(px[x, y]) for x in range(bw)] for y in range(bh)]
    for cy in range(bh // 2):                     # cell rows (2px tall)
        for cx in range(bw // 8):                 # cell cols (8px wide)
            cell = [px[cx * 8 + dx, cy * 2 + dy]
                    for dy in range(2) for dx in range(8)]
            best = None
            for bank in (0, 1):
                off = 8 if bank else 0
                pal = spec[off:off + 8]
                dist = [[_dist_py(cell[p], pal[k], match) for k in range(8)]
                        for p in range(16)]
                for a in range(8):
                    for b in range(8):
                        e = 0
                        for p in range(16):
                            da, db = dist[p][a], dist[p][b]
                            e += da if da <= db else db
                        if best is None or e < best[0]:
                            best = (e, off, a, b)
            _, off, a, b = best
            ra, rb = spec[off + a], spec[off + b]
            ia, ib = off + a, off + b
            for p in range(16):
                dy, dx = p // 8, p % 8
                yy, xx = cy * 2 + dy, cx * 8 + dx
                if kernel:
                    r, g, bl = err[yy][xx]
                else:
                    r, g, bl = cell[p]
                da = _dist_py((r, g, bl), ra, match)
                db = _dist_py((r, g, bl), rb, match)
                if kernel:
                    k = ia if da <= db else ib
                    out[yy][xx] = k
                    kr, kg, kb = spec[k]
                    er, eg, eb = r - kr, g - kg, bl - kb
                    wdiv, taps = kernel
                    for ox, oy, wgt in taps:
                        x2, y2 = xx + ox, yy + oy
                        if 0 <= x2 < bw and 0 <= y2 < bh:
                            q = err[y2][x2]
                            q[0] += er * wgt / wdiv
                            q[1] += eg * wgt / wdiv
                            q[2] += eb * wgt / wdiv
                else:
                    if mode == "off":
                        use_ink = da <= db
                    else:
                        tot = da + db
                        frac = db / tot if tot else 0.5
                        use_ink = frac > thresh[yy][xx]
                    out[yy][xx] = ia if use_ink else ib
    return out


def btile(grid, x0, y0):
    """48-byte 16x16 bicolor tile at (x0, y0)."""
    bmp = bytearray(32)
    atr = bytearray(16)
    for pp in range(8):                     # 8 attr line-pairs
        for col in range(2):                # two 8px columns per attr byte
            xb = x0 + col * 8
            counts = {}
            for y in (y0 + pp * 2, y0 + pp * 2 + 1):
                for x in range(xb, xb + 8):
                    v = grid[y][x]
                    counts[v] = counts.get(v, 0) + 1
            if not counts:
                atr[col * 8 + pp] = 0
                continue
            items = sorted(counts.items(), key=lambda kv: (sum(rgb(kv[0])), -kv[1]))
            ink, paper = items[0][0], items[-1][0]
            bright = 0x40 if (ink > 7 or paper > 7) else 0
            atr[col * 8 + pp] = (ink & 7) | ((paper & 7) << 3) | bright
            ink_rgb = rgb(ink)
            for row in range(2):
                r = y0 + pp * 2 + row
                b = 0
                for i in range(8):
                    b = (b << 1) | (1 if rgb(grid[r][xb + i]) == ink_rgb else 0)
                bmp[(pp * 2 + row) * 2 + col] = b
    return bytes(bmp + atr)


def tile_to_rgb(t, out):
    """Paint a 48-byte btile into `out` (a 16x16 list of SPEC indices)."""
    bmp, atr = t[:32], t[32:]
    for pp in range(8):
        for col in range(2):
            a = atr[col * 8 + pp]
            ink = (a & 7) + (8 if a & 0x40 else 0)
            paper = ((a >> 3) & 7) + (8 if a & 0x40 else 0)
            for row in range(2):
                b = bmp[(pp * 2 + row) * 2 + col]
                for i in range(8):
                    bit = (b >> (7 - i)) & 1
                    out[pp * 2 + row][col * 8 + i] = ink if bit else paper


def render_band_png(tile_bytes, m, path, rows=None):
    """Re-render a tile map to a 256x(16*rows) PNG using the ZX palette."""
    from PIL import Image
    r = tile_rows(rows)
    img = Image.new("RGB", (BAND_W, 16 * r))
    px = img.load()
    for cy in range(r):
        for cx in range(COLS):
            t = tile_bytes[m[cy * COLS + cx]]
            grid = [[0] * 16 for _ in range(16)]
            tile_to_rgb(t, grid)
            for y in range(16):
                for x in range(16):
                    px[cx * 16 + x, cy * 16 + y] = rgb(grid[y][x])
    img.save(path)


def _nearest_bank_spec(v, bank):
    """Base colour index 0..7 (in the given bright bank) nearest to SPEC[v]."""
    r, g, b = rgb(v)
    off = 8 if bank else 0
    best, bd = 0, 1 << 30
    for i in range(8):
        pr, pg, pb = SPEC[off + i]
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < bd:
            bd, best = d, i
    return best


def _attr_band(grid, cell_h, dither=DEFAULT_DITHER, rows=None, source=None):
    """Re-quantise a SPEC grid under rectangular attribute cells of height
    ``cell_h`` (width is always 8).

    Each cell picks one ink and one paper colour plus a shared bright bit, by
    exhaustive search over both bright banks. ``dither`` then assigns every
    pixel to one of that cell's colours (``off`` snaps to the nearer one);
    ``source`` is the prepared RGB band used by the ordered/diffusion schemes.
    ``cell_h=8`` is the classic 8x8 character cell; ``cell_h=1`` is Bifrost*'s
    per-scanline 8x1 cell.
    """
    h, w = len(grid), len(grid[0])
    mode = dither_mode(dither)
    pairs = {}
    for cy in range(0, h, cell_h):
        for cx in range(0, w, 8):
            best = None
            for bank in (0, 1):
                counts = {}
                for y in range(cy, cy + cell_h):
                    for x in range(cx, cx + 8):
                        bc = _nearest_bank_spec(grid[y][x], bank)
                        counts[bc] = counts.get(bc, 0) + 1
                items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
                ink, paper = items[0][0], items[-1][0]
                ink_rgb, paper_rgb = rgb(ink + 8 * bank), rgb(paper + 8 * bank)
                err = 0
                for y in range(cy, cy + cell_h):
                    for x in range(cx, cx + 8):
                        r, g, b = rgb(grid[y][x])
                        di = ((r - ink_rgb[0]) ** 2 + (g - ink_rgb[1]) ** 2
                              + (b - ink_rgb[2]) ** 2)
                        dp = ((r - paper_rgb[0]) ** 2 + (g - paper_rgb[1]) ** 2
                              + (b - paper_rgb[2]) ** 2)
                        err += di if di <= dp else dp
                if best is None or err < best[0]:
                    best = (err, ink, paper, bank)
            _, ink, paper, bank = best
            pairs[(cy, cx)] = (ink + 8 * bank, paper + 8 * bank)
    out = [[0] * w for _ in range(h)]
    if mode == "off" or source is None:
        for (cy, cx), (ink, paper) in pairs.items():
            ink_rgb, paper_rgb = rgb(ink), rgb(paper)
            for y in range(cy, cy + cell_h):
                for x in range(cx, cx + 8):
                    r, g, b = rgb(grid[y][x])
                    di = ((r - ink_rgb[0]) ** 2 + (g - ink_rgb[1]) ** 2
                          + (b - ink_rgb[2]) ** 2)
                    dp = ((r - paper_rgb[0]) ** 2 + (g - paper_rgb[1]) ** 2
                          + (b - paper_rgb[2]) ** 2)
                    out[y][x] = ink if di <= dp else paper
        return out

    def palette_at(x, y):
        ink, paper = pairs[((y // cell_h) * cell_h, (x // 8) * 8)]
        return (rgb(ink), rgb(paper))

    flat = dither_grid(source, palette_at, mode)
    for (cy, cx), (ink, paper) in pairs.items():
        for y in range(cy, cy + cell_h):
            base = y * w
            for x in range(cx, cx + 8):
                out[y][x] = ink if flat[base + x] == 0 else paper
    return out


def classic_band(im, crop=None, dither=DEFAULT_DITHER, rows=None, adjust=None,
                 palette=DEFAULT_PALETTE, palette_colors=None, margin=0,
                 fill=(0, 0, 0)):
    """Quantise to a 256x(16*rows) SPEC grid under standard 8x8 attributes.

    Each 8x8 character cell gets one ink and one paper colour and a shared
    bright bit -- the classic Spectrum attribute-clash look, the plain
    alternative to NIRVANA+'s per-2-line bicolor. ``dither`` assigns pixels
    between the cell's two colours (see ``dither_grid``). The optional colour
    adjustments / palette pre-reduction (see ``_prepare_band``) apply as in
    NIRVANA+. Returns a band-height x BAND_W grid of SPEC indices.
    """
    prepared = _prepare_band(im, crop, rows, adjust, palette, palette_colors,
                             margin, fill)
    return _attr_band(_quant_image(prepared), 8, dither=dither, rows=rows,
                      source=prepared)


def bifrost_band(im, crop=None, rows=None, adjust=None,
                 palette=DEFAULT_PALETTE, palette_colors=None, margin=0,
                 fill=(0, 0, 0)):
    """Approximate Bifrost*'s 8x1 multicolour as a 256x(16*rows) SPEC grid.

    Bifrost changes ink/paper every scanline (8x1 cells) rather than every 8x8
    character cell, so vertical colour is finer than classic attributes. This
    is a pure-Python approximation of that quantisation, not an engine render:
    Bifrost drives only 20 of the 32 columns this band uses. The optional
    colour adjustments / palette pre-reduction apply as in NIRVANA+. Returns a
    band-height x BAND_W grid of SPEC indices.
    """
    return _attr_band(quant(im, crop=crop, rows=rows, adjust=adjust,
                            palette=palette, palette_colors=palette_colors,
                            margin=margin, fill=fill), 1)


def classic_band_blob(grid):
    """Pack a classic-attribute SPEC grid into ULA bitmap + attribute bytes.

    Returns ``bitmap + attrs``: the bitmap is 32 bytes per pixel row in
    scanline order (the layout the 48K runtime copies into the ULA bitmap) and
    attrs is 32 bytes per 8x8 character row. Within each cell the most common
    colour becomes ink (set bits) and the other paper, so the stored attribute
    always matches the packed pixels.
    """
    h = len(grid)
    if h % 8 or not grid or len(grid[0]) != BAND_W:
        raise ValueError("classic band must be BAND_W x a multiple of 8")
    chars = h // 8
    bitmap = bytearray(chars * 8 * 32)
    attrs = bytearray(chars * 32)
    for cr in range(chars):
        for cc in range(32):
            counts = {}
            for y in range(cr * 8, cr * 8 + 8):
                row = grid[y]
                for x in range(cc * 8, cc * 8 + 8):
                    v = row[x]
                    counts[v] = counts.get(v, 0) + 1
            items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            ink = items[0][0]
            paper = items[-1][0]
            bank = (ink >> 3) & 1
            attrs[cr * 32 + cc] = (bank << 6) | ((paper & 7) << 3) | (ink & 7)
            for line in range(8):
                bits = 0
                row = grid[cr * 8 + line]
                for bit in range(8):
                    if row[cc * 8 + bit] == ink:
                        bits |= 0x80 >> bit
                bitmap[(cr * 8 + line) * 32 + cc] = bits
    return bytes(bitmap) + bytes(attrs)


def grid_to_rgb_image(grid):
    """Turn a band-height x BAND_W grid of SPEC indices into a PIL image."""
    from PIL import Image
    h, w = len(grid), len(grid[0])
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = rgb(grid[y][x])
    return img


def band_to_art(grid, rows=None):
    """Convert a SPEC-index grid into (map, tile_bytes, blob).

    Tiles are deduped within the band (``8*rows`` tiles max, so the index fits
    a byte). ``rows`` is the band height in 16px tile rows; when omitted it is
    derived from the grid height. The blob is map[8*rows] + tiles[48*N]: the
    engine pages it into the art workspace, points NIRVANAP_TILE_IMAGES at
    blob+map_len and draws each map entry.
    """
    if rows is None:
        rows = len(grid) // 16
    rows = int(rows)
    index, tiles = {}, []
    m = []
    for cy in range(rows):
        for cx in range(COLS):
            t = btile(grid, cx * 16, cy * 16)
            h = hashlib.blake2b(t, digest_size=8).hexdigest()
            if h not in index:
                index[h] = len(tiles)
                tiles.append(t)
            m.append(index[h])
    assert len(tiles) <= 256, "tile index must fit a byte"
    blob = bytes(m) + b"".join(tiles)
    return m, tiles, blob
