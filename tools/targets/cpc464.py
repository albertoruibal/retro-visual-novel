"""Amstrad CPC 464 target.

The 464 has 64K and no extra RAM banks.  The story stays resident (as on the
6128), but the compressed art/song blobs are stored in the GAME.Bn files on
the disk and loaded one at a time through AMSDOS by ``cpc_disk.asm``.
"""
from __future__ import annotations

from .cpc import (_available, _preview, _validate as _validate_cpc,
                  build_cpc, cpc_options)
from .base import Target


def _build(ctx):
    return build_cpc(ctx, "cpc464", "--cpc464", "-cpc464.dsk",
                     disk_stream=True)


def _validate(ctx):
    issues = _validate_cpc(ctx)
    for issue in issues:
        issue["target"] = "cpc464"
    return issues


TARGET = Target(
    id="cpc464",
    label="Amstrad CPC 464",
    description="64K Amstrad CPC 464 build: compressed art/song blobs are "
                "streamed from the disk one at a time (needs a disk drive).",
    outputs=(".dsk",),
    artifact_suffix="-cpc464",
    options=cpc_options(8),
    build=_build,
    validate=_validate,
    preview=_preview,
    available=_available,
    emulator="cpc464",
    machine="464",
    colors=4,
    band_width=320,
)
