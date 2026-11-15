"""HTML5 game target.

The HTML5 build is not a native binary: it writes a self-contained
``<game>/web/`` folder with the mobile-first story, the browser emulators of
the other selected systems and their built artifacts.  The ``webplayer`` target
writes the same Web Player without the HTML5 story; this target is the HTML5
game and is selected with ``## web`` under ``# Systems``.
"""
from __future__ import annotations

import io
import os

import scenefile

from .base import BuildResult, Target, TargetOption, mono_option


def _preview(src, conv, options, game=None):
    import webgame
    from PIL import Image

    rows = max(1, int(options.get("art_rows") or 10) // 2)
    im = Image.open(src).convert("RGB")
    img = webgame.render_web_art(im, conv or {}, rows)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


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

    info = webgame.export_game(ctx.slug)
    result = BuildResult(target="web")
    for warning in info.get("warnings") or []:
        result.warnings.append(warning)
    result.add_output(info["path"], "web-game",
                      _folder_bytes(info["path"]))
    return result


TARGET = Target(
    id="web",
    label="HTML5",
    description="HTML5 game: the mobile-first story plus the Web Player shell "
                "and a playable browser emulator for every other selected "
                "system. The hidden Web Player target refreshes the emulators "
                "without the story; ticking HTML5 adds it.",
    outputs=("web/",),
    options=(
        TargetOption(
            "art_rows", "Art rows", "choice", 10,
            (8, 10, 12, 14, 16),
            "Height of the novel's picture band in 8px character rows (even "
            "8..16, default 10 = 256x80). Independent of the native systems.",
            minimum=8, maximum=16),
        mono_option(),
        TargetOption(
            "dither", "Dithering", "choice", scenefile.DEFAULT_DITHER,
            scenefile.DITHER_MODES,
            help="Used by Black and white: off becomes a 2x2 Bayer dither, "
                 "ordered schemes range from coarse (2x2) to fine (8x8), and "
                 "the error-diffusion kernels smooth gradients."),
    ),
    build=_build,
    preview=_preview,
    available=_available,
    emulator="webplayer",
    machine="HTML5",
    engine="HTML5",
)
