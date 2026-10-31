"""Amstrad CPC art conversion helpers.

CPC video memory is always 80 bytes per scanline; the mode only changes how
many pixels/inks a byte carries:

    mode 0  160x200, 16 inks, 2 pixels per byte (4 bits each)
    mode 1  320x200,  4 pens (monochrome), 4 pixels per byte (2 bits each)
    mode 2  640x200,  2 inks, 8 pixels per byte (1 bit each)

The game band is ``mode_width x (8*art_rows)``.  A compiled art blob is
``[u8 ninks][u8 hardware ink * ninks][8 blk chunks]`` where each chunk holds
``art_rows`` consecutive 80-byte scanlines for one of the eight scanline
offsets of a CPC character row.  The runtime pages the blob in, decodes it to
the screen, and scatters the chunks to rows 1..art_rows.

Mode 1 is monochrome: its four pens are a black/grey/white ramp shared by the
picture and the text, so the configured text colours do not apply there.  The
luminance is ordered-dithered onto the ramp; the regular Bayer pattern packs far
smaller than error diffusion in the CPC's four extra banks.  In
Modes 0 and 2 palette entry 0 is the configured ``text_bg:`` (default black)
because the runtime clears the title/text pane to pen 0.  The last entry is
``text_ink:`` and the one before it ``highlight_ink:`` (Mode 2 uses the text ink
for both).  Those colours are forced into the palette before quantising, so the
picture may still use them; it keeps the mode's full ink count and the text is
drawn in the colours the author chose rather than the picture's brightest inks.

An explicit crop keeps its full width: its vertical window is re-centred to
the band's aspect (clamped to the source), so the source keeps its proportions
without being cropped sideways or stretched.  The CPC screen is 4:3 and the
three modes use different pixel widths, so the band is fitted to the screen's
physical aspect and then squeezed into the mode's pixel grid; the CPC widens
(Mode 0) or narrows (Mode 2) it again on display.

Mode 0 pixels are not plain nibbles: each byte interleaves the two pixels'
bitplanes as ``p0-b0 p1-b0 p0-b2 p1-b2 p0-b1 p1-b1 p0-b3 p1-b3`` (bits 7..0).
"""
from __future__ import annotations

import io

# The 27 hardware inks of the CPC's Gate Array (RGB approximations).
CPC_PALETTE = [
    (0, 0, 0),       # 0 black
    (0, 0, 128),     # 1 blue
    (0, 0, 255),     # 2 bright blue
    (128, 0, 0),     # 3 red
    (128, 0, 128),   # 4 magenta
    (128, 0, 255),   # 5 violet
    (255, 0, 0),     # 6 bright red
    (255, 0, 128),   # 7 pink
    (255, 0, 255),   # 8 bright magenta
    (0, 128, 0),     # 9 green
    (0, 128, 128),   # 10 cyan
    (0, 128, 255),   # 11 sky blue
    (128, 128, 0),   # 12 yellow
    (128, 128, 128), # 13 grey
    (128, 128, 255), # 14 light blue
    (255, 128, 0),   # 15 orange
    (255, 128, 128), # 16 salmon
    (255, 128, 255), # 17 light magenta
    (0, 255, 0),     # 18 bright green
    (0, 255, 128),   # 19 sea green
    (0, 255, 255),   # 20 bright cyan
    (128, 255, 0),   # 21 lime
    (128, 255, 128), # 22 light green
    (128, 255, 255), # 23 pale cyan
    (255, 255, 0),   # 24 bright yellow
    (255, 255, 128), # 25 pale yellow
    (255, 255, 255), # 26 white
]

# mode -> (width, number of inks, pixels per byte)
MODE_INFO = {
    0: (160, 16, 2),
    1: (320, 4, 4),
    2: (640, 2, 8),
}
DEFAULT_MODE = 1
DEFAULT_ART_ROWS = 12

# Mode 1's four pens are a black/grey/white ramp; the CPC only has three
# neutral Gate Array inks, so the brightest one fills both text pens.
MONO_INKS = (0, 13, 26, 26)

