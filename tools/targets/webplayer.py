"""Web Player target (internal).

Writes the self-contained ``<game>/web/`` player shell, the selected native
systems' browser emulators and their built artifacts, without the mobile-first
HTML5 story.  The ordinary build runs this target last when the HTML5 system is
not selected; it can also be requested explicitly with
``build.py build <game> webplayer``.  The ``web`` target adds the story.
"""
from __future__ import annotations

from .base import BuildResult, Target
from .web import _available, _folder_bytes


def _build(ctx):
    import webgame

    info = webgame.export_player(ctx.slug)
    result = BuildResult(target="webplayer")
    for warning in info.get("warnings") or []:
        result.warnings.append(warning)
    result.add_output(info["path"], "web-player",
                      _folder_bytes(info["path"]))
    return result


TARGET = Target(
    id="webplayer",
    label="Web Player",
    description="Browser player shell and the selected systems' emulators. "
                "The automatic build step; the HTML5 game target adds the "
                "mobile-first story.",
    outputs=("web/",),
    build=_build,
    available=_available,
    hidden=True,
    emulator="webplayer",
    machine="HTML5",
    engine="HTML5",
)
