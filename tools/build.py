#!/usr/bin/env python3
"""Build a game's ZX adventure (portable replacement for adventure.sh).

One shared engine builds any game under ``games/<slug>/``. The per-game inputs
(``game.md``, ``assets/art``) live in the game folder and the generated
intermediates (``scene_data.h``, ``scene_banks.asm``,
``scene_bankN.asm``, ``scene_flags.txt``, ``adventure.bin``,
``adventure_NIRVANAP.bin``) go under ``games/<slug>/build/``. Only the playable
artifacts (``<slug>.tap``, ``<slug>.sna`` and the other targets' ROM/disk
outputs) stay at the game root.

This is the sh-free driver the editor server spawns; it performs the identical
steps as the old ``tools/adventure.sh`` but uses :mod:`subprocess` directly, so
it runs on Windows and macOS as well as Linux (the old script depended on a
POSIX shell and GNU ``stat -c%s``).

Usage:
    python3 tools/build.py list-targets
    python3 tools/build.py build [game] [target...]
    python3 tools/build.py build [game] --all
    python3 tools/build.py run   [game] [target]

    zcc ... src/zx/*.c src/zx/paging.asm src/zx/loader.asm \
            games/<slug>/build/scene_banks.asm ... -I games/<slug>/build \
            -o <game>/build/adventure.bin
    appmake -> <game>/<slug>.tap (tape) and <game>/<slug>.sna (128K snapshot)
    # 48K: loader48.asm + scene_flat.bin -> <game>/<slug>-48k.tap
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cc65path
import gamestore
import scenefile
import targets
from targets.base import portable_sources
import z88dkpath
# The target plugins import this module lazily by name; make sure that name
# resolves to the running script as well as to a normal import.
sys.modules.setdefault("build", sys.modules[__name__])

ROOT = gamestore.ROOT
BANK = 0x4000


def _fwd(p):
    """Normalise path separators for the z88dk tools.

    z88dk's Windows binaries accept forward slashes, so passing them avoids the
    backslash quoting pitfalls inside the compiler/assembler argument parser.
    """
    return str(p).replace("\\", "/")


def _settings_path():
    """The editor settings file, shared by the CLI and the desktop app."""
    path = os.environ.get("RVN_SETTINGS") or os.environ.get("ZXAD_SETTINGS")
    if path:
        return path
    if sys.platform == "darwin":
        cfg = os.path.join(os.path.expanduser("~"), "Library",
                           "Application Support")
    elif os.name == "nt":
        cfg = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        cfg = os.environ.get("XDG_CONFIG_HOME") or \
            os.path.join(os.path.expanduser("~"), ".config")
    path = os.path.join(cfg, "retro-visual-novel", "settings.json")
    for old in (os.path.join(cfg, "zx-novel", "settings.json"),
                os.path.join(cfg, "zxadventure", "settings.json")):
        if os.path.exists(path):
            break
        if os.path.exists(old):
            path = old
    return path


def _settings_value(key):
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            val = json.load(f).get(key)
    except Exception:                          # noqa: BLE001 - missing/garbled
        return ""
    return str(val).strip() if val else ""


def _settings_z88dk():
    """The editor's saved z88dk_path, so a CLI build honours the UI setting.

    The editor server passes ``$Z88DK`` directly, so this is only a fallback
    for running ``tools/build.py`` on its own.
    """
    return _settings_value("z88dk_path")


def _settings_cc65():
    """The editor's saved cc65_path (Commodore 64 / NES builds)."""
    return _settings_value("cc65_path")


def zcc_config(z88dk):
    """zcc's config directory for a toolchain tree.

    A source/Docker install keeps it in ``lib/config``; the snap relocates the
    whole kit under ``share/z88dk``. Prefer whichever actually has the target
    config, so both layouts work without the user setting ``ZCCCFG``.
    """
    for rel in (("share", "z88dk", "lib", "config"), ("lib", "config")):
        path = os.path.join(z88dk, *rel)
        if os.path.isfile(os.path.join(path, "zx.cfg")):
            return path
    return os.path.join(z88dk, "lib", "config")


def build_env():
    """Environment with the z88dk toolchain on PATH (mirrors adventure.sh).

    An explicit ``$Z88DK`` or the editor's saved path wins; otherwise the
    Snap install is detected automatically before the ``/tmp/z88dk`` fallback.
    """
    env = dict(os.environ)
    z88dk = env.get("Z88DK") or _settings_z88dk() or z88dkpath.default_root()
    env["Z88DK"] = z88dk
    env["ZCCCFG"] = zcc_config(z88dk)
    env["PATH"] = os.path.join(z88dk, "bin") + os.pathsep + env.get("PATH", "")
    cc65 = env.get("CC65") or _settings_cc65() or cc65path.detected()
    if cc65:
        env["CC65"] = cc65
        os.environ["CC65"] = cc65
        env["PATH"] = cc65path.bin_dir(cc65) + os.pathsep + env["PATH"]
    return env


