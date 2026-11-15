#!/usr/bin/env python3
"""Export a game as a standalone Web Player.

The export is a self-contained folder that plays the story in the browser and
bundles the selected native systems' browser emulators and built files:

    <game-folder>/web/
      index.html, player.js, player-data.js, style.css
      novel/<variant>/       each variant's mobile-first HTML5 story
      emulator/              only the selected systems' emulator bundles
      files/<variant>/       one played artifact per native system

The story runtime (``tools/webgame_runtime/``) reads ``novel/game.js``, which
assigns ``window.RVN_GAME``.  The player shell reads ``player-data.js``, which
assigns ``window.RVN_PLAYER``.  Both data files are classic scripts, so the
HTML5 story works from ``file://``; the native emulator entries need an HTTP
host (GitHub Pages, itch.io or ``python3 -m http.server``).

    python3 tools/webgame.py <slug>          # write <game-folder>/web/
    python3 tools/webgame.py <slug> --player # player only, no HTML5 story
    python3 tools/webgame.py <slug> --game   # player plus the HTML5 story
    python3 tools/webgame.py <slug> --json   # print the HTML5 data

Only the systems ticked in ``# Systems`` are included.  The player shell and
the selected native systems' emulators are always part of the export; the
HTML5 story (``novel/``) is added when the HTML5 system is selected (or forced
by ``export_game``).  Its art is baked to a dithered black-and-white band when
``mono`` is on, using the HTML5 ``art_rows``/``dither`` options.
``export_player`` writes the Web Player without the story, so the two build
steps are independent.
Systems without a browser emulator (such as the ZX Spectrum Next) and missing
build artifacts are skipped with a warning.  The player itself has no download
button; the editor's Emulator toolbar downloads the current system's built file.

Music is rendered from the selected PT3 modules with ``spectrumizer.play``
(22050 Hz mono WAV) into ``novel/assets/music/``.  The renderer is an editor
dependency; if it is unavailable the export still succeeds without music and
returns a warning.

The story semantics mirror ``src/portable/core/`` and ``tools/gen_scenes.py``:
all ``if``/``unless`` tokens must hold, ``pick`` options hide while the item is
held or the pack is full, ``clear`` resets the flags and re-grants ``# Game
start:`` before applying the option's own effects, selectable words are
one-shot, and entering a scene sets its ``ending:`` flag.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamestore
import scenefile
import targets

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DIR = os.path.join(TOOLS_DIR, "webgame_runtime")
PLAYER_RUNTIME_DIR = os.path.join(TOOLS_DIR, "webplayer_runtime")
EMULATOR_DIR = os.path.join(TOOLS_DIR, "editor", "static", "emulator")
WEB_DIRNAME = "web"
NOVEL_DIRNAME = "novel"
EMULATOR_EXPORT_DIR = "emulator"
FILES_EXPORT_DIR = "files"
PLAYER_FILES = ("index.html", "player.js", "style.css")
RUNTIME_FILES = ("index.html", "app.js", "style.css")
PLAYER_DATA = "player-data.js"
GAME_JS = "game.js"
ART_SUBDIR = os.path.join("assets", "art")
MUSIC_SUBDIR = os.path.join("assets", "music")
SONG_RENDER_TIMEOUT = 180
OPT_RE = re.compile(r"(.+?)\s*->\s*(\S+)(.*)$")
_SPEC_DIM = [(0, 0, 0), (0, 0, 192), (192, 0, 0), (192, 0, 192),
             (0, 192, 0), (0, 192, 192), (192, 192, 0), (192, 192, 192)]
_SPEC_BRIGHT = [(0, 0, 0), (0, 0, 255), (255, 0, 0), (255, 0, 255),
                (0, 255, 0), (0, 255, 255), (255, 255, 0), (255, 255, 255)]

# Browser emulator adapter -> (exported page folder, files/extension).
EMU_PAGE = {
    "emulatorjs": "sms",
    "emulatorjs-c64": "c64",
    "emulatorjs-nes": "nes",
    "gambatte": "gb",
    "webmsx": "msx",
    "cpcjs": "cpc",
    "cpc464": "cpc",
    "oricutron": "oric",
}
EMU_ASSET_DIRS = {
    "jsspeccy": ("jsspeccy",),
    "emulatorjs": ("emulatorjs", "sms"),
    "emulatorjs-c64": ("emulatorjs", "c64"),
    "emulatorjs-nes": ("emulatorjs", "nes"),
    "gambatte": ("emulatorjs", "gb"),
    "webmsx": ("msx",),
    "cpcjs": ("cpc",),
    "cpc464": ("cpc",),
    "oricutron": ("oric",),
}
EMU_ASPECT = {
    "zx128": 4 / 3,
    "zx48": 4 / 3,
    "sms": 4 / 3,
    "c64": 4 / 3,
    "nes": 4 / 3,
    "gb": 160 / 144,
    "cpc": 768 / 540,
    "cpc464": 768 / 540,
    "msx1": 4 / 3,
    "msx2": (544 * 1.14) / 456,
    "oric": 640 / 720,
}


def runtime_path(name):
    """Resolve one of the shipped story-runtime files (no arbitrary paths)."""
    if name not in RUNTIME_FILES:
        raise FileNotFoundError(f"no runtime file: {name}")
    path = os.path.join(RUNTIME_DIR, name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"missing runtime file: {name}")
    return path


def player_path(name):
    """Resolve one of the shipped player-shell files (no arbitrary paths)."""
    if name not in PLAYER_FILES:
        raise FileNotFoundError(f"no player file: {name}")
    path = os.path.join(PLAYER_RUNTIME_DIR, name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"missing player file: {name}")
    return path


def runtime_file(name):
    """Return ``(bytes, content_type)`` for a runtime file."""
    ctype = ("text/html" if name.endswith(".html")
             else "text/javascript" if name.endswith(".js")
             else "text/css")
    return open(runtime_path(name), "rb").read(), ctype


def _game(slug, variant=None):
    rec = gamestore.resolve(slug, variant)
    if rec is None:
        raise KeyError(f"no such game: {slug!r}")
    return rec


def _doc(rec):
    path = rec.get("md") or os.path.join(rec["dir"], "game.md")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{rec['slug']}: {os.path.basename(path)} "
                                "does not exist")
    return scenefile.parse(path)


def _art_sources(rec, doc):
    """Map an art id to its selected source PNG (or None)."""
    root = os.path.join(rec["dir"], scenefile.ART_ROOT)
    legacy = os.path.join(rec["dir"], scenefile.ART_LEGACY_ROOT)
    out = {}
    for art in doc.get("arts") or []:
        out[art["id"]] = scenefile.resolve_art_image(root, art, legacy)
    return out


def selected_art_rows(doc):
    """The art-band height used by the HTML5 layout.

    The HTML5 system has its own ``## web art_rows`` (even 8..16, default 10).
    Fall back to the selected native systems (ZX first) only when the target
    registry is unavailable, then to the legacy shared ``art_lines``.
    """
    try:
        target = targets.get_target("web")
        if target is not None:
            options = targets.target_options(doc, target)
            rows = options.get("art_rows")
            try:
                rows = int(rows)
            except (TypeError, ValueError):
                rows = None
            if rows is not None and 8 <= rows <= 16:
                return rows - (rows & 1)
    except Exception:               # noqa: BLE001 - optional registry
        pass
    for target_id in targets.selected_targets(doc):
        target = targets.get_target(target_id)
        if target is None:
            continue
        options = targets.target_options(doc, target)
        if "art_rows" not in options:
            continue
        try:
            rows = int(options["art_rows"])
        except (TypeError, ValueError):
            continue
        if 8 <= rows <= 16:
            return rows - (rows & 1)
    return scenefile.art_lines((doc or {}).get("game") or {})


def _web_options(doc):
    """Resolve the HTML5 target's ``mono`` and ``dither`` settings."""
    try:
        target = targets.get_target("web")
        if target is not None:
            options = targets.target_options(doc, target)
            mon = bool(options.get("mono"))
            dither = options.get("dither") or scenefile.DEFAULT_DITHER
            if dither not in scenefile.DITHER_MODES:
                dither = scenefile.DEFAULT_DITHER
            return mon, dither
    except Exception:               # noqa: BLE001 - optional registry
        pass
    return False, scenefile.DEFAULT_DITHER


