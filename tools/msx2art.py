"""MSX2 (V9938) art conversion helpers.

The MSX2 runtime uses Screen 7: a 512 x 212 four-bit bitmap with sixteen
palette entries selected from the V9938's 9-bit RGB (512-colour) space.  The
art band is the full 512 x (8*art_rows) Screen 7 width above an 80-column
text pane.  Screen 7 pixels are half-width (512 pixels span Screen 5's 256),
so the source is fitted to that physical aspect and stretched into the pixel
grid; an explicit crop keeps its full width and re-centres its vertical window
to that aspect, so it is neither stretched nor cropped sideways.  The editor
preview is doubled vertically to show the same proportions.  The editor preview
and the ROM build share this module.

Palette entry 0 is the configured text background, and entries 14/15 the
configured highlight/text inks; the remaining thirteen colours are chosen from
the art.  A compiled art blob is::

    [u8 palette[16*2]][u8 bitmap[256*8*art_rows]]

Palette bytes are ``red:3 << 4 | blue:3`` followed by ``green:3``; bitmap bytes
hold two pixels each (high nibble first).
"""
from __future__ import annotations

import io

TEXT_BLACK = 0
TEXT_GREEN = 14
TEXT_WHITE = 15
DEFAULT_ART_ROWS = 12

# Screen 7's 512 pixels span the same physical width as Screen 5's 256, so
# each pixel is half as wide as it is tall.
PIXEL_WIDTH_DIV = 2