def run(cmd, env, cwd=None, stdout=None):
    """Run one step, streaming its output; stop the build if it fails."""
    proc = subprocess.run(cmd, cwd=cwd or ROOT, env=env, stdout=stdout)
    if proc.returncode != 0:
        sys.stderr.write("build step failed: %s\n" % " ".join(cmd))
        raise SystemExit(proc.returncode)


def _py():
    """The interpreter to run the sibling tools with (portable/bundled safe)."""
    return sys.executable or "python3"


def stage_inputs(dest, sources):
    """Copy build inputs flat into ``dest``; return their basenames.

    Generated port asm names bank images by a path relative to ``ROOT``. Those
    paths may contain spaces (the AppImage mount) and are relative to the
    normal build cwd, so rewrite each ``BINARY``/``INCBIN`` to the flat copy's
    basename. Callers then run zcc with ``cwd=dest`` and relative names, which
    also avoids zcc mangling source paths that contain spaces.
    """
    names = []
    for src in sources:
        if not src or not os.path.exists(src):
            continue
        name = os.path.basename(src)
        dst = os.path.join(dest, name)
        if name.endswith(".asm"):
            with open(src, encoding="utf-8") as f:
                text = f.read()

            def repl(match):
                rel = match.group(2).replace("\\", "/")
                path = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
                base = os.path.basename(rel)
                shutil.copyfile(path, os.path.join(dest, base))
                return match.group(1) + '"' + base + '"'

            text = re.sub(r'(?m)^(\s*(?:BINARY|INCBIN)\s+)"([^"]+)"',
                          repl, text)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            shutil.copyfile(src, dst)
        names.append(name)
    return names


def guard_map(gdir):
    """Paging routines must stay below 0xC000, or paging overwrites itself."""
    mp = os.path.join(gdir, gamestore.BUILD_NAME, "adventure.map")
    if not os.path.exists(mp):
        return
    txt = open(mp).read()
    bad = []
    for sym in ("_paged_unpack", "_zx0_unpack", "_load_banks",
                "_scene_bank_list"):
        m = re.search(rf"^{sym}\s+= \$([0-9A-Fa-f]+)", txt, re.M)
        if m and int(m.group(1), 16) >= 0xC000:
            bad.append(sym)
    if bad:
        raise SystemExit(
            "home-region overflow: %s linked at or above 0xC000 (bank 0), "
            "so paging would overwrite its own code. Shrink the game "
            "(fewer/shorter scenes, text, options or arts)." % ", ".join(bad))


def _scene_define(gdir, key):
    """Read an integer ``#define key N`` from the game's scene_data.h, or None.

    gen_scenes.py emits the per-game sizes there (ART_WS_SIZE, SCENE_WS_SIZE,
    ART_LINES, ...) and we pass the assembler ones; absent means None.
    """
    path = os.path.join(gdir, gamestore.BUILD_NAME, "scene_data.h")
    try:
        txt = open(path).read()
    except OSError:
        return None
    m = re.search(r"^#define\s+%s\s+(\d+)" % re.escape(key), txt, re.M)
    return int(m.group(1)) if m else None


def _engine_config(rows):
    """The vendored NIRVANA+ config with ``__NIRVANAP_TOTAL_ROWS`` set to rows.

    The engine races rows 1..TOTAL_ROWS, so a game's ``## zx128`` ``art_rows:``
    becomes TOTAL_ROWS (the internal scene_data.h name is ART_LINES). Both the
    z80asm ``defc`` and the m4 ``define`` line in config_private.inc are patched;
    the m4 line is what the Z88DK_FOR loops read (see vendor/nirvanap/README).
    """
    path = os.path.join(ROOT, "vendor", "nirvanap", "config_private.inc")
    src = open(path).read()
    src, n1 = re.subn(r"(defc\s+__NIRVANAP_TOTAL_ROWS\s*=\s*)\d+",
                      lambda m: m.group(1) + str(rows), src)
    src, n2 = re.subn(r"(define\(`__NIRVANAP_TOTAL_ROWS',\s*)\d+",
                      lambda m: m.group(1) + str(rows), src)
    if not (n1 and n2):
        raise SystemExit(
            "vendor/nirvanap/config_private.inc: cannot patch "
            "__NIRVANAP_TOTAL_ROWS (expected a defc and a define line)")
    return src


def _map_addr(gdir, symbol):
    """The linked address of one symbol from the game's adventure.map."""
    path = os.path.join(gdir, gamestore.BUILD_NAME, "adventure.map")
    try:
        txt = open(path).read()
    except OSError:
        return None
    m = re.search(rf"^{re.escape(symbol)}\s*=\s*\$([0-9A-Fa-f]+)", txt, re.M)
    return int(m.group(1), 16) if m else None