def render_web_art(im, conv, rows):
    """Render an HTML5 band: dithered 1-bit with mono, else the fitted source.

    ``rows`` is the band height in 16px tile rows (HTML5 ``art_rows`` / 2). An
    explicit crop is always re-fitted to the HTML5 band aspect before baking, so
    a crop authored for another target never stretches, in mono or colour.
    """
    import zxart

    conv = conv or {}
    rows = max(1, int(rows))
    crop = conv.get("crop")
    if crop:
        im = zxart.crop_for_band(im, crop, rows)
        crop = None
    if conv.get("mono"):
        return zxart.mono_image(
            im, crop=crop, dither=conv.get("dither", scenefile.DEFAULT_DITHER),
            rows=rows, adjust=conv.get("adjust"),
            palette=conv.get("palette", scenefile.DEFAULT_PALETTE),
            palette_colors=conv.get("palette_colors"),
            margin=conv.get("margin", 0), fill=(0, 0, 0))
    return zxart._fit_band(im, crop, rows)


def _conds(text):
    return [[kind, name] for kind, name in scenefile.option_conditions(text)]


def _effect_tokens(rest):
    def one(key):
        m = re.search(rf"\b{key}\s+(\S+)", rest)
        return m.group(1) if m else ""
    return {"set": one("set"), "unset": one("unset"),
            "pick": one("pick"), "leave": one("leave"),
            "clear": bool(re.search(r"\bclear\b", rest))}


