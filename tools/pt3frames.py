"""Shared PT3 replay front-end for build-time music conversion.

Both the SMS SN76489 converter and the Game Boy Color APU converter replay a
PT3 module through the pinned ``spectrumizer`` package.  This module owns the
chip-independent part: parse and validate the module, build the AY period
table, and model the AY hardware-envelope ramp.  The target converters own the
register translation and wire format.

``spectrumizer`` is an editor dependency (``tools/requirements.txt``); the
import is lazy so builds for targets without music keep working when it is
absent.
"""
from __future__ import annotations

AY_CLOCK = 1773400
FRAME_HZ = 50


class Pt3MusicError(Exception):
    """A PT3 module cannot be replayed or converted."""


def spectrumizer():
    """Return the pinned ``(player, audio)`` modules."""
    try:
        from spectrumizer.pt3 import player
        from spectrumizer import audio
    except ImportError as err:  # pragma: no cover - depends on the install
        raise Pt3MusicError(
            "music conversion needs the pinned spectrumizer package; install "
            "tools/requirements.txt or use the editor Docker image") from err
    return player, audio


def envelope_levels(shape):
    """An AY envelope shape (R13) as a list of 0..15 levels + a loop index."""
    cont, att, alt, hold = shape & 8, shape & 4, shape & 2, shape & 1
    ramp = list(range(16)) if att else list(range(15, -1, -1))
    if not cont:
        return ramp + [0], len(ramp)
    if hold:
        return ramp + [15 - ramp[-1] if alt else ramp[-1]], len(ramp)
    if alt:
        return ramp + ramp[::-1], 0
    return ramp, 0


ENV_SHAPES = [envelope_levels(s) for s in range(16)]


def replay(data, *, name=""):
    """Return ``(periods, frames)`` for a validated PT3 module.

    ``frames`` yields ``(channels, noise_period, envelope)`` at 50 Hz, exactly
    as documented by ``spectrumizer.pt3.player.iter_frames``.
    """
    player, audio = spectrumizer()
    try:
        module = player.parse_module(data)
    except ValueError as err:
        raise Pt3MusicError(f"{name or 'PT3'}: {err}") from err
    warnings = player.foreign_warnings(module)
    if warnings:
        raise Pt3MusicError(
            f"{name or 'PT3'}: unsupported PT3 feature(s): "
            + "; ".join(warnings))
    return audio.build_pt3_table(), player.iter_frames(module)
