#!/usr/bin/env python3
"""Oric Atmos HIRES art conversion shared by the build and the editor.

The Oric's HIRES bitmap is 240x200: 40 bytes per row, six one-bit pixels per
byte.  A pixel byte must have bit 6 set; bits 5..0 are the pixels left to
right.  This module fits an art source to a 240 x (8*art_rows) band, applies
the shared colour adjustments and dither setting, and packs the result as
40 bytes per row.  Colour is monochrome (white ink on black paper); the
serial-attribute colour cells cost screen width, so the initial Oric target
keeps the full 40-column screen.  Because the screen is 1-bit, `dither: off`
becomes an ordered dither (see ``zxart.mono_dither``): a hard threshold would
throw away every mid-tone.
"""
from __future__ import annotations

import io

import zxart

WIDTH = 240
COLS = 40
DEFAULT_ART_ROWS = 8
ART_ROWS = (8, 10, 12)
INK = 7
PAPER = 0


def text_colours(game=None):
    """Return the Oric ink/highlight/paper values (monochrome)."""
    return INK, INK, PAPER


def _fit(im, crop, art_rows):
    """Crop/scale a source to the 240 x (8*art_rows) HIRES band."""
    from PIL import Image
    art_rows = int(art_rows)
    height = 8 * art_rows
    w, h = im.size
    box = im.crop(zxart.band_crop_rect(crop, w, h, WIDTH / float(height)))
    target = (WIDTH, height)
    if box.size != target:
        box = box.resize(target, Image.LANCZOS)
    return box


def _mono_grid(im, mode):
    """Dither a prepared image to a 0/1 ink grid using the shared schemes.

    ``off`` resolves to an ordered dither (``zxart.mono_dither``) because a
    1-bit screen cannot hold a mid-tone.
    """
    gray = im.convert("L")
    w, h = gray.size
    px = gray.load()
    mode = zxart.mono_dither(mode)
    out = [[0] * w for _ in range(h)]
    if mode in zxart._DIFFUSE:
        err = [[float(px[x, y]) for x in range(w)] for y in range(h)]
        wdiv, taps = zxart._DIFFUSE[mode]
        for y in range(h):
            for x in range(w):
                value = err[y][x]
                ink = 255 if value >= 128 else 0
                out[y][x] = 1 if ink else 0
                delta = value - ink
                for dx, dy, weight in taps:
                    x2, y2 = x + dx, y + dy
                    if 0 <= x2 < w and 0 <= y2 < h:
                        err[y2][x2] += delta * weight / wdiv
        return out
    grid = zxart._threshold_grid(mode, None)
    gh = len(grid)
    for y in range(h):
        row = grid[y % gh]
        for x in range(w):
            out[y][x] = 1 if (px[x, y] / 255.0) > row[x] else 0
    return out


def _pack(grid, art_rows):
    """Pack a 0/1 grid into Oric HIRES bytes (bit 6 set, bit 5 leftmost)."""
    height = 8 * int(art_rows)
    out = bytearray(COLS * height)
    for y in range(height):
        row = grid[y]
        base = y * COLS
        for bx in range(COLS):
            value = 0
            for bit in range(6):
                x = bx * 6 + bit
                if x < len(row) and row[x]:
                    value |= 1 << (5 - bit)
            out[base + bx] = 0x40 | value
    return bytes(out)


def art_blob(im, conv=None, art_rows=DEFAULT_ART_ROWS):
    """Convert one source image to a packed Oric HIRES band."""
    from PIL import Image
    if isinstance(im, str):
        im = Image.open(im).convert("RGB")
    else:
        im = im.convert("RGB")
    conv = conv or {}
    art_rows = int(art_rows)
    im = _fit(im, conv.get("crop"), art_rows)
    adjust = conv.get("adjust") or {}
    im = zxart.preprocess(im, adjust.get("saturation", 1.0),
                          adjust.get("contrast", 1.0),
                          adjust.get("brightness", 1.0),
                          adjust.get("gamma", 1.0))
    im = zxart._apply_palette(im, conv.get("palette", zxart.DEFAULT_PALETTE),
                              conv.get("palette_colors"))
    grid = _mono_grid(im, conv.get("dither", zxart.DEFAULT_DITHER))
    return _pack(grid, art_rows), 0


def blank_blob(art_rows=DEFAULT_ART_ROWS):
    """A blank 0x40-filled band."""
    return bytes((0x40,)) * (COLS * 8 * int(art_rows)), 0


def band(im, conv=None, art_rows=DEFAULT_ART_ROWS):
    """Return the band as a 240 x (8*art_rows) RGB image."""
    from PIL import Image
    blob, _ = art_blob(im, conv, art_rows)
    art_rows = int(art_rows)
    img = Image.new("RGB", (WIDTH, 8 * art_rows), (0, 0, 0))
    px = img.load()
    for y in range(8 * art_rows):
        for bx in range(COLS):
            value = blob[y * COLS + bx]
            for bit in range(6):
                if value & (1 << (5 - bit)):
                    px[bx * 6 + bit, y] = (255, 255, 255)
    return img


def preview_image(path, conv=None, options=None, game=None):
    from PIL import Image
    options = options or {}
    art_rows = int(options.get("art_rows") or DEFAULT_ART_ROWS)
    try:
        im = Image.open(path).convert("RGB")
    except Exception:                          # noqa: BLE001 - missing/corrupt
        return None
    return band(im, conv, art_rows)


def preview_bytes(path, conv=None, options=None, game=None):
    img = preview_image(path, conv, options, game)
    if img is None:
        return None
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