def _folded_conds(conds, system):
    """Drop build-time system conditions, or ``None`` when the line is hidden."""
    folded = scenefile.filter_system_conditions(conds, system)
    return None if folded is None else [[k, n] for k, n in folded]


def _scene_option(raw, system="web"):
    core, popup = scenefile.split_option_msg(str(raw or ""))
    m = OPT_RE.match(core)
    if not m:
        return {"label": str(raw or ""), "target": "-", "cond": [],
                "set": "", "unset": "", "pick": "", "leave": "",
                "clear": False, "popup": popup}
    label, target, rest = m.groups()
    conds = _folded_conds(_conds(rest), system)
    if conds is None:
        return None
    out = {"label": label.strip(), "target": target, "cond": conds,
           "popup": popup}
    out.update(_effect_tokens(rest))
    return out


def _item_option(raw, system="web"):
    out = _scene_option(raw, system)
    if out is None:
        return None
    core, _popup = scenefile.split_option_msg(str(raw or ""))
    m = re.search(r"\binscene\s+(\S+)", core)
    out["inscene"] = m.group(1) if m else ""
    return out


def _text_line(raw, system="web"):
    rendered, conds = scenefile.split_text_line(raw)
    conds = _folded_conds(conds, system)
    if conds is None:
        return None
    segments = [{"text": text, "flag": flag}
                for text, flag in scenefile.word_segments(rendered) if text]
    return {"segments": segments, "cond": conds}


def _desc_line(raw, system="web"):
    rendered, conds = scenefile.split_text_line(raw)
    conds = _folded_conds(conds, system)
    if conds is None:
        return None
    return {"text": rendered, "cond": conds}


def _colour(token):
    """A ``text_ink``/``highlight_ink``/``text_bg`` token as a CSS hex colour."""
    code, bright = scenefile.WORD_INKS.get(token, (7, 0))
    rgb = (_SPEC_BRIGHT if bright else _SPEC_DIM)[code & 7]
    return "#%02x%02x%02x" % rgb


def _art_entry(art, source, art_id, mono=False):
    crop = art.get("crop")
    if mono or not (isinstance(crop, list) and len(crop) == 4):
        crop = None
    src = None
    if source and os.path.isfile(source):
        src = f"{ART_SUBDIR.replace(os.sep, '/')}/{art_id}.png"
    return {"src": src, "crop": crop}


def urllib_quote(value):
    """Quote a URL path segment without importing urllib at module scope."""
    from urllib.parse import quote
    return quote(str(value), safe="")


