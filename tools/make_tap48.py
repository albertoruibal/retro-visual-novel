#!/usr/bin/env python3
"""Append the 48K flat scene block to the appmake-produced adventure TAP.

The 48K build has no paged banks: tools/gen_scenes.py writes the compressed
scene store, padded to FLAT_DATA_SIZE, as ``build/scene_flat.bin``.
src/zx/loader48.asm reads that one headerless block into lower RAM at 0x6000
with the ROM LD-BYTES routine. Art and inventory are linked into the main
image, so they are already in the base TAP block.

Usage: make_tap48.py <base.tap> <out.tap> [<game>]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamestore
from make_tap import block


def flat_size(gdir):
    path = os.path.join(gdir, gamestore.BUILD_NAME, "scene_data.h")
    try:
        txt = open(path).read()
    except OSError:
        return None
    m = re.search(r"^#define\s+FLAT_DATA_SIZE\s+(\d+)", txt, re.M)
    return int(m.group(1)) if m else None


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit("usage: make_tap48.py <base.tap> <out.tap> [<game>]")
    base, out_path = args[0], args[1]
    slug = args[2] if len(args) > 2 else None
    game = gamestore.resolve(slug)
    if game is None:
        sys.exit(f"no such game: {slug!r} (see 'games/')")
    gdir = game["dir"]
    path = os.path.join(gdir, gamestore.BUILD_NAME, "scene_flat.bin")
    try:
        data = open(path, "rb").read()
    except OSError:
        sys.exit(f"missing {path}; the 48K build generates it")
    size = flat_size(gdir) or len(data)
    if len(data) > size:
        sys.exit(f"scene_flat.bin is {len(data)}B, exceeding FLAT_DATA_SIZE "
                 f"{size}B")
    data = data + bytes(size - len(data))

    out = bytearray(open(base, "rb").read())
    out += block(255, data)
    open(out_path, "wb").write(out)
    sys.stderr.write(f"tap: flat block {len(data)}B\n")
    sys.stderr.write(f"wrote {out_path} ({len(out)} bytes)\n")


if __name__ == "__main__":
    main()
