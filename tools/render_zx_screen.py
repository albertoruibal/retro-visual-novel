#!/usr/bin/env python3
"""Render a ZX Spectrum screen file (6912 bytes) to PNG, and compare it with
the source asset intro.png used to generate intro_screen.h."""
import sys
from PIL import Image

def render(data, out_png, scale=4):
    img = Image.new('RGB', (256, 192), (0, 0, 0))
    px = img.load()
    FLASH = 0x80
    BRIGHT = 0x40
    ink = paper = (0,) * 3
    pal = [(0,0,0),(0,0,205),(205,0,0),(205,0,205),(0,205,0),(0,205,205),
           (205,0,0),(205,205,0),(205,205,0),(190,255,190),(255,255,255)]  # placeholder
    palette = [
        (0,0,0),(0,0,215),(215,0,0),(215,0,215),(0,215,0),(0,215,215),
        (215,215,0),(215,215,215),(0,0,255),(255,0,255),(255,255,255)]
    for row in range(192):
        arow = ((row & 0xC0) >> 3) | ((row & 0x38) >> 3) | ((row & 7) << 3)
        # standard: attr row = row // 8  (attribute rows are sequential)
        arow = row // 8
        acol_base = 0x5800 + (arow * 32) - 0x4000  # attr offset within blob
        pix_off = 0x4000 + ((row & 7) << 8) + ((row & 0x38) << 2) + ((row & 0xC0) << 5) - 0x4000
        attr_off = 0x1800 + arow * 32
        for cx in range(32):
            attr = data[attr_off + cx]
            ink_i = attr & 7
            paper_i = (attr >> 3) & 7
            bright = attr & 0x40
            def col(i):
                r, g, b = palette[i]
                f = 1.0 if not bright else 1.45
                return (min(255,int(r*f)), min(255,int(g*f)), min(255,int(b*f)))
            ink_c = col(ink_i)
            paper_c = col(paper_i)
            for bx in range(8):
                byte = data[pix_off + cx]
                bit = (byte >> (7 - bx)) & 1
                x = cx * 8 + bx
                px[x, row] = ink_c if bit else paper_c
    img = img.resize((256*scale, 192*scale), Image.NEAREST)
    img.save(out_png)
    print("wrote", out_png)

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    render(data, sys.argv[2])