def webgame_data(slug, variant=None):
    """Build the ``window.RVN_GAME`` object for one variant (export data)."""
    rec = _game(slug, variant)
    doc = _doc(rec)
    game = doc["game"]
    item_meta = doc.get("item_meta") or {}
    item_names = scenefile.item_display_names(game, item_meta)
    _flag_map, item_list, _order = scenefile.assign_flags(
        doc["scenes"], game.get("start", []), game.get("flags", []),
        scenefile.declared_items(game, item_meta),
        item_names=item_names, item_meta=item_meta)

    art_rows = selected_art_rows(doc)
    mono, dither = _web_options(doc)

    sources = _art_sources(rec, doc)
    arts = {art["id"]: _art_entry(art, sources.get(art["id"]), art["id"],
                                  mono=mono)
            for art in doc.get("arts") or []}

    system = "web"
    items = {}
    for item_id in item_list:
        meta = item_meta.get(item_id) or {}
        items[item_id] = {
            "name": item_names.get(item_id) or item_id,
            "desc": [x for line in meta.get("desc") or []
                     if (x := _desc_line(line, system)) is not None],
            "opts": [x for line in meta.get("opts") or []
                     if (x := _item_option(line, system)) is not None],
        }

    songs = {song: {"src": f"{MUSIC_SUBDIR.replace(os.sep, '/')}/{song}.wav"}
             for song in game.get("songs") or []}
    scenes = []
    for scene in doc["scenes"]:
        scenes.append({
            "id": scene["id"],
            "title": scene.get("title") or scene["id"],
            "art": scene.get("art") or "",
            "ending": scene.get("ending") or "",
            "music": scenefile.resolve_song(scene, game),
            "text": [x for line in scene.get("text") or []
                     if (x := _text_line(line, system)) is not None],
            "opts": [x for line in scene.get("opts") or []
                     if (x := _scene_option(line, system)) is not None],
        })
    start_scene = scenes[0]["id"] if scenes else ""

    text, highlight, bg = scenefile.text_tokens(game)
    if mono:
        text, highlight, bg = "white", "white", "black"
    storage_key = (rec["slug"] if len(rec.get("variants") or []) <= 1
                   else f"{rec['slug']}.{rec['variant']}")
    return {
        "format": 1,
        "slug": rec["slug"],
        "variant": rec["variant"],
        "storageKey": storage_key,
        "title": game.get("title") or rec["slug"],
        "artRows": art_rows,
        "startScene": start_scene,
        "startItems": list(game.get("start") or []),
        "carry": int(game.get("carry") or 0),
        "password": str(game.get("password") or ""),
        "passwordLabel": scenefile.password_label(game),
        "popupHint": str(game.get("popup_hint") or "").strip(),
        "inventory": scenefile.inventory_strings(game),
        "mono": mono,
        "dither": dither,
        "textColors": {
            "ink": _colour(text),
            "highlight": _colour(highlight),
            "bg": _colour(bg),
        },
        "itemOrder": item_list,
        "items": items,
        "arts": arts,
        "songs": songs,
        "scenes": scenes,
    }


def _js(data):
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return "window.RVN_GAME=" + text + ";\n"


def _player_js(data):
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return "window.RVN_PLAYER=" + text + ";\n"


def _media_for(extension):
    """The media type shown for a system's played file."""
    if extension == ".tap":
        return "tape"
    if extension == ".dsk":
        return "disk"
    return "cartridge"


def _web_selected(doc):
    """True when the HTML5 system is ticked (it owns the story entry)."""
    return "web" in targets.selected_targets(doc)


def _player_systems(rec, doc):
    """Selected systems as player entries, plus emulator dirs and warnings."""
    systems = []
    emulator_dirs = set()
    warnings = []
    variant = rec["variant"]
    for target_id in targets.ordered_targets(targets.selected_targets(doc)):
        target = targets.get_target(target_id)
        if target is None or not target.outputs or target.id == "web":
            continue
        extension = target.outputs[0]
        filename = (f"{rec['output_stem']}{target.artifact_suffix}"
                    f"{extension}")
        source = os.path.join(rec["dir"], filename)
        if not os.path.isfile(source) or os.path.getsize(source) == 0:
            warnings.append(f"{variant}/{target.label}: {filename} is not "
                            "built; skipped")
            continue
        if target.emulator in EMU_ASSET_DIRS:
            media = _media_for(extension)
            entry = {
                "id": target.id,
                "label": target.label,
                "kind": "native",
                "variant": variant,
                "emulator": target.emulator,
                "machine": target.machine,
                "page": EMU_PAGE.get(target.emulator, ""),
                "file": f"{FILES_EXPORT_DIR}/{variant}/{filename}",
                "filename": filename,
                "aspect": round(EMU_ASPECT.get(target.id, 4 / 3), 6),
                "media": media,
                "mediaLabel": media.capitalize(),
            }
            if target.emulator in ("cpcjs", "cpc464"):
                entry["run"] = "GAME"
            emulator_dirs.update(EMU_ASSET_DIRS[target.emulator])
        else:
            warnings.append(f"{variant}/{target.label}: no browser emulator; "
                            "skipped")
            continue
        entry["_source"] = source
        systems.append(entry)
    return systems, emulator_dirs, warnings


