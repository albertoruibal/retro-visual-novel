#!/usr/bin/env python3
"""Locate and manage per-game project folders.

A game is a self-contained directory::

    <game-folder>/
      game.md                         story (game / art / scene sections)
      assets/art/<id>/<action>-<epoch>.png   candidate source images (`image:` picks one)
      <slug>.tap, <slug>.sna, ...     playable build outputs (stay at the root)
      build/scene_banks/bankN.bin     generated bank images
      build/scene_data.h, ...         generated build sources
      build/adventure.bin, ...        build intermediates

Games can be authoring data only: the shared engine (``src/zx/`` +
paging/loader asm and ``vendor/``) and the tools live at the repository/app
root, and a per-game header is picked up with ``-I<game>``.

Two modes share this module:

* **Opened folders** (desktop/folder model) — one or more game folders anywhere
  on disk are open at once (the editor shows them as a switchable list).
  ``open_folder``/``close_folder``/``set_opened`` (or the ``RVN_GAMES`` /
  ``RVN_GAME`` environment variables, honoured at import) maintain the set, and
  ``resolve``/``game_dir``/``list_games`` refer to those folders, addressed by
  slug (a folder's basename) or by absolute path.
* **Workspace** (legacy/browser dev) — when nothing is opened, games are the
  ``games/<slug>/`` folders under :data:`GAMES_DIR`.

The shared engine and the tools live at the repository root; a per-game header
is picked up with ``-I<game>``.

This module is stdlib-only and is imported by the editor server, the build
scripts and ``gen_images.py`` so the layout is defined once.
"""
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scenefile