def write_engine_blob(gdir, engdir, engine_asm, asm_sources, env):
    """Rebuild the standalone NIRVANA+ image merged into the TAP/SNA.

    `zcc` links the engine into the game's address space but omits it from
    adventure.bin, so the TAP/SNA need a raw image from org 0xDC03. Regenerate
    it every build from the same patched engine that was linked (including the
    wrappers the game actually references); using a per-game stale file here
    kept the old TOTAL_ROWS after an art_rows change.
    """
    head = _map_addr(gdir, "__NIRVANAP_head")
    tail = _map_addr(gdir, "__code_nirvanap_tail")
    if head is None or tail is None:
        raise SystemExit(
            "adventure.map is missing the NIRVANA+ bounds "
            "(__NIRVANAP_head / __code_nirvanap_tail); cannot build the "
            "engine image")
    if head != 0xDC03:
        raise SystemExit(
            "NIRVANA+ engine head is 0x%04X, expected 0xDC03" % head)

    wrappers = []
    for name, symbol in (
            ("NIRVANAP_start.asm", "NIRVANAP_start"),
            ("NIRVANAP_drawT_raw_callee.asm", "NIRVANAP_drawT_raw_callee"),
            ("NIRVANAP_fillT_raw_callee.asm", "NIRVANAP_fillT_raw_callee")):
        if name not in asm_sources:
            continue
        addr = _map_addr(gdir, symbol)
        if addr is not None:
            wrappers.append((addr, name))
    wrappers.sort()

    out = os.path.join(gdir, gamestore.BUILD_NAME, "adventure_NIRVANAP.bin")
    names = [engine_asm] + [name for _addr, name in wrappers]
    # z80asm -b writes one image per section, named <prefix>_<SECTION>.bin;
    # the NIRVANAP section image already contains the linked wrappers and
    # starts at org 0xDC03. The empty <prefix> file is not the image.
    prefix = os.path.join(engdir, "engine_blob")
    section = prefix + "_NIRVANAP.bin"
    run(["z88dk-z80asm", "-b", "-D__CLASSIC=1", "-o" + _fwd(prefix), *names],
        env, cwd=engdir)
    if not os.path.exists(section):
        raise SystemExit("z88dk-z80asm did not write %s" % section)
    blob = open(section, "rb").read()
    expected = tail - head
    if len(blob) != expected:
        raise SystemExit(
            "NIRVANA+ engine image is %d bytes but the linked map needs %d "
            "(0x%04X..0x%04X); the engine sources and the game link disagree"
            % (len(blob), expected, head, tail))
    if len(blob) > 0x10000 - head:
        raise SystemExit("NIRVANA+ engine image overruns bank 0")
    with open(out, "wb") as f:
        f.write(blob)
    try:
        os.remove(prefix)
    except OSError:
        pass
    return out


def merge_engine(gdir):
    """Merge the fixed-address NIRVANA+ engine into the main image."""
    main = bytearray(open(os.path.join(gdir, gamestore.BUILD_NAME,
                                       "adventure.bin"), "rb").read())
    engine = os.path.join(gdir, gamestore.BUILD_NAME, "adventure_NIRVANAP.bin")
    if not os.path.exists(engine):
        raise SystemExit(
            "missing %s; the ZX build did not generate the NIRVANA+ image"
            % engine)
    eng = open(engine, "rb").read()
    off = 0xDC03 - 0x8000
    if len(main) > off:
        raise SystemExit(
            "home bank overflow: adventure.bin is %d bytes but must be <= %d "
            "(0xDC03-0x8000); the main image would overlap the NIRVANA+ engine. "
            "Shorten scene text, popup messages or item descriptions, or remove "
            "arts to recover RAM."
            % (len(main), off))
    if len(main) < off:
        main += bytes(off - len(main))
    main[off:off + len(eng)] = eng
    open(os.path.join(gdir, gamestore.BUILD_NAME,
                      "adventure_merged.bin"), "wb").write(main)


def memory_report(gdir):
    """How full the 128K machine is once the game is resident."""
    def size(path):
        return os.path.getsize(path) if os.path.exists(path) else 0

    main = size(os.path.join(gdir, gamestore.BUILD_NAME, "adventure.bin"))
    engine = os.path.join(gdir, gamestore.BUILD_NAME, "adventure_NIRVANAP.bin")
    eng = size(engine)
    banks_dir = os.path.join(gdir, gamestore.BUILD_NAME, "scene_banks")
    data = sum(size(os.path.join(banks_dir, "bank%d.bin" % b))
               for b in (1, 3, 4, 6, 7))
    fixed = min(main, BANK)                       # 0x8000..0xBFFF
    home0 = max(main - BANK, (0xDC03 - 0xC000) + eng)
    used = BANK + fixed + home0 + data            # screen + fixed + bank 0 + paged
    total = 8 * BANK
    print("memory: %d/%d bytes (%.1f%% of 128K full)"
          % (used, total, 100.0 * used / total))