def _clean_systems(systems):
    return [{k: v for k, v in item.items() if k != "_source"}
            for item in systems]


def _player_data(base, variants):
    """Assemble window.RVN_PLAYER from per-variant entries."""
    data = {
        "format": 1,
        "slug": base["slug"],
        "title": (variants[0].get("title") if variants else "") or base["slug"],
        "variants": variants,
    }
    primary = variants[0] if variants else None
    if primary:
        if primary.get("src"):
            data["web"] = {
                "label": "HTML5",
                "src": primary["src"],
                "machine": "HTML5",
                "media": "web",
                "mediaLabel": "HTML5",
            }
        data["systems"] = primary.get("systems") or []
    return data


def _copy_emulators(tmp, dirs, warnings):
    if not dirs:
        return
    for name in sorted(dirs):
        source = os.path.join(EMULATOR_DIR, name)
        if not os.path.isdir(source):
            warnings.append(f"emulator bundle missing: {name}")
            continue
        shutil.copytree(source, os.path.join(tmp, EMULATOR_EXPORT_DIR, name))
    notice = os.path.join(EMULATOR_DIR, "THIRD_PARTY.md")
    if os.path.isfile(notice):
        shutil.copyfile(notice, os.path.join(tmp, EMULATOR_EXPORT_DIR,
                                             "THIRD_PARTY.md"))


