"""MSX1 (TMS9918A) art conversion helpers.

The MSX1 runtime uses Graphics II (SCREEN 2): a 256 x 192 tile display with
three 2 KB pattern-generator banks (one per eight-row screen third), a 6 KB
colour table (one ink/paper pair per 8x1 cell row) and a 768-byte name table.
The art band is 256 x (8*art_rows) pixels above the 32-column text pane.  Each
8x8 cell therefore has two TMS9918 colours per 8x1 row, and a cell's pattern is
shared by every screen third only through its own bank; the runtime copies the
band's patterns into banks 0 and 1.

A compiled art blob is::

    [u8 ntiles][u8 cell[32*art_rows][1 pnt + 8 colour bytes]]
        [u8 patterns[ntiles*8]]

The name-table byte in each cell is the real Graphics II pattern number
(96..255 for art, 0..95 for the shared font).  The eight colour bytes are
``ink << 4 | paper`` for that cell's eight pixel rows.

``mono`` (the per-system Black and white option) renders the picture as a
dithered white-on-black 1-bit band instead of the 15-colour TMS9918 palette.
The editor preview and the ROM build share this module.
"""
from __future__ import annotations

import io
from itertools import combinations

MAX_TILES = 160
DEFAULT_ART_ROWS = 10
ART_COLS = 32
FONT_TILES = 96
MONO_INK = 15
MONO_PAPER = 1

# TMS9918A fixed palette.  Index 0 is transparent on the hardware; the art
# converter reserves it and uses 1..15 only.
TMS_RGB = [
    (0, 0, 0),
    (0, 0, 0),
    (33, 200, 66),
    (94, 220, 120),
    (84, 85, 237),
    (125, 118, 252),
    (212, 82, 77),
    (66, 235, 245),
    (252, 85, 84),
    (255, 121, 120),
    (212, 193, 84),
    (230, 206, 128),
    (33, 176, 59),
    (201, 91, 186),
    (204, 204, 204),
    (255, 255, 255),
]

# `# Game` text colour token -> (dim TMS colour, bright TMS colour).  Colour 0
# is transparent, so black maps to 1 (the TMS black).
_TEXT_INKS = {
    "black": (1, 1),
    "blue": (4, 5),
    "green": (2, 3),
    "cyan": (7, 7),
    "red": (6, 8),
    "magenta": (13, 13),
    "yellow": (10, 11),
    "white": (14, 15),
}


def text_ink(token):
    t = str(token or "").strip().lower()
    dim = t.startswith("dim_")
    name = t[4:] if dim else t
    pair = _TEXT_INKS.get(name, _TEXT_INKS["white"])
    return pair[0] if dim else pair[1]


def text_colours(game, mono=False):
    """Resolve ``# Game`` text colours to TMS9918 colour indices.

    Returns ``(text_ink, highlight_ink, text_bg)``.  ``mono`` forces the
    black-and-white system option (white ink on black).
    """
    if mono:
        return MONO_INK, MONO_INK, MONO_PAPER
    import scenefile
    text, highlight, bg = scenefile.text_tokens(game)
    return text_ink(text), text_ink(highlight), text_ink(bg)


def colour_byte(ink, paper):
    """One TMS9918 colour-table byte (foreground high nibble)."""
    ink = int(ink) & 0x0F
    paper = int(paper) & 0x0F
    return ((ink or MONO_PAPER) << 4) | (paper or MONO_PAPER)


def _fit(im, crop, art_rows):
    from PIL import Image
    import zxart
    art_rows = int(art_rows)
    width, height = 256, 8 * art_rows
    w, h = im.size
    box = im.crop(zxart.band_crop_rect(crop, w, h,
                                       width / float(height)))
    if box.size != (width, height):
        box = box.resize((width, height), Image.LANCZOS)
    return box


def _prepared(im, conv, art_rows, bg_rgb):
    import zxart
    im = _fit(im, conv.get("crop"), art_rows)
    a = conv.get("adjust") or {}
    im = zxart.preprocess(im, a.get("saturation", 1.0),
                          a.get("contrast", 1.0),
                          a.get("brightness", 1.0), a.get("gamma", 1.0))
    return zxart.inset_band(im, conv.get("margin", 0), bg_rgb)


def _bg_rgb(text_bg):
    index = int(text_bg or MONO_PAPER) & 0x0F
    if index == 0:
        index = MONO_PAPER
    return TMS_RGB[index]


def _quantize(im):
    """Map ``im`` to the 15 usable TMS9918 palette indices (0..14 -> 1..15)."""
    from PIL import Image
    rgb = []
    for colour in TMS_RGB[1:]:
        rgb.extend(colour)
    rgb.extend([0] * (768 - len(rgb)))
    pal = Image.new("P", (1, 1))
    pal.putpalette(rgb)
    q = im.quantize(palette=pal, dither=Image.Dither.NONE)
    return list(q.getdata())