# `# Game` text colour token -> (dim ink, bright ink) hardware CPC ink.
_TEXT_INKS = {
    "black": (0, 0), "blue": (1, 2), "green": (9, 18), "cyan": (10, 20),
    "red": (3, 6), "magenta": (4, 8), "yellow": (12, 24), "white": (13, 26),
}


def text_ink(token):
    """Map a scenefile colour token to the nearest CPC hardware ink."""
    t = str(token or "").strip().lower()
    dim = t.startswith("dim_")
    name = t[4:] if dim else t
    pair = _TEXT_INKS.get(name, _TEXT_INKS["white"])
    return pair[0] if dim else pair[1]


def text_colours(game):
    """Resolve the ``# Game`` text colours to CPC hardware inks.

    Returns ``(text_ink, highlight_ink, text_bg)``.
    """
    import scenefile
    text, highlight, bg = scenefile.text_tokens(game)
    return text_ink(text), text_ink(highlight), text_ink(bg)


def _norm_mode(mode):
    """Return a known CPC mode id, falling back to ``DEFAULT_MODE``."""
    try:
        mode = int(mode)
    except (TypeError, ValueError):
        mode = DEFAULT_MODE
    return mode if mode in MODE_INFO else DEFAULT_MODE


def mode_info(mode):
    """Return ``(width, inks, pixels_per_byte)`` for a CPC mode."""
    return MODE_INFO[_norm_mode(mode)]


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
            + (a[2] - b[2]) ** 2)


def _nearest_ink(rgb):
    best = 0
    bestd = None
    for i, c in enumerate(CPC_PALETTE):
        d = _dist(rgb, c)
        if bestd is None or d < bestd:
            best, bestd = i, d
    return best


def _select_inks(im, count):
    """Choose ``count`` distinct CPC hardware inks for the image.

    A median-cut pass finds the image's dominant colours; each is snapped to
    the nearest Gate Array ink.  Duplicate snaps are filled with the nearest
    unused hardware ink so the requested ink count is always present.
    """
    from PIL import Image
    q = im.quantize(colors=count, method=Image.Quantize.MEDIANCUT,
                    dither=Image.Dither.NONE)
    raw = q.getpalette() or []
    centres = []
    for i in range(count):
        rgb = tuple(raw[i * 3:i * 3 + 3])
        if len(rgb) == 3:
            centres.append(rgb)
    chosen = []
    for c in centres:
        idx = _nearest_ink(c)
        if idx not in chosen:
            chosen.append(idx)
    if len(chosen) < count:
        unused = [i for i in range(len(CPC_PALETTE)) if i not in chosen]
        for c in centres:
            if len(chosen) >= count:
                break
            unused.sort(key=lambda i: _dist(c, CPC_PALETTE[i]))
            for idx in unused:
                if idx not in chosen:
                    chosen.append(idx)
                    break
        if len(chosen) < count:
            for idx in range(len(CPC_PALETTE)):
                if idx not in chosen:
                    chosen.append(idx)
                if len(chosen) >= count:
                    break
    return chosen[:count]


# The CPC screen is 4:3, so a full-width band of `height` scanlines has a
# physical aspect of (4/3) * 200 / height.  Its physical width is constant.
CPC_PHYS_WIDTH = 267


def _fit(im, crop, art_rows, mode):
    from PIL import Image
    import zxart
    width, _inks, _ppb = mode_info(mode)
    height = 8 * int(art_rows)
    w, h = im.size
    aspect = CPC_PHYS_WIDTH / float(height)
    im = im.crop(zxart.band_crop_rect(crop, w, h, aspect))
    if im.size != (width, height):
        im = im.resize((width, height), Image.LANCZOS)
    return im


