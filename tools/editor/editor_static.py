"""Built-artifact and vendored static-file serving."""

from __future__ import annotations

from server import *  # noqa: F401,F403 - shared state and helpers

from editor_games import *

def tap_file(slug, name):
    """Serve a built game file (.tap/.sna) to the embedded emulator.

    Only the game's own build outputs are exposed, so /api/tap/<slug>/...
    can't be used to walk the games directory.
    """
    game = _game_or_error(slug)
    if not (name.endswith(".tap") or name.endswith(".sna")):
        raise ValueError("only .tap / .sna can be served")
    # the build writes exactly games/<slug>/<slug>.tap; accept only that name
    if name != f"{slug}.tap" and name != f"{slug}.sna":
        raise ValueError(f"no such build output: {name}")
    path = os.path.join(game["dir"], name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"{name} not built yet — run Build first")
    mt = ("application/octet-stream" if name.endswith(".tap")
          else "application/octet-stream")
    return open(path, "rb").read(), mt



def artifact_file(slug, name):
    """Serve one built target artifact to the web emulators.

    Only the game's own target outputs are exposed; the name must be
    ``<slug>.<ext>`` and the extension must be a known build output.
    """
    game = _game_or_error(slug)
    allowed = (".tap", ".sna", ".sms", ".rom", ".dsk", ".gb", ".gbc", ".nex")
    if not name.endswith(allowed):
        raise ValueError(f"unsupported artifact: {name}")
    if name.rsplit(".", 1)[0] != game["slug"]:
        raise ValueError(f"no such build output: {name}")
    path = os.path.join(game["dir"], name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"{name} not built yet — run Build first")
    return open(path, "rb").read(), "application/octet-stream"



def emulator_file(rel):
    """Serve a vendored emulator runtime with correct extension MIMEs."""
    rel = rel.replace("\\", "/")
    full = os.path.realpath(os.path.join(EMULATOR, rel))
    if not full.startswith(os.path.realpath(EMULATOR) + os.sep):
        raise ValueError("bad emulator path")
    if not os.path.isfile(full):
        raise FileNotFoundError(rel)
    ctype = ("application/wasm" if full.endswith(".wasm")
             else "text/javascript" if full.endswith(".js")
             else "text/css" if full.endswith(".css")
             else "text/html" if full.endswith(".html")
             else "application/json" if full.endswith(".json")
             else "image/png" if full.endswith(".png")
             else "image/svg+xml" if full.endswith(".svg")
             else "application/octet-stream")
    return open(full, "rb").read(), ctype



def monaco_file(rel):
    """Serve the vendored Monaco editor assets (static/monaco/).

    Like ``emulator_file``, the path is confined to its own tree. Monaco's
    loader resolves modules and the codicon font relative to its script URL, so
    nested paths must be preserved (``/static/`` only serves top-level files).
    """
    rel = rel.replace("\\", "/")
    full = os.path.realpath(os.path.join(MONACO, rel))
    if not full.startswith(os.path.realpath(MONACO) + os.sep):
        raise ValueError("bad monaco path")
    if not os.path.isfile(full):
        raise FileNotFoundError(rel)
    ctype = ("text/javascript" if full.endswith(".js")
             else "text/css" if full.endswith(".css")
             else "font/ttf" if full.endswith(".ttf")
             else "application/octet-stream")
    return open(full, "rb").read(), ctype



__all__ = [
    'tap_file',
    'artifact_file',
    'emulator_file',
    'monaco_file',
]