# The project root normally sits one level above this file. A packaged/desktop
# build overrides it with RVN_ROOT so games (and the engine) live in a
# user-writable workspace instead of the read-only app bundle. The old
# ZXAD_ROOT is still accepted as a fallback.
ROOT = os.path.abspath(
    os.environ.get("RVN_ROOT")
    or os.environ.get("ZXAD_ROOT")
    or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
GAMES_DIR = os.path.join(ROOT, "games")
BUILD_NAME = "build"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DEFAULT_GAME = None  # no hardcoded default: resolve() falls back to the first game

# Generated names inside a game folder; excluded when duplicating so the copy
# is a clean authoring starting point rather than a stale build tree.
_GEN_FILES = ("game.md.bak", "adventure.map", "scene_flags.txt")
_GEN_SUFFIXES = (".tap", ".sna", ".bin")

# The game folders open in the desktop/folder model, in tab order. Empty means
# the games/ workspace is used instead.
_opened = []


def slugify(name, fallback="game"):
    s = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    return s or fallback


def valid_slug(slug):
    return bool(_SLUG_RE.match(slug or "")) and ".." not in slug


def is_game_dir(path):
    """True if ``path`` is a directory holding a ``game.md``."""
    return bool(path) and os.path.isfile(os.path.join(path, "game.md"))


def game_from_dir(path):
    """Build a game dict for an explicit folder (no ``games/`` lookup)."""
    path = os.path.abspath(os.path.expanduser(path))
    title = ""
    try:
        title = scenefile.parse(os.path.join(path, "game.md"))["game"].get("title", "")
    except Exception:      # noqa: BLE001 - a malformed game still opens
        pass
    slug = os.path.basename(os.path.normpath(path)) or "game"
    return {"slug": slug, "title": title, "dir": path}


def _norm(path):
    return os.path.abspath(os.path.expanduser(str(path)))


def _find_opened(ref):
    """The opened folder matching a slug (its basename) or a folder path."""
    if not ref:
        return None
    ref = str(ref)
    norm = _norm(ref)
    for p in _opened:
        if os.path.basename(os.path.normpath(p)) == ref or p == norm:
            return p
    if is_game_dir(ref):
        return norm
    return None


def set_opened(path):
    """Replace the set of open game folders with just ``path`` (empty clears).

    Raises :class:`FileNotFoundError` if ``path`` has no ``game.md``.
    """
    global _opened
    if not path:
        _opened = []
        return None
    path = _norm(path)
    if not is_game_dir(path):
        raise FileNotFoundError(f"not a game folder (no game.md): {path}")
    _opened = [path]
    return game_from_dir(path)


def open_folder(path):
    """Open another game folder (idempotent), keeping the current tabs open.

    A different folder whose basename matches one already open is rejected:
    the basename is the game's slug (and names its build outputs), so two
    same-named folders cannot be addressed apart.
    """
    path = _norm(path)
    if not is_game_dir(path):
        raise FileNotFoundError(f"not a game folder (no game.md): {path}")
    if path in _opened:
        return game_from_dir(path)
    slug = os.path.basename(os.path.normpath(path)) or "game"
    for other in _opened:
        if os.path.basename(os.path.normpath(other)) == slug:
            raise ValueError(
                f"a game folder named '{slug}' is already open: {other}")
    _opened.append(path)
    return game_from_dir(path)


def close_folder(ref):
    """Close one open game folder, by slug or path."""
    path = _find_opened(ref)
    if path is None or path not in _opened:
        raise FileNotFoundError(f"no such open game: {ref!r}")
    _opened.remove(path)
    return game_from_dir(path)


def opened():
    """The open game folder paths, in tab order (empty in the workspace)."""
    return list(_opened)


def game_dir(slug):
    """Absolute path to a game folder, or None if it cannot be resolved."""
    if _opened:
        return _find_opened(slug)
    if slug and is_game_dir(slug):
        return _norm(slug)
    if not valid_slug(slug):
        return None
    return os.path.join(GAMES_DIR, slug)


def game_md(slug):
    return os.path.join(game_dir(slug), "game.md")


def gen_dir(slug):
    return os.path.join(game_dir(slug), "assets", "gen")


def build_dir(slug):
    """Where a game's generated intermediates live (never its outputs)."""
    return os.path.join(game_dir(slug), BUILD_NAME)


def banks_dir(slug):
    return os.path.join(game_dir(slug), BUILD_NAME, "scene_banks")


def list_games():
    """Return [{"slug", "title", "dir"}]: the open folders, or the workspace."""
    if _opened:
        return [game_from_dir(p) for p in _opened]
    out = []
    if not os.path.isdir(GAMES_DIR):
        return out
    for name in sorted(os.listdir(GAMES_DIR)):
        path = os.path.join(GAMES_DIR, name)
        if not os.path.isdir(path) or not valid_slug(name):
            continue
        if not os.path.exists(os.path.join(path, "game.md")):
            continue
        title = ""
        try:
            title = scenefile.parse(os.path.join(path, "game.md"))["game"].get("title", "")
        except Exception:      # noqa: BLE001 - a malformed game should still list
            pass
        out.append({"slug": name, "title": title, "dir": path})
    return out


def resolve(slug=None):
    """Resolve a slug or folder path to an existing game.

    With folders open, ``slug`` is matched against each open folder's basename
    (its slug) or its path; omitted picks the first open folder. In the
    workspace a ``slug`` that is itself a game directory path is opened
    directly, otherwise it names a folder under ``games/`` (first if omitted).
    """
    if _opened:
        if slug:
            path = _find_opened(slug)
            return game_from_dir(path) if path else None
        return game_from_dir(_opened[0])
    if slug and is_game_dir(slug):
        return game_from_dir(slug)
    games = list_games()
    if slug:
        for g in games:
            if g["slug"] == slug:
                return g
        return None
    if not games:
        return None
    return games[0]


def _skeleton(title):
    """A minimal, valid game.md for a brand-new game."""
    game = {"title": title, "prompt": "", "start": [], "seed": 42,
            "steps": scenefile.STEPS_DEFAULT, "cfg": 6.0, "width": 512,
            "height": 128}
    doc = {
        "game": game,
        "arts": [{"id": "title", "prompt": "game title screen",
                  "seed": None, "steps": None, "cfg": None, "width": None,
                  "height": None}],
        "scenes": [{"id": "start", "title": "Start", "art": "title",
                    "ending": None, "text": ["A new adventure begins."],
                    "opts": []}],
    }
    return scenefile.serialize(doc)


def _new_game_folder(path, title):
    """Write a fresh game skeleton at ``path`` (which must not exist yet)."""
    if os.path.exists(path):
        raise FileExistsError(f"game folder already exists: {path}")
    os.makedirs(os.path.join(path, "assets", "gen"), exist_ok=True)
    os.makedirs(os.path.join(path, BUILD_NAME, "scene_banks"), exist_ok=True)
    title = (title or os.path.basename(path) or "game").strip()
    with open(os.path.join(path, "game.md"), "w", encoding="utf-8") as f:
        f.write(_skeleton(title))
    return {"slug": os.path.basename(os.path.normpath(path)), "title": title,
            "dir": os.path.abspath(path)}


def create(name, title=None):
    """Create a new game folder in the ``games/`` workspace."""
    slug = slugify(name)
    if not valid_slug(slug):
        raise ValueError(f"invalid game name: {name!r}")
    return _new_game_folder(os.path.join(GAMES_DIR, slug), title or name)


def create_at(parent, name, title=None):
    """Create a new game folder at ``parent/<name>`` (folder-open model)."""
    slug = slugify(name)
    if not valid_slug(slug):
        raise ValueError(f"invalid game name: {name!r}")
    parent = os.path.abspath(os.path.expanduser(parent or ""))
    if not os.path.isdir(parent):
        raise FileNotFoundError(f"no such folder: {parent or '(empty)'}")
    return _new_game_folder(os.path.join(parent, slug), title or name)


def duplicate(src_slug, name, title=None):
    """Copy an existing game (authoring files only) to a new folder."""
    if _opened:
        raise ValueError("duplicate is only available in the games/ workspace")
    src = resolve(src_slug)
    if src is None:
        raise FileNotFoundError(f"no such game: {src_slug}")
    slug = slugify(name)
    if not valid_slug(slug):
        raise ValueError(f"invalid game name: {name!r}")
    dst = os.path.join(GAMES_DIR, slug)
    if os.path.exists(dst):
        raise FileExistsError(f"game '{slug}' already exists")

    def ignore(_dir, names):
        drop = set()
        for n in names:
            if n == BUILD_NAME:
                drop.add(n)
            elif n in _GEN_FILES or n.endswith(_GEN_SUFFIXES):
                drop.add(n)
            elif n.endswith(".bak"):
                drop.add(n)
            elif n.startswith("scene_") and n.endswith((".asm", ".h", ".txt")):
                drop.add(n)
        return drop

    shutil.copytree(src["dir"], dst, ignore=ignore)
    os.makedirs(os.path.join(dst, "assets", "gen"), exist_ok=True)
    os.makedirs(os.path.join(dst, BUILD_NAME, "scene_banks"), exist_ok=True)

    md = os.path.join(dst, "game.md")
    doc = scenefile.parse(md)
    if title:
        doc["game"]["title"] = title
    with open(md, "w", encoding="utf-8") as f:
        f.write(scenefile.serialize(doc))
    return {"slug": slug, "title": doc["game"].get("title", ""), "dir": dst}


def delete(slug):
    path = game_dir(slug)
    if path is None or not os.path.isdir(path):
        raise FileNotFoundError(f"no such game: {slug}")
    shutil.rmtree(path)
    return True


def rename(old_slug, name):
    """Rename a game folder to a new slug, keeping its files and title."""
    if _opened:
        raise ValueError("rename is only available in the games/ workspace")
    src = resolve(old_slug)
    if src is None:
        raise FileNotFoundError(f"no such game: {old_slug}")
    slug = slugify(name)
    if not valid_slug(slug):
        raise ValueError(f"invalid game name: {name!r}")
    if slug == src["slug"]:
        return src
    dst = os.path.join(GAMES_DIR, slug)
    if os.path.exists(dst):
        raise FileExistsError(f"game '{slug}' already exists")
    os.rename(src["dir"], dst)
    # Build outputs are named after the slug; a renamed folder would otherwise
    # keep a stale <old_slug>.tap/.sna the emulator can no longer address.
    for suffix in (".tap", ".sna"):
        stale = os.path.join(dst, f"{src['slug']}{suffix}")
        if os.path.exists(stale):
            os.remove(stale)
    return {"slug": slug, "title": src["title"], "dir": dst}


# Honour RVN_GAMES (a JSON list of folders, the desktop app's open tabs) and
# RVN_GAME (a single folder) at import so every tool (server, build.py,
# gen_scenes.py, make_tap.py, make_sna.py) resolves the same game(s). The old
# ZXAD_GAMES/ZXAD_GAME names remain accepted as fallbacks.
_env_games = os.environ.get("RVN_GAMES") or os.environ.get("ZXAD_GAMES")
if _env_games:
    try:
        for _p in json.loads(_env_games):
            try:
                open_folder(_p)
            except (OSError, ValueError):
                pass
    except (ValueError, TypeError):
        pass
_env_game = os.environ.get("RVN_GAME") or os.environ.get("ZXAD_GAME")
if _env_game:
    # RVN_GAME pins the game a child build works on. Add it even when
    # RVN_GAMES already seeded other tabs (a desktop session opened at
    # runtime), otherwise the pinned game would not resolve by slug.
    try:
        _env_game = _norm(_env_game)
        if is_game_dir(_env_game):
            open_folder(_env_game)
    except (OSError, ValueError):
        pass


if __name__ == "__main__":
    for g in list_games():
        print(f"{g['slug']}\t{g['title']}")
