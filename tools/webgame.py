#!/usr/bin/env python3
"""Export a game as a standalone, mobile-first web runtime.

The runtime is a small static SPA (``tools/webgame_runtime/``) that reads one
data file, ``game.js``, which assigns ``window.RVN_GAME``.  Because the data is
a classic script, an exported folder works from ``file://`` without a server or
a fetch/CORS exception.  The runtime itself is frontend-only; this module is the
build/export step that writes the runtime files and the data they consume.

    python3 tools/webgame.py <slug>          # write games/<slug>/web/
    python3 tools/webgame.py <slug> --json   # print the runtime data

Exports use relative ``assets/art/<id>.png`` paths and copy the selected source
image for every art.

The story semantics mirror ``src/portable/core/`` and ``tools/gen_scenes.py``:
all ``if``/``unless`` tokens must hold, ``pick`` options hide while the item is
held or the pack is full, ``clear`` resets the flags and re-grants ``# Game
start:`` before applying the option's own effects, selectable words are
one-shot, and entering a scene sets its ``ending:`` flag.  Music is deliberately
not part of the web runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamestore
import scenefile
import targets

RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "webgame_runtime")
WEB_DIRNAME = "web"
RUNTIME_FILES = ("index.html", "app.js", "style.css")
GAME_JS = "game.js"
ART_SUBDIR = os.path.join("assets", "art")
OPT_RE = re.compile(r"(.+?)\s*->\s*(\S+)(.*)$")
_SPEC_DIM = [(0, 0, 0), (0, 0, 192), (192, 0, 0), (192, 0, 192),
             (0, 192, 0), (0, 192, 192), (192, 192, 0), (192, 192, 192)]
_SPEC_BRIGHT = [(0, 0, 0), (0, 0, 255), (255, 0, 0), (255, 0, 255),
                (0, 255, 0), (0, 255, 255), (255, 255, 0), (255, 255, 255)]


def runtime_path(name):
    """Resolve one of the shipped runtime files (no arbitrary paths)."""
    if name not in RUNTIME_FILES:
        raise FileNotFoundError(f"no runtime file: {name}")
    path = os.path.join(RUNTIME_DIR, name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"missing runtime file: {name}")
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

    scenes = []
    for scene in doc["scenes"]:
        scenes.append({
            "id": scene["id"],
            "title": scene.get("title") or scene["id"],
            "art": scene.get("art") or "",
            "ending": scene.get("ending") or "",
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
        "scenes": scenes,
    }


def _js(data):
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return "window.RVN_GAME=" + text + ";\n"


def _export_rev(tmp, sources):
    """Fingerprint the exported runtime so the editor can reload only on change."""
    digest = hashlib.sha1()
    for name in RUNTIME_FILES + (GAME_JS,):
        with open(os.path.join(tmp, name), "rb") as fh:
            digest.update(name.encode("utf-8") + b"\0" + fh.read() + b"\0")
    for art_id in sorted(sources):
        src = sources[art_id]
        if not src or not os.path.isfile(src):
            continue
        st = os.stat(src)
        digest.update(
            f"{art_id}\0{os.path.basename(src)}\0{st.st_size}\0{st.st_mtime_ns}\n"
            .encode("utf-8"))
    return digest.hexdigest()


def export_web(slug):
    """Write a self-contained ``games/<slug>/web/`` folder and return its info."""
    rec = _game(slug)
    doc = _doc(rec)
    sources = _art_sources(rec, doc)
    data = webgame_data(slug)
    dest = os.path.join(rec["dir"], WEB_DIRNAME)
    tmp = dest + ".tmp"
    old = dest + ".old"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, ART_SUBDIR), exist_ok=True)
    try:
        for name in RUNTIME_FILES:
            shutil.copyfile(runtime_path(name), os.path.join(tmp, name))
        with open(os.path.join(tmp, GAME_JS), "w", encoding="utf-8") as f:
            f.write(_js(data))
        for art_id, src in sources.items():
            if not src or not os.path.isfile(src):
                continue
            shutil.copyfile(src, os.path.join(tmp, ART_SUBDIR,
                                              f"{art_id}.png"))
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
        "rev": rev,
    }


def export_zip(slug):
    """A zip of the exported folder (under ``<slug>/``), building it if needed."""
    rec = _game(slug)
    web = os.path.join(rec["dir"], WEB_DIRNAME)
    if not os.path.isdir(web):
        export_web(slug)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, _dirs, files in os.walk(web):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, web).replace(os.sep, "/")
                archive.write(full, f"{rec['slug']}/{rel}")
    return buf.getvalue()


def zip_filename(slug):
    rec = _game(slug)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", rec["slug"]).strip("-") or "game"
    return f"{safe}-web.zip"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export a novel as a standalone, mobile-first web runtime.")
    parser.add_argument("game", help="game slug or folder")
    parser.add_argument("--json", action="store_true",
                        help="print the runtime data instead of exporting")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(webgame_data(args.game), indent=2, ensure_ascii=False))
        return 0
    result = export_web(args.game)
    print(f"exported {result['game']} -> {result['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
