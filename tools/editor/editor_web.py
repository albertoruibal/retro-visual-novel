"""Static Web Player serving, export and zip routes.

The player is frontend-only: ``tools/webgame_runtime/`` (story) and
``tools/webplayer_runtime/`` (system selector) are plain classic-script pages
copied into ``<game>/web/`` by ``tools/webgame.py``.  The editor's Emulator tab
previews that exported folder, so the browser never asks the server to build or
render the story at request time.
"""

from __future__ import annotations

import mimetypes
import os

from server import *  # noqa: F401,F403 - shared state and helpers

from editor_games import *  # noqa: F401,F403

import webgame


def _web_root(slug):
    game = _game_or_error(slug)
    return os.path.realpath(os.path.join(game["dir"], webgame.WEB_DIRNAME))


def web_exported_file(slug, name):
    """Serve one static file from the exported ``web/`` folder.

    ``name`` is a relative path inside the export (for example ``app.js`` or
    ``assets/art/title.png``); containment is checked after resolving it, so a
    request cannot walk outside the game's export folder.
    """
    if not name or "\\" in name:
        raise ValueError("bad runtime path")
    root = _web_root(slug)
    full = os.path.realpath(os.path.join(root, name))
    if full != root and not full.startswith(root + os.sep):
        raise ValueError("bad runtime path")
    if not os.path.isfile(full):
        raise FileNotFoundError(f"no such player file: {name}")
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    return open(full, "rb").read(), ctype


def web_export(slug):
    """Write ``<game>/web/`` and return its path plus the zip URL."""
    return webgame.export_web(slug)


def web_zip(slug):
    """A zip of the current player, re-exporting the folder first."""
    return webgame.export_zip(slug)


__all__ = [
    'web_exported_file',
    'web_export',
    'web_zip',
]
