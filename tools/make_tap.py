#!/usr/bin/env python3
"""Append the scene-bank blocks to the appmake-produced adventure TAP.

The build first merges the fixed-address NIRVANAP+ engine into the main image
and runs `z88dk-appmake +zx` on it (loader + main CODE block, verified format).
This script then appends one headerless 16K data block per scene bank; the
game reads them at startup with the ROM LD-BYTES routine (src/zx/loader.asm),
in the order given by the game's ``build/scene_banks.asm`` [_scene_bank_list].

Usage: make_tap.py <base.tap> <out.tap> [<game>]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamestore

BANK_SIZE = 0x4000


def block(flag, payload):
    body = bytes([flag]) + payload
    chk = 0
    for b in body:
        chk ^= b
    return (len(body) + 1).to_bytes(2, "little") + body + bytes([chk])


def bank_order(gdir, bdir=None):
    bdir = bdir or os.path.join(gdir, gamestore.BUILD_NAME)
    txt = open(os.path.join(bdir, "scene_banks.asm")).read()
    m = re.search(r"_scene_bank_list:(.*)", txt, re.S)
    nums = [int(x, 0) for x in re.findall(r"defb\s+(\S+)", m.group(1))]
    return [n for n in nums if n != 0xFF]


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit("usage: make_tap.py <base.tap> <out.tap> [<game>]")
    base, out_path = args[0], args[1]
    slug = args[2] if len(args) > 2 else None
    game = gamestore.resolve(slug, gamestore.env_variant())
    if game is None:
        sys.exit(f"no such game: {slug!r} (see 'games/')")
    gdir = game["dir"]
    bdir = game["bdir"]

    out = bytearray(open(base, "rb").read())
    for bn in bank_order(gdir, bdir):
        path = os.path.join(bdir, "scene_banks", f"bank{bn}.bin")
        data = open(path, "rb").read()
        if len(data) > BANK_SIZE:
            sys.exit(f"bank{bn} too big ({len(data)})")
        data = data + bytes(BANK_SIZE - len(data))
        out += block(255, data)
        sys.stderr.write(f"tap: bank{bn} block {len(data)}B\n")

    open(out_path, "wb").write(out)
    sys.stderr.write(f"wrote {out_path} ({len(out)} bytes)\n")


if __name__ == "__main__":
    main()
