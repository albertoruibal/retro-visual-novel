#!/usr/bin/env python3
"""Regenerate vendor/pixeloperator8/font8x8.bin from the vendored TTF.

The font is rendered at 8x scale and each 8x8 block is thresholded at 50%, which recovers the intended 8x8 pixel design
(including accents that sit above the 8px ascender). The output rows are LSB-left. The script also prints the
ACCENT_GLYPHS_8X8 dictionary to paste into tools/gen_scenes.py.

Usage: python3 tools/make_font8.py [--ttf PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TTF = ROOT / "vendor" / "pixeloperator8" / "PixelOperatorMono8.ttf"
DEFAULT_OUT = ROOT / "vendor" / "pixeloperator8" / "font8x8.bin"
SCALE = 8
ACCENTS = {
    "Á": 0x5B, "Ñ": 0x5C, "á": 0x5D, "é": 0x5E, "í": 0x5F, "Ü": 0x60,
    "ü": 0x7B, "ñ": 0x7C, "ó": 0x7D, "ú": 0x7E, "¿": 0x7F,
}


def extract(font, ch):
    """Return the eight LSB-left rows for one glyph."""
    size = 8 * SCALE
    origin = size
    image = Image.new("L", (origin * 3, origin * 3), 0)
    ImageDraw.Draw(image).text((origin, origin), ch, font=font, fill=255)
    rows = []
    for by in range(8):
        value = 0
        for bx in range(8):
            lit = 0
            for y in range(by * SCALE, (by + 1) * SCALE):
                for x in range(bx * SCALE, (bx + 1) * SCALE):
                    if image.getpixel((origin + x, origin + y)) >= 128:
                        lit += 1
            if lit >= SCALE * SCALE / 2:
                value |= 1 << bx
        rows.append(value)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ttf", type=Path, default=DEFAULT_TTF)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    font = ImageFont.truetype(str(args.ttf), 8 * SCALE)
    data = bytes(value for code in range(32, 128)
                 for value in extract(font, chr(code)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(data)
    print(f"wrote {len(data)} bytes to {args.out}")
    print(f"sha256 {hashlib.sha256(data).hexdigest()}")
    print("ACCENT_GLYPHS_8X8 = {")
    for ch, code in ACCENTS.items():
        rows = extract(font, ch)
        values = ", ".join("0x%02X" % row for row in rows)
        print("    0x%02X: [%s],   # %s" % (code, values, ch))
    print("}")


if __name__ == "__main__":
    main()
