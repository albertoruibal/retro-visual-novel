#!/usr/bin/env python3
"""Build a 128K .SNA snapshot for a game's banked adventure.

Layout (standard 128K SNA):
    27-byte header
    49152 bytes 0x4000..0xFFFF  (screen + fixed 0x8000 region + home bank 0)
    4 bytes     128K extension: PC, port 0x7FFD, TR-DOS
    5 x 16384   banks 1, 3, 4, 6, 7

Sources (all inside the game folder, ``games/<slug>/``):
    build/adventure.bin             main image, org 0x8000 (fixed region + bank 0)
    build/adventure_NIRVANAP.bin    engine, org 0xDC03 (bank 0, above the main image)
    build/scene_banks/*.bin         scene banks (magic byte first), padded to 16K

Usage: make_sna.py [<game>] [out.sna]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamestore

BANK_ORDER = [1, 3, 4, 6, 7]
ENTRY = 0x8000
SP = 0x7FF7


def sna_header():
    """27-byte 128K SNA header: only I, SP, IM, border and IFF2 matter here."""
    h = bytearray(27)
    h[0] = 0x3F             # I (unused; IM 1)
    h[19] = 0xFF            # IFF2 (interrupts enabled)
    h[23] = SP & 0xFF       # SP low
    h[24] = SP >> 8         # SP high
    h[25] = 1               # IM 1
    h[26] = 0               # border black
    return bytes(h)


def build(gdir, slug, out_path):
    bdir = os.path.join(gdir, gamestore.BUILD_NAME)
    main_bin = open(os.path.join(bdir, "adventure.bin"), "rb").read()
    engine_path = os.path.join(bdir, "adventure_NIRVANAP.bin")
    if not os.path.exists(engine_path):
        sys.exit(f"missing {engine_path}; the ZX build generates it")
    engine = open(engine_path, "rb").read()

    hdr = sna_header()
    img = bytearray(0xC000)                     # 0x4000..0xFFFF

    # clear screen (pixels 0x4000.., attrs 0x5800..) and set plain attrs
    img[0x0000:0x1800] = bytes(0x1800)
    img[0x1800:0x1B00] = bytes([0x38]) * 0x300

    # main image: org 0x8000, fills fixed region and the start of bank 0
    off = 0x8000 - 0x4000
    img[off:off + len(main_bin)] = main_bin

    # NIRVANAP+ engine at its fixed org
    eoff = 0xDC03 - 0x4000
    img[eoff:eoff + len(engine)] = engine

    # 128K extension: PC, port 0x7FFD (ROM1 + bank 0), TR-DOS
    ext = bytearray(4)
    ext[0] = ENTRY & 0xFF
    ext[1] = ENTRY >> 8
    ext[2] = 0x10                              # bit4=ROM1, bank 0
    ext[3] = 0

    out = bytearray(hdr) + img + ext
    for bn in BANK_ORDER:
        path = os.path.join(bdir, "scene_banks", f"bank{bn}.bin")
        data = open(path, "rb").read() if os.path.exists(path) else b""
        if len(data) > 0x4000:
            sys.exit(f"bank{bn} too big")
        out += data + bytes(0x4000 - len(data))

    open(out_path, "wb").write(out)
    sys.stderr.write(f"sna: {out_path} ({len(out)} bytes)\n")


def main():
    args = sys.argv[1:]
    slug = None
    if args and not args[0].endswith(".sna"):
        slug = args.pop(0)
    game = gamestore.resolve(slug)
    if game is None:
        sys.exit(f"no such game: {slug!r} (see 'games/')")
    out_path = (args[0] if args
                else os.path.join(game["dir"], f"{game['slug']}.sna"))
    build(game["dir"], game["slug"], out_path)


if __name__ == "__main__":
    main()