def memory_report48(gdir, used, capacity):
    """How full the 48K machine is once the flat game is resident."""
    def size(path):
        return os.path.getsize(path) if os.path.exists(path) else 0

    main = size(os.path.join(gdir, gamestore.BUILD_NAME, "adventure.bin"))
    print("memory: data %d/%d bytes (%.1f%%), main %d/%d bytes (%.1f%% of "
          "0x8000-0xDC03), stack 1024 bytes at 0x7C00"
          % (used, capacity, (100.0 * used / capacity) if capacity else 0,
             main, 0xDC03 - 0x8000,
             100.0 * main / (0xDC03 - 0x8000)))


def _build_zx_model(slug, flat=False):
    """Build the ZX model (banked 128K, or flat 48K). Returns its artifacts."""
    game = gamestore.resolve(slug)
    if game is None:
        raise SystemExit("no such game: %r (see 'games/')" % (slug,))
    gdir = game["dir"]
    bdir = os.path.join(gdir, gamestore.BUILD_NAME)
    os.makedirs(bdir, exist_ok=True)
    env = build_env()
    # Tell the child tools (gen_scenes/make_tap/make_sna) exactly which folder
    # to work on, so an opened game outside games/ resolves for all of them.
    env["RVN_GAME"] = gdir
    env["SCENE_FLAT"] = "1" if flat else "0"
    env["SCENE_TARGET"] = "zx48" if flat else "zx128"
    py = _py()

    # --- generate tables + banks ------------------------------------------
    # Flat mode (48K) concatenates the compressed blobs into one lower-RAM
    # image; banked mode packs them into the 128K's paged banks. Either way the
    # per-art Spectrum btiles come from each art's selected source image.
    run([py, os.path.join(ROOT, "tools", "gen_scenes.py"), gdir], env)

    # --- build the vendored NIRVANA+ engine -------------------------------
    # The engine races attribute rows 1..TOTAL_ROWS, so it is rebuilt per game
    # with TOTAL_ROWS from the ZX target's `art_rows` option (ART_LINES in
    # scene_data.h). A temp config_private.inc, first on the m4 include path,
    # overrides the vendored one so the art band's height matches the
    # generated tables/banks.
    art_lines = _scene_define(gdir, "ART_LINES") or 10
    vendor = os.path.join(ROOT, "vendor", "nirvanap")
    builddir = tempfile.mkdtemp(prefix=".zx-", dir=bdir)
    engdir = os.path.join(builddir, "engine")
    objdir = os.path.join(builddir, "obj")
    cfgdir = os.path.join(builddir, "cfg")
    srcdir = os.path.join(builddir, "src")
    try:
        for path in (engdir, objdir, cfgdir, srcdir):
            os.makedirs(path)
        with open(os.path.join(cfgdir, "config_private.inc"), "w") as f:
            f.write(_engine_config(art_lines))
        # Build from a writable copy inside the game folder: a packaged app
        # runs from a read-only bundle, and z80asm's m4 pass writes the
        # generated .asm next to its source. Run m4 ourselves so paths (the
        # AppImage mount has spaces) are passed as separate argv entries.
        lst = os.path.join(vendor, "nirvanap_sccz80.lst")
        with open(lst) as f:
            sources = [line.strip() for line in f if line.strip()]
        asm_sources = []
        for name in sources:
            if name.endswith(".m4"):
                continue
            shutil.copyfile(os.path.join(vendor, name),
                            os.path.join(engdir, name))
            asm_sources.append(name)
        engine_m4 = next(n for n in sources if n.endswith(".m4"))
        engine_asm = os.path.basename(engine_m4)[:-3]
        with open(os.path.join(engdir, engine_asm), "w") as out:
            run(["m4", "-I" + _fwd(cfgdir), "-I" + _fwd(vendor),
                 "-I" + _fwd(os.path.join(vendor, "m4")),
                 _fwd(os.path.join(vendor, engine_m4))],
                env, cwd=engdir, stdout=out)
        run(["z88dk-z80asm", "-d", "-Oobj", "-xnirvanap.lib",
             "-D__CLASSIC=1", engine_asm, *asm_sources], env, cwd=engdir)

        # --- compile ------------------------------------------------------
        # Stage every input in the game-folder build dir and run from there
        # with relative names: zcc mangles source paths that contain spaces
        # (AppImage mount paths and some game folders do). Loader/zx0 sources
        # are listed first so the low routines stay below the paged window on
        # 128K; on 48K the flat loader reads one block into lower RAM.
        if flat:
            inputs = [
                os.path.join(ROOT, "src", "zx", "loader48.asm"),
                os.path.join(ROOT, "vendor", "zx0", "zx0.asm"),
                os.path.join(ROOT, "src", "z80", "zx0_wrap.asm"),
                *portable_sources(ROOT),
                os.path.join(ROOT, "src", "portable", "plat.h"),
                os.path.join(ROOT, "src", "zx", "plat_zx.c"),
                os.path.join(ROOT, "src", "zx", "paging.asm"),
                os.path.join(ROOT, "src", "zx", "engine.h"),
                os.path.join(bdir, "scene_data.h"),
                os.path.join(bdir, "scene_data.c"),
                os.path.join(bdir, "port_data.h"),
            ]
        else:
            inputs = [
                os.path.join(ROOT, "src", "zx", "loader.asm"),
                os.path.join(ROOT, "vendor", "zx0", "zx0.asm"),
                os.path.join(bdir, "scene_banks.asm"),
                *portable_sources(ROOT),
                os.path.join(ROOT, "src", "portable", "plat.h"),
                os.path.join(ROOT, "src", "zx", "plat_zx.c"),
                os.path.join(ROOT, "src", "zx", "paging.asm"),
                os.path.join(ROOT, "src", "zx", "engine.h"),
                os.path.join(bdir, "scene_data.h"),
                os.path.join(bdir, "scene_data.c"),
                os.path.join(bdir, "port_data.h"),
            ]
        for path in inputs:
            shutil.copyfile(path, os.path.join(srcdir, os.path.basename(path)))
        shutil.copyfile(os.path.join(engdir, "nirvanap.lib"),
                        os.path.join(srcdir, "nirvanap.lib"))
        cmd = ["zcc", "+zx", "-compiler=sccz80", "-vn", "-clib=default",
               "-startup=1", "-I.", "-L.", "-lnirvanap",
               "-pragma-define:CRT_DISABLELOADER=1"]
        for key in ("ART_WS_SIZE", "SCENE_WS_SIZE"):
            val = _scene_define(gdir, key)
            if val is not None:
                cmd.append("-Ca-D%s=%d" % (key, val))
        if flat:
            # No paging: keep the stack above the flat store, leaving 1 KB
            # (0x7C00-0x7FFF) between it and the data at 0x6000-0x7BFF.
            flat_addr = _scene_define(gdir, "FLAT_DATA_ADDR") or 0x6000
            flat_size = _scene_define(gdir, "FLAT_DATA_SIZE") or 0x1C00
            cmd += ["-DZX48=1", "-Ca-DZX48=1",
                    "-pragma-define:REGISTER_SP=0x7FFE",
                    "-Ca-DFLAT_DATA_ADDR=%d" % flat_addr,
                    "-Ca-DFLAT_DATA_SIZE=%d" % flat_size,
                    "loader48.asm", "zx0.asm", "zx0_wrap.asm",
                    "scene_data.c", "state.c", "game.c", "render.c",
                    "inventory.c", "scene.c", "menu.c", "main.c",
                    "plat_zx.c", "music.c", "paging.asm"]
        else:
            cmd += ["loader.asm", "zx0.asm", "scene_banks.asm",
                    "scene_data.c", "state.c", "game.c", "render.c",
                    "inventory.c", "scene.c", "menu.c", "main.c",
                    "plat_zx.c", "music.c", "paging.asm"]
        cmd += ["-o", "adventure.bin", "-lndos", "-m"]
        run(cmd, env, cwd=srcdir)
        for name in ("adventure.bin", "adventure.map"):
            src = os.path.join(srcdir, name)
            if os.path.exists(src):
                shutil.copyfile(src, os.path.join(bdir, name))
        # The engine image must come from this build: the linked map tells us
        # which wrappers the game uses and their order, so a stale
        # adventure_NIRVANAP.bin can never mask an art_rows change.
        write_engine_blob(gdir, engdir, engine_asm, asm_sources, env)
    finally:
        shutil.rmtree(builddir, ignore_errors=True)

    if flat:
        main_size = os.path.getsize(os.path.join(bdir, "adventure.bin"))
        limit = 0xDC03 - 0x8000
        if main_size > limit:
            raise SystemExit(
                "48K build does not fit: main image is %d B but only %d B "
                "fits at 0x8000-0xDC03 before the NIRVANA+ engine. Shorten "
                "scene text/options/item descriptions or use the 128K target."
                % (main_size, limit))
    else:
        guard_map(gdir)

    # --- tape (+ snapshot on 128K) ----------------------------------------
    # appmake can't put the fixed-address NIRVANAP+ engine (or raw 0xC000 bank
    # blocks) on a tape, so merge the engine into the main image and let
    # appmake produce the loader+main TAP. The 128K build then appends the
    # scene banks and writes a resident SNA; the 48K build appends its flat
    # lower-RAM block instead (and has no snapshot).
    merge_engine(gdir)
    run(["z88dk-appmake", "+zx", "-b",
         _fwd(os.path.join(bdir, "adventure_merged.bin")),
         "-o", _fwd(os.path.join(bdir, "advbase.tap")),
         "--org", "32768", "--blockname", "advmain"], env)
    if flat:
        out_tap = os.path.join(gdir, game["slug"] + "-48k.tap")
        run([py, os.path.join(ROOT, "tools", "make_tap48.py"),
             os.path.join(bdir, "advbase.tap"), out_tap, gdir], env)
    else:
        out_tap = os.path.join(gdir, game["slug"] + ".tap")
        run([py, os.path.join(ROOT, "tools", "make_tap.py"),
             os.path.join(bdir, "advbase.tap"), out_tap, gdir], env)
    out_sna = os.path.join(gdir, game["slug"] + ".sna")
    if not flat:
        run([py, os.path.join(ROOT, "tools", "make_sna.py"), gdir, out_sna],
            env)
    for tmp in ("advbase.tap", "adventure_merged.bin"):
        try:
            os.remove(os.path.join(bdir, tmp))
        except OSError:
            pass

    if flat:
        used = _scene_define(gdir, "FLAT_DATA_USED") or 0
        size = _scene_define(gdir, "FLAT_DATA_SIZE") or 0x1C00
        print("OK: %s (%d bytes)"
              % (out_tap, os.path.getsize(out_tap)))
        memory_report48(gdir, used, size)
        return [{"path": out_tap, "kind": "zx48-tap",
                 "size": os.path.getsize(out_tap)}]
    print("OK: %s (%d bytes), %s (%d bytes)"
          % (out_tap, os.path.getsize(out_tap),
             out_sna, os.path.getsize(out_sna)))
    memory_report(gdir)
    return [
        {"path": out_tap, "kind": "zx128-tap", "size": os.path.getsize(out_tap)},
        {"path": out_sna, "kind": "zx128-sna", "size": os.path.getsize(out_sna)},
    ]