def _render_music(rec, doc, novel_dir, warnings):
    """Render the songs the story uses to WAV, returning the rendered ids."""
    game = doc["game"]
    if not game.get("songs"):
        return set()
    used = set()
    for scene in doc.get("scenes") or []:
        song = scenefile.resolve_song(scene, game)
        if song:
            used.add(song)
    if not used:
        return set()

    music_dir = os.path.join(rec["dir"], "assets", "music")
    cache_dir = os.path.join(rec["dir"], "assets", "gen")
    os.makedirs(cache_dir, exist_ok=True)
    out_dir = os.path.join(novel_dir, MUSIC_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    rendered = set()
    for song in sorted(used):
        source = os.path.join(music_dir, f"{song}.pt3")
        if not os.path.isfile(source):
            warnings.append(f"song {song}: no assets/music/{song}.pt3; skipped")
            continue
        cache = os.path.join(cache_dir, f"song_{song}.wav")
        fresh = (os.path.isfile(cache)
                 and os.path.getmtime(cache) >= os.path.getmtime(source)
                 and os.path.getsize(cache) > 44)
        if not fresh:
            temp = cache + ".tmp"
            try:
                if os.path.exists(temp):
                    os.remove(temp)
                proc = subprocess.run(
                    [sys.executable, "-m", "spectrumizer.play", source,
                     "-o", temp, "--no-play", "-q", "--rate", "22050",
                     "--stereo", "mono"],
                    cwd=gamestore.ROOT, capture_output=True, text=True,
                    timeout=SONG_RENDER_TIMEOUT)
            except (OSError, subprocess.TimeoutExpired) as err:
                warnings.append(f"song {song}: could not render music: {err}")
                continue
            if proc.returncode != 0 or not os.path.isfile(temp) \
                    or os.path.getsize(temp) <= 44:
                detail = (proc.stderr or proc.stdout or "").strip().splitlines()
                warnings.append(
                    f"song {song}: could not render music"
                    + (f": {detail[-1]}" if detail else ""))
                try:
                    os.remove(temp)
                except OSError:
                    pass
                continue
            os.replace(temp, cache)
        shutil.copyfile(cache, os.path.join(out_dir, f"{song}.wav"))
        rendered.add(song)
    return rendered


def _write_web_art(src, dest, art, game, rows, warnings):
    """Write one HTML5 art, baking the HTML5 mono/dither setting when enabled."""
    try:
        from PIL import Image

        conv = scenefile.conversion_options(art, game, "web")
        im = Image.open(src).convert("RGB")
        img = render_web_art(im, conv, max(1, int(rows) // 2))
        img.save(dest, "PNG")
        return
    except Exception as err:            # noqa: BLE001 - fall back to the source
        warnings.append(
            f"{art.get('id', os.path.basename(src))}: HTML5 black-and-white "
            f"conversion failed: {err}; using the source image")
    shutil.copyfile(src, dest)



def _stamp_scripts(html_path, names):
    """Append a content hash to local script tags so static hosts bust caches."""
    if not os.path.isfile(html_path):
        return
    text = open(html_path, encoding="utf-8").read()
    for name in names:
        path = os.path.join(os.path.dirname(html_path), name)
        if not os.path.isfile(path):
            continue
        digest = hashlib.sha1(open(path, "rb").read()).hexdigest()[:12]
        text = text.replace(f'src="{name}"', f'src="{name}?v={digest}"')
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(text)


def _export_rev(tmp, sources):
    """Fingerprint the exported player so the editor reloads only on change."""
    digest = hashlib.sha1()
    names = list(PLAYER_FILES) + [PLAYER_DATA]
    for name in names:
        path = os.path.join(tmp, name)
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as fh:
            digest.update(name.encode("utf-8") + b"\0" + fh.read() + b"\0")
    for art_id in sorted(sources):
        src = sources[art_id]
        if not src or not os.path.isfile(src):
            continue
        st = os.stat(src)
        digest.update(
            f"{art_id}\0{os.path.basename(src)}\0{st.st_size}\0{st.st_mtime_ns}\n"
            .encode("utf-8"))
    for sub in (FILES_EXPORT_DIR, NOVEL_DIRNAME):
        root = os.path.join(tmp, sub)
        for base, _dirs, files in os.walk(root):
            for name in sorted(files):
                path = os.path.join(base, name)
                rel = os.path.relpath(path, tmp).replace(os.sep, "/")
                st = os.stat(path)
                digest.update(
                    f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode("utf-8"))
    return digest.hexdigest()


def export_web(slug, include_novel=None, variants=None):
    """Write a self-contained ``<game>/web/`` player and return its info.

    Every variant is exported into its own ``novel/<variant>/`` and
    ``files/<variant>/`` subtree, and the player shell gets a variant selector
    when more than one is present. ``include_novel`` forces the mobile-first
    story in or out; ``None`` (the default) follows each variant's HTML5 system
    selection. ``variants`` optionally restricts the exported ids.
    """
    base = _game(slug)
    entries = base.get("variants") or []
    if variants:
        wanted = {str(v) for v in variants}
        entries = [e for e in entries if e["id"] in wanted]
    if not entries:
        raise KeyError(f"no such game variant: {slug!r}")
    dest = os.path.join(base["dir"], WEB_DIRNAME)
    tmp = dest + ".tmp"
    old = dest + ".old"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        os.makedirs(tmp, exist_ok=True)
        for name in PLAYER_FILES:
            shutil.copyfile(player_path(name), os.path.join(tmp, name))
        emulator_dirs = set()
        warnings = []
        sources = {}
        variant_entries = []
        rendered_total = 0
        arts_total = 0
        any_novel = False
        for selected in entries:
            rec = _game(slug, selected["id"])
            doc = _doc(rec)
            variant = rec["variant"]
            has_novel = (include_novel if include_novel is not None
                         else _web_selected(doc))
            systems, dirs, warns = _player_systems(rec, doc)
            emulator_dirs.update(dirs)
            if not has_novel and not systems:
                warnings.append(f"{variant}: no story or built systems; skipped")
                continue
            src = ""
            if has_novel:
                src = f"{NOVEL_DIRNAME}/{variant}/index.html"
                novel = os.path.join(tmp, NOVEL_DIRNAME, variant)
                os.makedirs(os.path.join(novel, ART_SUBDIR), exist_ok=True)
                for name in RUNTIME_FILES:
                    shutil.copyfile(runtime_path(name),
                                    os.path.join(novel, name))
                data = webgame_data(slug, variant)
                rendered = _render_music(rec, doc, novel, warns)
                rendered_total += len(rendered)
                data["songs"] = {song: info
                                 for song, info in data["songs"].items()
                                 if song in rendered}
                for scene in data["scenes"]:
                    if scene.get("music") not in rendered:
                        scene["music"] = None
                with open(os.path.join(novel, GAME_JS), "w",
                          encoding="utf-8") as f:
                    f.write(_js(data))
                mono = bool(data.get("mono"))
                art_rows = selected_art_rows(doc)
                art_by_id = {art["id"]: art for art in doc.get("arts") or []}
                for art_id, source in _art_sources(rec, doc).items():
                    if not source or not os.path.isfile(source):
                        continue
                    sources[f"{variant}:{art_id}"] = source
                    target = os.path.join(novel, ART_SUBDIR, f"{art_id}.png")
                    if mono:
                        _write_web_art(source, target,
                                       art_by_id.get(art_id)
                                       or {"id": art_id}, doc["game"],
                                       art_rows, warns)
                    else:
                        shutil.copyfile(source, target)
                    arts_total += 1
                any_novel = True
            files_dir = os.path.join(tmp, FILES_EXPORT_DIR, variant)
            if systems:
                os.makedirs(files_dir, exist_ok=True)
            for system in systems:
                shutil.copyfile(system["_source"],
                                os.path.join(files_dir, system["filename"]))
            variant_entries.append({
                "id": variant,
                "label": variant,
                "title": doc["game"].get("title") or variant,
                "src": src,
                "systems": _clean_systems(systems),
            })
            warnings.extend(warns)
        _copy_emulators(tmp, emulator_dirs, warnings)
        with open(os.path.join(tmp, PLAYER_DATA), "w", encoding="utf-8") as f:
            f.write(_player_js(_player_data(base, variant_entries)))
        _stamp_scripts(os.path.join(tmp, "index.html"),
                       (PLAYER_DATA, "player.js"))
        for variant in variant_entries:
            if not variant.get("src"):
                continue
            novel = os.path.join(tmp, NOVEL_DIRNAME, variant["id"])
            _stamp_scripts(os.path.join(novel, "index.html"),
                           (GAME_JS, "app.js"))
        rev = _export_rev(tmp, sources)
        shutil.rmtree(old, ignore_errors=True)
        if os.path.exists(dest):
            os.replace(dest, old)
        os.replace(tmp, dest)
        shutil.rmtree(old, ignore_errors=True)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return {
        "game": base["slug"],
        "path": dest,
        "relative": os.path.relpath(dest, base["dir"]),
        "zip": f"/api/webzip/{urllib_quote(base['slug'])}",
        "arts": arts_total,
        "web": any_novel,
        "novel": any_novel,
        "variants": [item["id"] for item in variant_entries],
        "systems": [system["id"] for item in variant_entries
                    for system in item["systems"]],
        "music": rendered_total,
        "warnings": warnings,
        "rev": rev,
    }

def export_player(slug):
    """Write the Web Player and native emulators without the HTML5 story."""
    return export_web(slug, include_novel=False)


def export_game(slug):
    """Write the Web Player plus the mobile-first HTML5 story."""
    return export_web(slug, include_novel=True)


def export_zip(slug):
    """An itch.io-ready zip with ``index.html`` at the archive root."""
    rec = _game(slug)
    export_web(slug)
    web = os.path.join(rec["dir"], WEB_DIRNAME)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _dirs, files in os.walk(web):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, web).replace(os.sep, "/")
                archive.write(full, rel)
    return buf.getvalue()


def zip_filename(slug):
    rec = _game(slug)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", rec["slug"]).strip("-") or "game"
    return f"{safe}-web.zip"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export a game as a standalone Web Player.")
    parser.add_argument("game", help="game slug or folder")
    parser.add_argument("--variant", default=None,
                        help="variant id (default: the primary game.md/variant)")
    parser.add_argument("--json", action="store_true",
                        help="print the HTML5 data instead of exporting")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--player", action="store_true",
                      help="write the player without the mobile-first HTML5 story")
    mode.add_argument("--game", dest="web_game", action="store_true",
                      help="write the player plus the mobile-first HTML5 story")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(webgame_data(args.game, args.variant), indent=2,
                         ensure_ascii=False))
        return 0
    if args.web_game:
        include_novel = True
    elif args.player:
        include_novel = False
    else:
        include_novel = None
    result = export_web(args.game, include_novel=include_novel)
    print(f"exported {result['game']} -> {result['path']}")
    for warning in result.get("warnings") or []:
        print("warning: " + warning, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
