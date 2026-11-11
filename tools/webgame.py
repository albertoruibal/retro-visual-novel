#!/usr/bin/env python3
"""Export a game as a standalone web player.

The export is a self-contained folder that plays the story in the browser and
bundles the selected native systems' web emulators and built files:

    <game-folder>/web/
      index.html, player.js, player-data.js, style.css
      novel/                 the mobile-first story runtime
      emulator/              only the selected systems' emulator bundles
      files/                 one played artifact per native system

The story runtime (``tools/webgame_runtime/``) reads ``novel/game.js``, which
assigns ``window.RVN_GAME``.  The player shell reads ``player-data.js``, which
assigns ``window.RVN_PLAYER``.  Both data files are classic scripts, so the
novel works from ``file://``; the native emulator entries need an HTTP host
(GitHub Pages, itch.io or ``python3 -m http.server``).

    python3 tools/webgame.py <slug>          # write <game-folder>/web/
    python3 tools/webgame.py <slug> --json   # print the novel data

Only the systems ticked in ``# Systems`` are included.  The Web novel is always
present; a selected system with a bundled web emulator gets a playable entry,
and the ZX Spectrum Next (no web emulator) gets a download-only entry.  Missing
build artifacts are skipped with a warning.

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


def _game(slug):
    rec = gamestore.resolve(slug)
    if rec is None:
        raise KeyError(f"no such game: {slug!r}")
    return rec


def _doc(rec):
    path = os.path.join(rec["dir"], "game.md")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"{rec['slug']}: game.md does not exist")
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
    """The art-band height used by the web layout.

    Prefer the selected systems in registry order (ZX first) so the web band
    keeps the framing of the target the author is previewing.  An even 8..16
    value is required; otherwise fall back to the ZX/default ``art_lines``
    setting.
    """
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


def _art_entry(art, source, art_id):
    crop = art.get("crop")
    if not (isinstance(crop, list) and len(crop) == 4):
        crop = None
    src = None
    if source and os.path.isfile(source):
        src = f"{ART_SUBDIR.replace(os.sep, '/')}/{art_id}.png"
    return {"src": src, "crop": crop}


def urllib_quote(value):
    """Quote a URL path segment without importing urllib at module scope."""
    from urllib.parse import quote
    return quote(str(value), safe="")


def webgame_data(slug):
    """Build the ``window.RVN_GAME`` object for one game (export data)."""
    rec = _game(slug)
    doc = _doc(rec)
    game = doc["game"]
    item_meta = doc.get("item_meta") or {}
    item_names = scenefile.item_display_names(game, item_meta)
    _flag_map, item_list, _order = scenefile.assign_flags(
        doc["scenes"], game.get("start", []), game.get("flags", []),
        scenefile.declared_items(game, item_meta),
        item_names=item_names, item_meta=item_meta)

    sources = _art_sources(rec, doc)
    arts = {art["id"]: _art_entry(art, sources.get(art["id"]), art["id"])
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
    return {
        "format": 1,
        "slug": rec["slug"],
        "title": game.get("title") or rec["slug"],
        "artRows": selected_art_rows(doc),
        "startScene": start_scene,
        "startItems": list(game.get("start") or []),
        "carry": int(game.get("carry") or 0),
        "password": str(game.get("password") or ""),
        "passwordLabel": scenefile.password_label(game),
        "popupHint": str(game.get("popup_hint") or "").strip(),
        "inventory": scenefile.inventory_strings(game),
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


def _player_systems(rec, doc):
    """Selected systems as player entries, plus emulator dirs and warnings."""
    systems = []
    emulator_dirs = set()
    warnings = []
    for target_id in targets.ordered_targets(targets.selected_targets(doc)):
        target = targets.get_target(target_id)
        if target is None or not target.outputs:
            continue
        extension = target.outputs[0]
        filename = f"{rec['slug']}{target.artifact_suffix}{extension}"
        source = os.path.join(rec["dir"], filename)
        if not os.path.isfile(source) or os.path.getsize(source) == 0:
            warnings.append(f"{target.label}: {filename} is not built; skipped")
            continue
        if target.emulator in EMU_ASSET_DIRS:
            entry = {
                "id": target.id,
                "label": target.label,
                "kind": "native",
                "emulator": target.emulator,
                "machine": target.machine,
                "page": EMU_PAGE.get(target.emulator, ""),
                "file": f"{FILES_EXPORT_DIR}/{filename}",
                "filename": filename,
                "aspect": round(EMU_ASPECT.get(target.id, 4 / 3), 6),
            }
            if target.emulator in ("cpcjs", "cpc464"):
                entry["run"] = "GAME"
            emulator_dirs.update(EMU_ASSET_DIRS[target.emulator])
        elif target.id == "next":
            entry = {
                "id": target.id,
                "label": target.label,
                "kind": "download",
                "emulator": "",
                "machine": target.machine,
                "page": "",
                "file": f"{FILES_EXPORT_DIR}/{filename}",
                "filename": filename,
                "aspect": 4 / 3,
            }
        else:
            warnings.append(f"{target.label}: no web emulator; skipped")
            continue
        entry["_source"] = source
        systems.append(entry)
    return systems, emulator_dirs, warnings


def _player_data(rec, doc, systems):
    clean = [{k: v for k, v in item.items() if k != "_source"}
             for item in systems]
    return {
        "format": 1,
        "slug": rec["slug"],
        "title": doc["game"].get("title") or rec["slug"],
        "web": {
            "label": "Web version",
            "src": f"{NOVEL_DIRNAME}/index.html",
            "machine": "HTML5",
        },
        "systems": clean,
    }


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


def _export_rev(tmp, sources):
    """Fingerprint the exported player so the editor reloads only on change."""
    digest = hashlib.sha1()
    names = list(PLAYER_FILES) + [PLAYER_DATA]
    names += [f"{NOVEL_DIRNAME}/{name}" for name in RUNTIME_FILES + (GAME_JS,)]
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
    for sub in (FILES_EXPORT_DIR, os.path.join(NOVEL_DIRNAME, "assets", "music")):
        root = os.path.join(tmp, sub)
        for base, _dirs, files in os.walk(root):
            for name in sorted(files):
                path = os.path.join(base, name)
                rel = os.path.relpath(path, tmp).replace(os.sep, "/")
                st = os.stat(path)
                digest.update(
                    f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode("utf-8"))
    return digest.hexdigest()


def export_web(slug):
    """Write a self-contained ``<game>/web/`` player and return its info."""
    rec = _game(slug)
    doc = _doc(rec)
    sources = _art_sources(rec, doc)
    data = webgame_data(slug)
    systems, emulator_dirs, warnings = _player_systems(rec, doc)
    dest = os.path.join(rec["dir"], WEB_DIRNAME)
    tmp = dest + ".tmp"
    old = dest + ".old"
    shutil.rmtree(tmp, ignore_errors=True)
    novel = os.path.join(tmp, NOVEL_DIRNAME)
    os.makedirs(os.path.join(novel, ART_SUBDIR), exist_ok=True)
    try:
        for name in PLAYER_FILES:
            shutil.copyfile(player_path(name), os.path.join(tmp, name))
        for name in RUNTIME_FILES:
            shutil.copyfile(runtime_path(name), os.path.join(novel, name))
        rendered = _render_music(rec, doc, novel, warnings)
        data["songs"] = {song: info for song, info in data["songs"].items()
                         if song in rendered}
        for scene in data["scenes"]:
            if scene.get("music") not in rendered:
                scene["music"] = None
        with open(os.path.join(novel, GAME_JS), "w", encoding="utf-8") as f:
            f.write(_js(data))
        for art_id, src in sources.items():
            if not src or not os.path.isfile(src):
                continue
            shutil.copyfile(src, os.path.join(novel, ART_SUBDIR,
                                              f"{art_id}.png"))
        _copy_emulators(tmp, emulator_dirs, warnings)
        files_dir = os.path.join(tmp, FILES_EXPORT_DIR)
        if systems:
            os.makedirs(files_dir, exist_ok=True)
        for system in systems:
            shutil.copyfile(system["_source"],
                            os.path.join(files_dir, system["filename"]))
        with open(os.path.join(tmp, PLAYER_DATA), "w", encoding="utf-8") as f:
            f.write(_player_js(_player_data(rec, doc, systems)))
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
        "game": rec["slug"],
        "path": dest,
        "relative": os.path.relpath(dest, rec["dir"]),
        "zip": f"/api/webzip/{urllib_quote(rec['slug'])}",
        "arts": len([s for s in sources.values() if s and os.path.isfile(s)]),
        "systems": [item["id"] for item in systems],
        "music": len(rendered),
        "warnings": warnings,
        "rev": rev,
    }


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
        description="Export a game as a standalone web player.")
    parser.add_argument("game", help="game slug or folder")
    parser.add_argument("--json", action="store_true",
                        help="print the novel data instead of exporting")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(webgame_data(args.game), indent=2, ensure_ascii=False))
        return 0
    result = export_web(args.game)
    print(f"exported {result['game']} -> {result['path']}")
    for warning in result.get("warnings") or []:
        print("warning: " + warning, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