def _build_zx128(slug):
    """The original banked ZX Spectrum 128K pipeline."""
    return _build_zx_model(slug, flat=False)


def _build_zx48(slug):
    """The non-paged ZX Spectrum 48K pipeline (fails if the game does not fit)."""
    return _build_zx_model(slug, flat=True)

def _port_define(gdir, key):
    """Read an integer ``#define key N`` from the generated port_data.h."""
    path = os.path.join(gdir, gamestore.BUILD_NAME, "port_data.h")
    try:
        txt = open(path).read()
    except OSError:
        return None
    m = re.search(r"^#define\s+%s\s+(\d+)" % re.escape(key), txt, re.M)
    return int(m.group(1)) if m else None


def _guard_next_map(path):
    """The Next main image must stay below the banked 0xC000 window."""
    if not os.path.exists(path):
        return
    txt = open(path, encoding="utf-8", errors="replace").read()
    bad = []
    for sym in ("_main", "_plat_draw_art", "_plat_load",
                "_paged_next_unpack", "_zx0_unpack", "_set_music",
                "_music_apply", "_ay_vt2_play", "_next_isr"):
        m = re.search(rf"^{re.escape(sym)}\s*=\s*\$([0-9A-Fa-f]+)", txt,
                      re.M)
        if m and int(m.group(1), 16) >= 0xC000:
            bad.append(sym)
    if bad:
        raise SystemExit(
            "ZX Next home-region overflow: %s linked at or above 0xC000; "
            "the Next MMU window would replace the running code. Shorten "
            "the game or move data into banks." % ", ".join(bad))
    m = re.search(r"^__CODE_END_tail\s*=\s*\$([0-9A-Fa-f]+)", txt, re.M)
    if m and int(m.group(1), 16) >= 0xC000:
        raise SystemExit(
            "ZX Next main code/data reaches 0x%s; the resident image must "
            "stay below 0xC000." % m.group(1))
    head = re.search(r"^__BANK_0_H_head\s*=\s*\$([0-9A-Fa-f]+)", txt, re.M)
    size = re.search(r"^__BANK_0_H_size\s*=\s*\$([0-9A-Fa-f]+)", txt, re.M)
    if head and size:
        end = int(head.group(1), 16) + int(size.group(1), 16)
        if end > 0x10000:
            raise SystemExit(
                "ZX Next bank 0 workspaces reach 0x%04X; the upper 8K bank "
                "is full. Shorten a scene or the inventory text." % end)