def _mono_pixels(im, art_rows, ninks):
    """Ordered-dither a luminance image onto the Mode 1 pen ramp.

    Error diffusion (Floyd-Steinberg) resolves the ramp well but produces
    high-frequency noise that compresses poorly: the CPC 6128 only has four
    extra 16K banks for every art and song, and a full game can overflow them.
    A 4x4 Bayer matrix keeps the same number of levels with a regular pattern
    that ZX0 packs into far fewer bytes.
    """
    import zxart
    width, _inks, _ppb = mode_info(1)
    height = 8 * int(art_rows)
    pix = im.convert("L").load()
    matrix = zxart.BAYER4
    size = len(matrix)
    max_level = ninks - 1
    out = []
    for y in range(height):
        row = matrix[y % size]
        for x in range(width):
            value = pix[x, y] / 255.0 * max_level
            level = int(value + row[x % size])
            out.append(max(0, min(max_level, level)))
    return out


def _convert(im, conv=None, options=None, text_ink=None, highlight_ink=None,
             text_bg=None):
    """Return ``(preview_rgb_image, ink_bytes, palette)`` for a source image.

    Mode 1 converts the picture to an ordered-dithered black/grey/white
    luminance ramp whose four pens are shared with the text.  In Modes 0 and 2
    palette entry 0 is the configured text background, and the last two entries
    hold the configured highlight and text inks (Mode 2 only has room for the
    text ink).  The runtime clears the title/text pane to pen 0, so entry 0
    must be the background.  The image is quantised against the full palette,
    so the picture may use these entries too and keeps every ink the mode
    offers.
    """
    from PIL import Image
    import zxart

    conv = conv or {}
    options = options or {}
    if text_ink is None or highlight_ink is None or text_bg is None:
        default_text, default_hi, default_bg = text_colours(None)
        if text_ink is None:
            text_ink = default_text
        if highlight_ink is None:
            highlight_ink = default_hi
        if text_bg is None:
            text_bg = default_bg
    text_ink = int(text_ink) % len(CPC_PALETTE)
    highlight_ink = int(highlight_ink) % len(CPC_PALETTE)
    text_bg = int(text_bg) % len(CPC_PALETTE)
    mode = _norm_mode(options.get("mode"))
    art_rows = int(options.get("art_rows") or DEFAULT_ART_ROWS)
    if art_rows < 1:
        art_rows = DEFAULT_ART_ROWS
    width, ninks, _ppb = mode_info(mode)

    im = _fit(im, conv.get("crop"), art_rows, mode)
    adj = conv.get("adjust") or {}
    im = zxart.preprocess(im, adj.get("saturation", 1.0),
                          adj.get("contrast", 1.0),
                          adj.get("brightness", 1.0),
                          adj.get("gamma", 1.0))

    if mode == 1:
        # A mono picture needs dithering to resolve more than the three neutral
        # inks, so ignore the (default-off) colour dither and always ordered-
        # dither: it compresses far better than error diffusion.
        inks = list(MONO_INKS)
        raw_ink = _mono_pixels(im, art_rows, ninks)
    else:
        selected = _select_inks(im, ninks)
        if ninks > 2:
            fixed = [highlight_ink, text_ink]
            keep = [i for i in selected
                    if i not in fixed and i != text_bg][:ninks - 3]
            inks = [text_bg] + keep + fixed
        else:
            keep = [i for i in selected
                    if i != text_ink and i != text_bg][:ninks - 2]
            inks = [text_bg] + keep + [text_ink]
        dither_mode = str(conv.get("dither") or "off").lower()
        dither = (Image.Dither.NONE if dither_mode == "off"
                  else Image.Dither.FLOYDSTEINBERG)
        flat = []
        for i in range(256):
            flat.extend(CPC_PALETTE[inks[i % ninks]])
        pal_img = Image.new("P", (1, 1))
        pal_img.putpalette(flat)
        q = im.quantize(palette=pal_img, dither=dither)
        raw_ink = [int(v) % ninks for v in q.getdata()]

    # Rebuild a clean RGB preview from the normalised ink indices.
    out = Image.new("RGB", (width, 8 * art_rows))
    out.putdata([CPC_PALETTE[inks[v]] for v in raw_ink])
    if out.size != (CPC_PHYS_WIDTH, 8 * art_rows):
        out = out.resize((CPC_PHYS_WIDTH, 8 * art_rows), Image.NEAREST)
    blob = bytes([ninks]) + bytes(inks) + _pack(raw_ink, mode, art_rows)
    return out, blob, inks


