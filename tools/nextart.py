#!/usr/bin/env python3
"""ZX Spectrum Next Layer 2 art conversion.

The story band is the same 256 x (8 * ``art_rows``) rectangle as the ZX target,
but each pixel is an 8-bit index into a 256-colour Next palette.  The build
stores the band as two/three 16K banks (the generator pads it) and the palette
in a separate bank, so the runtime only has to select the Layer 2 bank and
upload 256 RGB333 entries.

The converter deliberately reuses ``zxart``'s crop and source-adjustment code
so the Art tab's crop box and colour controls behave the same on every target.
Pillow's median-cut quantiser picks the palette; ``dither: off`` uses a hard
nearest snap and any other non-off dither setting uses Floyd-Steinberg.
"""
from __future__ import annotations

import io

from PIL import Image

import zxart


def _art_rows(options):
    rows = int((options or {}).get("art_rows") or 10)
    return max(8, min(16, rows if rows % 2 == 0 else rows - 1))


def _conversion(conv):
    conv = conv or {}
    adjust = conv.get("adjust") or {}
    return {
        "crop": conv.get("crop"),
        "dither": conv.get("dither", "off"),
        "palette": conv.get("palette", "none"),
        "palette_colors": int(conv.get("palette_colors") or 256),
        "saturation": adjust.get("saturation", 1.0),
        "contrast": adjust.get("contrast", 1.0),
        "brightness": adjust.get("brightness", 1.0),
        "gamma": adjust.get("gamma", 1.0),
    }


def _band(im, conv, rows):
    """Fit the source to the art band and apply the shared source controls."""
    tile_rows = max(1, rows // 2)
    im = zxart._fit_band(im, conv.get("crop"), tile_rows)
    return zxart.preprocess(
        im, conv.get("saturation", 1.0), conv.get("contrast", 1.0),
        conv.get("brightness", 1.0), conv.get("gamma", 1.0))


def _spectrum_palette():
    pal = []
    for rgb in zxart.SPEC:
        pal.extend(rgb)
    return pal + [0] * (768 - len(pal))


def _quantise(im, conv):
    """Return a P-mode image (<=256 colours) plus its RGB palette."""
    mode = conv.get("palette", "none")
    n = 256
    if mode == "spectrum":
        n = 16
    elif mode == "adaptive":
        n = max(2, min(256, conv.get("palette_colors", 256)))
    dither = (Image.Dither.NONE if conv.get("dither", "off") == "off"
              else Image.Dither.FLOYDSTEINBERG)
    if mode == "spectrum":
        pal = Image.new("P", (1, 1))
        pal.putpalette(_spectrum_palette())
        q = im.quantize(palette=pal, dither=dither)
    else:
        q = im.quantize(colors=n, method=Image.Quantize.MEDIANCUT,
                        dither=dither)
    return q


def _palette_bytes(q):
    raw = q.getpalette() or []
    raw = raw[:768] + [0] * (768 - len(raw[:768]))
    out = bytearray()
    for i in range(256):
        r, g, b = raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]
        r3, g3, b3 = r >> 5, g >> 5, b >> 5
        out.append(((r3 << 5) | (g3 << 2) | (b3 >> 1)) & 0xFF)
        out.append(b3 & 1)
    return bytes(out)


def _pixels(q, rows):
    data = bytes(q.tobytes())
    expected = 256 * (8 * rows)
    if len(data) < expected:
        data += bytes(expected - len(data))
    return data[:expected]


def art_blob(path, conv, options):
    """Convert one source image to ``(pixel_bytes, palette_bytes)``."""
    conv = _conversion(conv)
    rows = _art_rows(options)
    im = Image.open(path).convert("RGB")
    im = _band(im, conv, rows)
    q = _quantise(im, conv)
    return _pixels(q, rows), _palette_bytes(q)


def blank_blob(options):
    rows = _art_rows(options)
    return bytes(256 * (8 * rows)), bytes(512)


def preview_bytes(path, conv, options, game=None):
    conv = _conversion(conv)
    rows = _art_rows(options)
    im = Image.open(path).convert("RGB")
    im = _band(im, conv, rows)
    q = _quantise(im, conv)
    out = io.BytesIO()
    q.convert("RGB").save(out, "PNG")
    return out.getvalue()