def _build_next(slug):
    """Build the native ZX Next .nex with Layer 2 art and AY music."""
    game = gamestore.resolve(slug)
    if game is None:
        raise SystemExit("no such game: %r (see 'games/')" % (slug,))
    gdir = game["dir"]
    bdir = os.path.join(gdir, gamestore.BUILD_NAME)
    os.makedirs(bdir, exist_ok=True)
    env = build_env()
    env["RVN_GAME"] = gdir
    py = _py()

    run([py, os.path.join(ROOT, "tools", "gen_port.py"), gdir, "--next"], env)
    stage = _port_define(gdir, "STAGE_WS_SIZE") or 0
    song = _port_define(gdir, "SONG_WS_SIZE") or 0
    if stage + song > 0x2000:
        raise SystemExit(
            "ZX Next staging + song workspace is %d bytes; the lower-RAM "
            "window at 0x6000 is only 8192 bytes. Shorten a blob or song."
            % (stage + song))

    td = tempfile.mkdtemp(prefix=".next-", dir=bdir)
    try:
        sources = [
            os.path.join(ROOT, "src", "next", "paging_next.asm"),
            os.path.join(ROOT, "vendor", "zx0", "zx0.asm"),
            os.path.join(ROOT, "src", "next", "next_isr.asm"),
            os.path.join(bdir, "port_next_font.asm"),
            *portable_sources(ROOT),
            os.path.join(ROOT, "src", "next", "plat_next.c"),
            os.path.join(ROOT, "src", "portable", "plat.h"),
            os.path.join(bdir, "port_data.c"),
            os.path.join(bdir, "port_data.h"),
            os.path.join(bdir, "port_next_data.asm"),
        ]
        names = stage_inputs(td, sources)
        names = [n for n in names if n.endswith((".c", ".asm"))]
        cmd = ["zcc", "+zxn", "-clib=classic", "-compiler=sccz80",
               "-create-app", "-subtype=nex", "-m", "-DPLAT_ROWS=24",
               "-pragma-define:REGISTER_SP=0xc000",
               "-Cz--nex-2mb", "-I."]
        for key in ("PORT_SCENE_WS", "PORT_INV_WS"):
            val = _port_define(gdir, key)
            if val is not None:
                cmd.append("-Ca-D%s=%d" % (
                    "SCENE_WS_SIZE" if key == "PORT_SCENE_WS" else "INV_WS_SIZE",
                    val))
        cmd += [*names, "-o", slug]
        run(cmd, env, cwd=td)
        produced = os.path.join(td, slug + ".nex")
        if not os.path.exists(produced):
            raise SystemExit("ZX Next build produced no .nex file")
        _guard_next_map(os.path.join(td, slug + ".map"))
        data = open(produced, "rb").read()
        if not data.startswith(b"Next"):
            raise SystemExit("ZX Next build produced an invalid .nex header")
        if len(data) < 512 or data[9] > 112:
            raise SystemExit("ZX Next .nex has an invalid bank count")
        if sum(1 for i in range(112) if data[18 + i]) != data[9]:
            raise SystemExit("ZX Next .nex bank map is inconsistent")
        path = os.path.join(gdir, slug + ".nex")
        shutil.copyfile(produced, path)
    finally:
        shutil.rmtree(td, ignore_errors=True)

    print("OK: %s (%d bytes)" % (path, os.path.getsize(path)))
    return [{"path": path, "kind": "zx-next-nex",
             "size": os.path.getsize(path)}]