def _dist2(a, b):
    dr = a[0] - b[0]
    dg = a[1] - b[1]
    db = a[2] - b[2]
    return dr * dr + dg * dg + db * db


def _row_pair(indices):
    """Best TMS ink/paper indices for eight palette indices and their bits."""
    uniq = list(dict.fromkeys(indices))
    if len(uniq) == 1:
        idx = uniq[0] + 1
        return 0, idx, idx
    best = None
    for a, b in combinations(uniq, 2):
        ca, cb = TMS_RGB[a + 1], TMS_RGB[b + 1]
        err = 0
        bits = 0
        for i, q in enumerate(indices):
            p = TMS_RGB[q + 1]
            da = _dist2(p, ca)
            db = _dist2(p, cb)
            if da <= db:
                bits |= 0x80 >> i
                err += da
            else:
                err += db
        if best is None or err < best[0]:
            best = (err, bits, a + 1, b + 1)
    _, bits, ink, paper = best
    return bits, ink, paper


def _fixed_pattern(rgb_rows, pattern):
    """Choose an ink/paper pair for each row of an already fixed pattern."""
    colours = list(range(1, 16))
    result = []
    for y in range(8):
        bit = pattern[y]
        ink_px = [rgb_rows[y][x] for x in range(8) if bit & (0x80 >> x)]
        paper_px = [rgb_rows[y][x] for x in range(8) if not bit & (0x80 >> x)]
        best = None
        for a in colours:
            ca = TMS_RGB[a]
            da = sum(_dist2(p, ca) for p in ink_px)
            for b in colours:
                if b == a:
                    continue
                db = sum(_dist2(p, TMS_RGB[b]) for p in paper_px)
                err = da + db
                if best is None or err < best[0]:
                    best = (err, a, b)
        if best is None:
            result.append(colour_byte(MONO_INK, MONO_PAPER))
        else:
            result.append(colour_byte(best[1], best[2]))
    return result


def _pack_cells(cell_rows):
    """Deduplicate 8-byte patterns and build cells + pattern data.

    ``cell_rows`` is a list of ``(pattern, colour_bytes)`` in art-band order.
    Patterns are capped at ``MAX_TILES``; an extra pattern is merged into the
    nearest one and that cell's colours are recomputed for the shared pattern.
    """
    patterns = []
    index = {}
    cells = bytearray()
    for pattern, colours, rgb_rows in cell_rows:
        key = bytes(pattern)
        if not any(key):
            cells.append(0)
            cells.extend(colours)
            continue
        idx = index.get(key)
        if idx is None and len(patterns) < MAX_TILES:
            idx = len(patterns)
            patterns.append(key)
            index[key] = idx
        elif idx is None:
            # Reuse the most similar existing pattern (the colour table is per
            # cell, so only the 1bpp pattern itself has to be shared).
            best = None
            value = int.from_bytes(key, "big")
            for i, existing in enumerate(patterns):
                diff = (value ^ int.from_bytes(existing, "big")).bit_count()
                if best is None or diff < best[0]:
                    best = (diff, i)
            idx = best[1]
            pattern = patterns[idx]
            if rgb_rows is not None:
                colours = _fixed_pattern(rgb_rows, pattern)
        cells.append((FONT_TILES + idx) & 0xFF)
        cells.extend(colours)
    return bytes([len(patterns)]) + bytes(cells) + b"".join(patterns)


def _colour_blob(im, conv, art_rows, text_bg):
    im = _prepared(im, conv, art_rows, _bg_rgb(text_bg))
    indexed = _quantize(im)
    width = 256
    cell_rows = []
    for cy in range(int(art_rows)):
        for cx in range(ART_COLS):
            bits = []
            colours = []
            rgb_rows = []
            for y in range(8):
                row = []
                for x in range(8):
                    row.append(indexed[(cy * 8 + y) * width + cx * 8 + x])
                rgb_rows.append([TMS_RGB[q + 1] for q in row])
                bit, ink, paper = _row_pair(row)
                bits.append(bit)
                colours.append(colour_byte(ink, paper))
            cell_rows.append((bytes(bits), colours, rgb_rows))
    return _pack_cells(cell_rows)