def _pack(pixels, mode, art_rows):
    """Pack a width x (8*art_rows) ink grid into CPC screen-order chunks.

    Mode 1 interleaves the two bitplanes across a byte: pixel 0 uses bits
    7/3, pixel 1 bits 6/2, pixel 2 bits 5/1 and pixel 3 bits 4/0.  Mode 0
    interleaves the four bitplanes: pixel 0 uses 7/3/5/1 and pixel 1 uses
    6/2/4/0 for ink bits 0..3.  Mode 2 is one bit per pixel.
    """
    width, _inks, ppb = mode_info(mode)
    out = bytearray()
    for blk in range(8):
        for r in range(int(art_rows)):
            y = r * 8 + blk
            base = y * width
            if mode == 1:
                for x in range(0, width, 4):
                    v0 = pixels[base + x]
                    v1 = pixels[base + x + 1]
                    v2 = pixels[base + x + 2]
                    v3 = pixels[base + x + 3]
                    out.append(((v0 & 2) << 6) | ((v1 & 2) << 5)
                               | ((v2 & 2) << 4) | ((v3 & 2) << 3)
                               | ((v0 & 1) << 3) | ((v1 & 1) << 2)
                               | ((v2 & 1) << 1) | (v3 & 1))
            elif mode == 0:
                for x in range(0, width, 2):
                    p0 = pixels[base + x]
                    p1 = pixels[base + x + 1]
                    out.append(((p0 & 1) << 7) | ((p1 & 1) << 6)
                               | ((p0 & 4) << 3) | ((p1 & 4) << 2)
                               | ((p0 & 2) << 2) | ((p1 & 2) << 1)
                               | ((p0 & 8) >> 2) | ((p1 & 8) >> 3))
            else:
                for x in range(0, width, 8):
                    value = 0
                    for k in range(8):
                        value = (value << 1) | pixels[base + x + k]
                    out.append(value)
    return bytes(out)


def blank_blob(mode=DEFAULT_MODE, art_rows=DEFAULT_ART_ROWS,
               text_ink=26, highlight_ink=None, text_bg=0):
    """A background band blob with the mode's palette."""
    mode = _norm_mode(mode)
    width, ninks, ppb = mode_info(mode)
    if mode == 1:
        inks = list(MONO_INKS)
    else:
        inks = [0] * ninks
        inks[0] = int(text_bg)
        if ninks > 2 and highlight_ink is not None:
            inks[-2] = int(highlight_ink)
        inks[-1] = int(text_ink)
    return (bytes([ninks]) + bytes(inks)
            + bytes(width // ppb * 8 * int(art_rows)))


def band(im, conv=None, options=None, text_ink=None, highlight_ink=None,
         text_bg=None):
    """Return ``(rgb_image, blob, palette)`` for an in-memory source image."""
    return _convert(im, conv, options, text_ink, highlight_ink, text_bg)


def art_blob(path, conv=None, options=None, text_ink=None, highlight_ink=None,
             text_bg=None):
    """Return the compiled CPC art blob for ``path`` (or None if unreadable)."""
    from PIL import Image
    if not path:
        return None
    try:
        im = Image.open(path).convert("RGB")
    except Exception:                          # noqa: BLE001 - missing/corrupt
        return None
    _preview, blob, _palette = _convert(im, conv, options, text_ink,
                                        highlight_ink, text_bg)
    return blob


def preview_image(path, conv=None, options=None, text_ink=None,
                  highlight_ink=None, text_bg=None):
    from PIL import Image
    try:
        im = Image.open(path).convert("RGB")
    except Exception:                          # noqa: BLE001 - missing/corrupt
        return None
    image, _blob, _palette = _convert(im, conv, options, text_ink,
                                      highlight_ink, text_bg)
    return image


def preview_bytes(path, conv=None, options=None, text_ink=None,
                  highlight_ink=None, text_bg=None):
    img = preview_image(path, conv, options, text_ink, highlight_ink, text_bg)
    if img is None:
        return None
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