Z88DK_TOOLS = ("zcc", "z88dk-z80asm", "z88dk-appmake", "z88dk-zx0")


def _z88dk_missing(env=None):
    env = env or build_env()
    path = env.get("PATH", "")
    return [name for name in Z88DK_TOOLS
            if shutil.which(name, path=path) is None]


def _game_doc(slug):
    game = gamestore.resolve(slug)
    if game is None:
        raise SystemExit("no such game: %r (see 'games/')" % (slug,))
    md = os.path.join(game["dir"], "game.md")
    return game, scenefile.parse(md)


def _target_ids(doc, requested=None, build_all=False):
    if build_all:
        ids = []
        for t in targets.all_targets().values():
            if t.id not in ids:
                ids.append(t.id)
        return targets.ordered_targets(sorted(ids))
    if requested:
        return targets.ordered_targets(
            str(x).strip().lower() for x in requested if str(x).strip())
    return targets.ordered_targets(targets.selected_targets(doc))


CC65_TARGETS = ("c64", "nes")


def _needs_z88dk(ids):
    return any(str(t).strip().lower() not in CC65_TARGETS for t in ids)


def build_selected(slug, requested=None, build_all=False):
    """Build every selected target; return a per-target result summary."""
    game, doc = _game_doc(slug)
    env = build_env()
    ids = _target_ids(doc, requested, build_all)
    if not ids:
        raise SystemExit("no build targets selected (add targets: to game.md)")
    if _needs_z88dk(ids):
        missing = _z88dk_missing(env)
        if missing:
            raise SystemExit(
                "z88dk is incomplete — missing %s. Set $Z88DK or choose the "
                "toolchain folder in the editor's Settings (Build toolchain)"
                % ", ".join(missing))
    if any(str(t).strip().lower() in CC65_TARGETS for t in ids):
        cc65 = env.get("CC65") or cc65path.detected()
        missing = cc65path.missing_tools(cc65)
        if missing:
            raise SystemExit(
                "cc65 is incomplete — missing %s. Install cc65 or choose its "
                "folder in the editor's Settings (Build toolchain)"
                % ", ".join(missing))
    summary = []
    failures = 0
    for index, target_id in enumerate(ids):
        target = targets.get_target(target_id)
        if len(ids) > 1:
            if index:
                print()
            print(targets.build_separator(
                target_id, target.label if target else ""), flush=True)
        if target is None:
            print(f"[{target_id}] error: unknown build target")
            failures += 1
            summary.append({"target": target_id, "status": "error",
                            "error": "unknown target", "outputs": []})
            continue
        options = targets.target_options(doc, target)
        ctx = targets.BuildContext(slug=game["slug"], gdir=game["dir"],
                                   bdir=os.path.join(game["dir"],
                                                    gamestore.BUILD_NAME),
                                   doc=doc, options=options, env=env,
                                   py=_py(), root=ROOT)
        print(f"[{target_id}] building {target.label} ...", flush=True)
        started = time.monotonic()
        try:
            if target.available is not None:
                avail, reason = target.available()
                if not avail:
                    raise RuntimeError(reason)
            result = target.build(ctx) or targets.BuildResult(target=target_id)
            seconds = time.monotonic() - started
            summary.append({"target": target_id, "status": "done",
                            "outputs": result.outputs,
                            "warnings": result.warnings,
                            "seconds": round(seconds, 1)})
        except SystemExit as err:
            failures += 1
            seconds = time.monotonic() - started
            print(f"[{target_id}] failed in {seconds:.1f}s: {err}")
            summary.append({"target": target_id, "status": "error",
                            "error": str(err), "outputs": [],
                            "seconds": round(seconds, 1)})
        except Exception as err:                # noqa: BLE001 - one target fails
            failures += 1
            seconds = time.monotonic() - started
            print(f"[{target_id}] failed in {seconds:.1f}s: {err}")
            summary.append({"target": target_id, "status": "error",
                            "error": str(err), "outputs": [],
                            "seconds": round(seconds, 1)})
    return summary, failures


