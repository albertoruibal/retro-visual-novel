"""Web player target.

The web build is not a native binary: it writes a self-contained
``<game>/web/`` folder with the mobile-first novel, the browser emulators of
the other selected systems and their built artifacts.  Selecting Web under
``# Systems`` therefore makes the Build button (and ``tools/build.py``)
produce the web player alongside the native builds.
"""
from __future__ import annotations

import os

from .base import BuildResult, Target


def _available():
    try:
        import webgame  # noqa: F401 - the exporter owns the runtime files
    except Exception as err:                    # noqa: BLE001
        return False, str(err)
    return True, ""


def _folder_bytes(path):
    return sum(os.path.getsize(os.path.join(base, name))
               for base, _dirs, files in os.walk(path)
               for name in files)


def _build(ctx):
    import webgame

    info = webgame.export_web(ctx.slug)
    result = BuildResult(target="web")
    for warning in info.get("warnings") or []:
        result.warnings.append(warning)
    result.add_output(info["path"], "web-player",
                      _folder_bytes(info["path"]))
    return result


TARGET = Target(
    id="web",
    label="Web",
    description="Standalone browser player: the mobile-first novel plus a "
                "playable web emulator for every other selected system.",
    outputs=("web/",),
    build=_build,
    available=_available,
    emulator="webplayer",
    machine="HTML5",
)