def _fit(im, crop, art_rows, width=512):
    from PIL import Image
    import zxart
    art_rows = int(art_rows)
    height = 8 * art_rows
    phys_width = max(1, width // PIXEL_WIDTH_DIV)
    w, h = im.size
    box = im.crop(zxart.band_crop_rect(crop, w, h,
                                       phys_width / float(height)))
    target = (width, height)
    if box.size != target:
        box = box.resize(target, Image.LANCZOS)
    return box


def _prepared(im, crop, art_rows, dither, adjust):
    import zxart
    from PIL import Image
    art_rows = int(art_rows)
    im = _fit(im, crop, art_rows)
    a = adjust or {}
    im = zxart.preprocess(im, a.get("saturation", 1.0),
                          a.get("contrast", 1.0),
                          a.get("brightness", 1.0), a.get("gamma", 1.0))
    if str(dither or "off").lower() != "off":
        im = im.quantize(colors=16, method=Image.Quantize.MEDIANCUT,
                         dither=Image.Dither.FLOYDSTEINBERG).convert("RGB")
    return im


def _rgb8(value):
    return (int(value) & 7) * 255 // 7


# `# Game` text colour token -> ((dim RGB333), (bright RGB333)).  Dim colours
# use level 4 of the 0..7 channel scale, bright colours level 7.
_TEXT_INKS = {
    "black": ((0, 0, 0), (0, 0, 0)),
    "blue": ((0, 0, 4), (0, 0, 7)),
    "green": ((0, 4, 0), (0, 7, 0)),
    "cyan": ((0, 4, 4), (0, 7, 7)),
    "red": ((4, 0, 0), (7, 0, 0)),
    "magenta": ((4, 0, 4), (7, 0, 7)),
    "yellow": ((4, 4, 0), (7, 7, 0)),
    "white": ((4, 4, 4), (7, 7, 7)),
}


def text_ink(token):
    """Map a scenefile colour token to a V9938 RGB333 colour."""
    t = str(token or "").strip().lower()
    dim = t.startswith("dim_")
    name = t[4:] if dim else t
    pair = _TEXT_INKS.get(name, _TEXT_INKS["white"])
    return pair[0] if dim else pair[1]


def text_colours(game):
    """Resolve the ``# Game`` text colours to MSX2 RGB333 colours.

    Returns ``(text_ink, highlight_ink, text_bg)``.
    """
    import scenefile
    text, highlight, bg = scenefile.text_tokens(game)
    return text_ink(text), text_ink(highlight), text_ink(bg)


def _bg_rgb(text_bg):
    """Expand a resolved RGB333 background (or the default) to 8-bit RGB."""
    if text_bg is None:
        _ink, _hi, text_bg = text_colours(None)
    return tuple(_rgb8(v) for v in text_bg)


def palette_pair(color):
    """Return one RGB333 colour as a little-endian two-byte palette value."""
    r, g, b = (int(v) & 7 for v in color)
    return ((r << 4) | b) | ((g & 7) << 8)


def _palette_bytes(colors):
    """Return the 32-byte V9938 palette and its RGB8 preview values."""
    out = bytearray()
    rgb = []
    for r, g, b in colors:
        r &= 7
        g &= 7
        b &= 7
        out.append((r << 4) | b)
        out.append(g)
        rgb.append((_rgb8(r), _rgb8(g), _rgb8(b)))
    return bytes(out), rgb


def _art_palette(im, text=None, highlight=None, bg=None):
    """Choose 16 RGB333 colours: background, 13 image colours, highlight, text."""
    from PIL import Image

    if text is None or highlight is None or bg is None:
        default_text, default_hi, default_bg = text_colours(None)
        text = default_text if text is None else text
        highlight = default_hi if highlight is None else highlight
        bg = default_bg if bg is None else bg
    q = im.quantize(colors=13, method=Image.Quantize.MEDIANCUT,
                    dither=Image.Dither.NONE)
    raw = q.getpalette() or []
    colors = [tuple(int(v) & 7 for v in bg)]
    for i in range(13):
        rgb = raw[i * 3:i * 3 + 3]
        if len(rgb) == 3:
            colors.append(tuple((int(c) * 7 + 127) // 255 for c in rgb))
        else:
            colors.append((0, 0, 0))
    colors.append(tuple(int(v) & 7 for v in highlight))
    colors.append(tuple(int(v) & 7 for v in text))
    return colors[:16]


def _indexed(im, conv, text=None, highlight=None, bg=None):
    from PIL import Image
    import zxart

    conv = conv or {}
    colors = _art_palette(im, text, highlight, bg)
    rgb = []
    for r, g, b in colors:
        rgb.extend((_rgb8(r), _rgb8(g), _rgb8(b)))
    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette(rgb)
    dither = (Image.Dither.NONE
              if str(conv.get("dither") or "off").lower() == "off"
              else Image.Dither.FLOYDSTEINBERG)
    q = im.quantize(palette=pal_img, dither=dither)
    return list(q.getdata()), colors


def _pack(indexed, art_rows):
    width = 512
    out = bytearray()
    for y in range(8 * int(art_rows)):
        base = y * width
        for x in range(0, width, 2):
            out.append((indexed[base + x] << 4) | indexed[base + x + 1])
    return bytes(out)


def art_blob(path, conv=None, options=None, text_ink=None, highlight_ink=None,
             text_bg=None):
    """Return the MSX2 art blob for ``path``, or None if unreadable."""
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
    im = _fit(im, conv.get("crop"), art_rows)
    adj = conv.get("adjust") or {}
    import zxart
    im = zxart.preprocess(im, adj.get("saturation", 1.0),
                          adj.get("contrast", 1.0),
                          adj.get("brightness", 1.0),
                          adj.get("gamma", 1.0))
    im = zxart.inset_band(im, conv.get("margin", 0), _bg_rgb(text_bg))
    indexed, colors = _indexed(im, conv, text_ink, highlight_ink, text_bg)
    pal, _rgb = _palette_bytes(colors)
    return pal + _pack(indexed, art_rows)


def blank_blob(art_rows=DEFAULT_ART_ROWS, text_ink=None, highlight_ink=None,
               text_bg=None):
    """A background band with the reserved text palette."""
    if text_ink is None or highlight_ink is None or text_bg is None:
        default_text, default_hi, default_bg = text_colours(None)
        text_ink = default_text if text_ink is None else text_ink
        highlight_ink = default_hi if highlight_ink is None else highlight_ink
        text_bg = default_bg if text_bg is None else text_bg
    colors = ([tuple(int(v) & 7 for v in text_bg)] + [(0, 0, 0)] * 13
              + [tuple(int(v) & 7 for v in highlight_ink),
                 tuple(int(v) & 7 for v in text_ink)])
    pal, _rgb = _palette_bytes(colors)
    return pal + bytes(256 * 8 * int(art_rows))


def band(im, crop=None, art_rows=DEFAULT_ART_ROWS, dither="off", adjust=None,
         match="rgb", options=None, text_ink=None, highlight_ink=None,
         text_bg=None, margin=0):
    """Return the MSX2 band as an RGB image."""
    from PIL import Image
    import zxart

    conv = {"crop": crop, "dither": dither, "adjust": adjust or {},
            "margin": margin}
    art_rows = int(art_rows)
    im = _fit(im, conv.get("crop"), art_rows)
    a = conv.get("adjust") or {}
    im = zxart.preprocess(im, a.get("saturation", 1.0),
                          a.get("contrast", 1.0),
                          a.get("brightness", 1.0), a.get("gamma", 1.0))
    im = zxart.inset_band(im, margin, _bg_rgb(text_bg))
    indexed, colors = _indexed(im, conv, text_ink, highlight_ink, text_bg)
    _pal, rgb = _palette_bytes(colors)
    img = Image.new("RGB", (512, 8 * art_rows))
    img.putdata([rgb[v] for v in indexed])
    return img


def preview_bytes(path, conv=None, options=None, text_ink=None,
                  highlight_ink=None, text_bg=None):
    from PIL import Image
    conv = conv or {}
    options = options or {}
    try:
        im = Image.open(path).convert("RGB")
    except Exception:                          # noqa: BLE001 - missing/corrupt
        return None
    art_rows = int(options.get("art_rows") or DEFAULT_ART_ROWS)
    img = band(im, crop=conv.get("crop"), art_rows=art_rows,
               dither=conv.get("dither", "off"),
               adjust=conv.get("adjust"),
               match=conv.get("match", "rgb"),
               text_ink=text_ink, highlight_ink=highlight_ink,
               text_bg=text_bg, margin=conv.get("margin", 0))
    import zxart
    img = zxart.preview_margin_crop(img, conv.get("margin"), 512,
                                    8 * art_rows)
    # The bitmap is 512 px wide but Screen 7 shows it with half-width pixels;
    # double the preview height so the editor shows the physical proportions.
    img = img.resize((img.width, img.height * PIXEL_WIDTH_DIV),
                     Image.NEAREST)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