def run_game(slug, target_id=None):
    summary, failures = build_selected(slug, [target_id] if target_id else None)
    if failures:
        raise SystemExit("build failed; not starting the emulator")
    target_id = target_id or (summary[0]["target"] if summary else "zx128")
    target = targets.get_target(target_id)
    target_id = target.id if target else target_id
    if target_id not in ("zx128", "zx48", "next"):
        print(f"{target_id}: build complete; use an external emulator "
              f"(outputs above)")
        return
    game, _ = _game_doc(slug)
    ext = ".nex" if target_id == "next" else ".tap"
    suffix = target.artifact_suffix if target else ""
    image = os.path.join(game["dir"], game["slug"] + suffix + ext)
    machine = "48k" if target_id == "zx48" else None
    env = build_env()
    run([_py(), os.path.join(ROOT, "tools", "spectrum.py"), "off"], env)
    time.sleep(1)
    args = [_py(), os.path.join(ROOT, "tools", "spectrum.py"), "run", image]
    if machine:
        args.append(machine)
    run(args, env)


def list_targets():
    for item in targets.targets_json()["targets"]:
        status = "available" if item["available"] else \
            "unavailable: " + (item["unavailable_reason"] or "missing toolchain")
        print(f"{item['id']:<4} {item['label']:<24} "
              f"{', '.join(item['outputs']):<12} {status}")


def main():
    args = sys.argv[1:]
    if args and args[0] == "list-targets":
        list_targets()
        return
    if args and args[0] in ("build", "run"):
        cmd = args[0]
        rest = args[1:]
    else:
        cmd = "build"
        rest = args
    build_all = "--all" in rest
    rest = [a for a in rest if a != "--all"]
    if not rest:
        raise SystemExit("usage: build.py %s <game> [target ...] [--all]" % cmd)
    game_arg = rest[0]
    requested = rest[1:] or None
    if cmd == "run":
        run_game(game_arg, requested[0] if requested else None)
    else:
        summary, failures = build_selected(game_arg, requested, build_all)
        print()
        for item in summary:
            elapsed = item.get("seconds")
            timing = f" in {elapsed:.1f}s" if elapsed is not None else ""
            print(f"[{item['target']}] {item['status']}{timing}")
            for out in item.get("outputs", []):
                print(f"  {out['path']} ({out.get('size', '?')} bytes)")
        if failures:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