def _mono_blob(im, conv, art_rows, text_bg):
    import zxart
    # Fit through ``_prepared`` so an explicit crop is re-centred to the MSX1
    # band aspect (``mono_band`` would rescale the raw ZX crop rectangle and
    # distort the picture).
    im = _prepared(im, conv, art_rows, _bg_rgb(text_bg))
    im = zxart._apply_palette(im, conv.get("palette", "none"),
                              conv.get("palette_colors"))
    im = zxart.to_mono_image(im, conv.get("dither", "off"))
    px = im.load()
    colour = colour_byte(MONO_INK, MONO_PAPER)
    cell_rows = []
    for cy in range(int(art_rows)):
        for cx in range(ART_COLS):
            pattern = bytes(
                sum(0x80 >> x for x in range(8)
                    if px[cx * 8 + x, cy * 8 + y][0] >= 128)
                for y in range(8))
            cell_rows.append((pattern, [colour] * 8, None))
    return _pack_cells(cell_rows)


def _blob_from_image(im, conv, art_rows, text_bg, mono=False):
    if mono:
        return _mono_blob(im, conv, art_rows, text_bg)
    return _colour_blob(im, conv, art_rows, text_bg)


def art_blob(path, conv=None, options=None, text_bg=None):
    """Return an MSX1 art blob for ``path``, or None if it cannot be read."""
    from PIL import Image
    if not path:
        return None
    try:
        im = Image.open(path).convert("RGB")
    except Exception:                          # noqa: BLE001 - missing/corrupt
        return None
    conv = conv or {}
    options = options or {}
    art_rows = int(options.get("art_rows") or DEFAULT_ART_ROWS)
    mono = bool(options.get("mono"))
    if text_bg is None:
        text_bg = MONO_PAPER
    return _blob_from_image(im, conv, art_rows, text_bg, mono)


def blank_blob(art_rows=DEFAULT_ART_ROWS, text_bg=None, mono=False):
    """A one-colour band (the font's blank tile) in the reserved background."""
    if text_bg is None:
        _t, _h, text_bg = text_colours(None)
    paper = int(text_bg or MONO_PAPER)
    colour = colour_byte(paper, paper)
    cell_rows = [(bytes(8), [colour] * 8, None)
                 for _ in range(int(art_rows) * ART_COLS)]
    return _pack_cells(cell_rows)


def _render_blob(blob, art_rows, palette=None):
    """Render an art blob back to a 256 x (8*art_rows) RGB image."""
    from PIL import Image
    art_rows = int(art_rows)
    npat = blob[0]
    cells = blob[1:1 + art_rows * ART_COLS * 9]
    patterns = blob[1 + art_rows * ART_COLS * 9:]
    img = Image.new("RGB", (256, 8 * art_rows), (0, 0, 0))
    px = img.load()
    for cy in range(art_rows):
        for cx in range(ART_COLS):
            off = (cy * ART_COLS + cx) * 9
            pnt = cells[off]
            cols = cells[off + 1:off + 9]
            if pnt < FONT_TILES or pnt >= FONT_TILES + npat:
                pat = bytes(8)
            else:
                start = (pnt - FONT_TILES) * 8
                pat = patterns[start:start + 8]
            for y in range(8):
                colour = cols[y]
                ink = (colour >> 4) & 0x0F
                paper = colour & 0x0F
                if not ink:
                    ink = MONO_PAPER
                if not paper:
                    paper = MONO_PAPER
                for x in range(8):
                    q = ink if pat[y] & (0x80 >> x) else paper
                    px[cx * 8 + x, cy * 8 + y] = TMS_RGB[q & 0x0F]
    return img


def band(im, crop=None, art_rows=DEFAULT_ART_ROWS, dither="off", adjust=None,
         options=None, text_bg=None, margin=0, mono=False):
    """Return the converted band as an RGB image for the editor."""
    options = dict(options or {})
    options["art_rows"] = art_rows
    options["mono"] = mono
    conv = {"crop": crop, "dither": dither, "adjust": adjust or {},
            "margin": margin}
    blob = _blob_from_image(im, conv, art_rows, text_bg, mono)
    return _render_blob(blob, art_rows)


def preview_bytes(path, conv=None, options=None, text_bg=None, mono=False):
    from PIL import Image
    conv = conv or {}
    options = options or {}
    try:
        im = Image.open(path).convert("RGB")
    except Exception:                          # noqa: BLE001 - missing/corrupt
        return None
    art_rows = int(options.get("art_rows") or DEFAULT_ART_ROWS)
    mono = bool(mono or options.get("mono"))
    img = band(im, crop=conv.get("crop"), art_rows=art_rows,
               dither=conv.get("dither", "off"), adjust=conv.get("adjust"),
               text_bg=text_bg, margin=conv.get("margin", 0), mono=mono)
    import zxart
    img = zxart.preview_margin_crop(img, conv.get("margin", 0), 256,
                                    8 * art_rows)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()
