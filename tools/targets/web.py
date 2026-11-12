"""Web player target.

The web build is not a native binary: it writes a self-contained
``<game>/web/`` folder with the mobile-first novel, the browser emulators of
the other selected systems and their built artifacts.  Selecting Web under
``# Systems`` therefore makes the Build button (and ``tools/build.py``)
produce the web player alongside the native builds.
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
                "playable web emulator for every other selected system. Every "
                "build refreshes the emulator player; ticking Web adds the "
                "novel.",
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
