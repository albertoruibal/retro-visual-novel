"""Convert a PT3 module to a Game Boy Color APU register stream.

The Game Boy's four-channel APU is not AY compatible, so the PT3 module is
replayed here with the pinned ``spectrumizer`` decoder and the resulting per
50 Hz frame AY state is translated to Game Boy register writes:

  * AY tone channels A/B/C -> pulse 1 / pulse 2 / the wave channel.
  * AY noise -> the APU's single noise channel.
  * AY hardware envelope -> a per-frame volume approximation.
  * Low AY notes that exceed the APU's 11-bit divider are folded up an octave
    until they fit.

The emitted stream is read directly from banked ROM by
``src/gb/gb_music.c``.  A command is the low byte of an APU register
(``0x10..0x3F``, i.e. ``0xFF10..0xFF3F``) followed by its value, a wait run
``0x80 | (n - 1)``, an end marker ``0x00`` or a loop marker ``0x01``.  Wait runs
delimit frames and skip empty ones.  The player initialises NR50/NR51/NR52 and
the wave RAM; the converter only emits the per-frame changes.

``spectrumizer`` is an editor dependency (``tools/requirements.txt``); the
import is lazy so non-Game-Boy builds keep working when it is absent.
"""
from __future__ import annotations

import math

import pt3frames

AY_CLOCK = pt3frames.AY_CLOCK
FRAME_HZ = pt3frames.FRAME_HZ
GB_STREAM_MAX = 0x4000 * 16

CMD_END = 0x00
CMD_LOOP = 0x01
CMD_WAIT = 0x80

NR10 = 0x10
NR11 = 0x11
NR12 = 0x12
NR13 = 0x13
NR14 = 0x14
NR21 = 0x16
NR22 = 0x17
NR23 = 0x18
NR24 = 0x19
NR30 = 0x1A
NR32 = 0x1C
NR33 = 0x1D
NR34 = 0x1E
NR42 = 0x21
NR43 = 0x22
NR44 = 0x23


class GbMusicError(pt3frames.Pt3MusicError):
    """A PT3 module cannot be converted to a Game Boy APU stream."""


def _gb_period(periods, note, tone_ofs):
    note = max(0, min(95, note))
    period = max(1, periods[note] + tone_ofs)
    while True:
        x = 2048 - int(round(131072.0 * 16.0 * period / AY_CLOCK))
        if x >= 0:
            return min(2047, x)
        period = (period + 1) // 2


def _gb_noise(ay_r6):
    period = max(1, ay_r6 & 0x1F)
    target = AY_CLOCK / (16.0 * period)
    best = None
    for shift in range(16):
        for code, divisor in enumerate((0.5, 1, 2, 3, 4, 5, 6, 7)):
            freq = 262144.0 / (divisor * (1 << (shift + 1)))
            err = abs(math.log(freq / target))
            if best is None or err < best[0]:
                best = (err, (shift << 4) | code)
    return best[1]


def _wave_level(amp):
    if amp <= 0:
        return 0
    if amp >= 12:
        return 1
    if amp >= 5:
        return 2
    return 3


def _put(out, reg, val, last, force=False):
    val &= 0xFF
    if not force and last.get(reg) == val:
        return
    out.append(reg)
    out.append(val)
    last[reg] = val


def _emit_frame(frame, r6, env, periods, prev):
    out = bytearray()
    last = prev["reg"]
    env_period, env_shape, env_retrig = env
    use_env = any(c[4] for c in frame)
    level = None
    if use_env:
        levels, loop = pt3frames.ENV_SHAPES[env_shape & 0x0F]
        if env_retrig:
            prev["env_pos"], prev["env_acc"] = 0, 0.0
        if prev["env_pos"] >= len(levels):
            prev["env_pos"] = loop
        level = levels[prev["env_pos"]]
        prev["env_acc"] += (AY_CLOCK / 16.0 / max(1, env_period)) / FRAME_HZ
        while prev["env_acc"] >= 1.0:
            prev["env_acc"] -= 1.0
            prev["env_pos"] += 1
            if prev["env_pos"] >= len(levels):
                prev["env_pos"] = loop

    for ci in range(2):
        note, amp, tone_on, _noise_on, chan_env, tone_ofs = frame[ci]
        st = prev["pulse"][ci]
        if note is None or not tone_on:
            vol = 0
        else:
            vol = level if chan_env else amp
        reg_v = NR12 + ci * 5
        reg_low = NR13 + ci * 5
        reg_high = NR14 + ci * 5
        if vol <= 0:
            if st["active"] or last.get(reg_v) != 0:
                _put(out, reg_v, 0, last)
            st["active"] = False
            continue
        _put(out, reg_v, vol << 4, last)
        freq = _gb_period(periods, note, tone_ofs)
        if freq != st["freq"]:
            _put(out, reg_low, freq & 0xFF, last)
            high = (freq >> 8) & 0x07
            trigger = not st["active"]
            if trigger:
                high |= 0x80
            _put(out, reg_high, high, last, force=trigger)
            st["freq"], st["active"] = freq, True
        elif not st["active"]:
            _put(out, reg_low, freq & 0xFF, last, force=True)
            _put(out, reg_high, 0x80 | ((freq >> 8) & 0x07), last,
                 force=True)
            st["active"] = True

    note, amp, tone_on, _noise_on, chan_env, tone_ofs = frame[2]
    st = prev["wave"]
    vol = 0 if note is None or not tone_on else (level if chan_env else amp)
    level3 = _wave_level(vol)
    if level3 == 0:
        if st["active"] or last.get(NR32) != 0:
            _put(out, NR32, 0, last)
        st["active"] = False
    else:
        _put(out, NR32, level3 << 5, last)
        freq = _gb_period(periods, note, tone_ofs)
        if freq != st["freq"]:
            _put(out, NR33, freq & 0xFF, last)
            high = (freq >> 8) & 0x07
            trigger = not st["active"]
            if trigger:
                high |= 0x80
            _put(out, NR34, high, last, force=trigger)
            st["freq"], st["active"] = freq, True
        elif not st["active"]:
            _put(out, NR33, freq & 0xFF, last, force=True)
            _put(out, NR34, 0x80 | ((freq >> 8) & 0x07), last,
                 force=True)
            st["active"] = True

    noise_vol = 0
    for _note, amp, _tone_on, noise_on, chan_env, _tone_ofs in frame:
        if noise_on:
            v = level if chan_env else amp
            if v > noise_vol:
                noise_vol = v
    st = prev["noise"]
    if noise_vol <= 0:
        if st["active"] or last.get(NR42) != 0:
            _put(out, NR42, 0, last)
        st["active"] = False
    else:
        _put(out, NR42, noise_vol << 4, last)
        rate = _gb_noise(r6)
        if rate != st["freq"]:
            _put(out, NR43, rate, last)
            trigger = not st["active"]
            _put(out, NR44, 0x80 if trigger else 0x00, last, force=trigger)
            st["freq"], st["active"] = rate, True
        elif not st["active"]:
            _put(out, NR43, rate, last, force=True)
            _put(out, NR44, 0x80, last, force=True)
            st["active"] = True

    return out


def _wait_run(n):
    out = bytearray()
    while n:
        chunk = min(128, n)
        out.append(CMD_WAIT | (chunk - 1))
        n -= chunk
    return out


def _build_stream(frames):
    out = bytearray()
    empty = 0
    for writes in frames:
        if not writes:
            empty += 1
            continue
        if empty:
            out += _wait_run(empty)
            empty = 0
        out += writes
        out.append(CMD_WAIT)
    if empty:
        out += _wait_run(empty)
    out.append(CMD_END)
    return bytes(out)


def _decode_ticks(stream, ticks):
    decoded = []
    writes = bytearray()
    pos = 0
    n = len(stream)
    while len(decoded) < ticks:
        if pos >= n:
            raise GbMusicError("stream ended before the last frame")
        cmd = stream[pos]
        pos += 1
        if cmd == CMD_END:
            raise GbMusicError("stream ended before the last frame")
        if cmd == CMD_LOOP:
            raise GbMusicError("unexpected loop marker")
        if cmd >= CMD_WAIT:
            decoded.append(bytes(writes))
            writes.clear()
            extra = cmd & 0x7F
            if len(decoded) + extra > ticks:
                raise GbMusicError("wait run overshoots the last frame")
            decoded.extend([b""] * extra)
            continue
        if NR10 <= cmd <= 0x3F:
            if pos >= n:
                raise GbMusicError("truncated register write")
            writes.append(cmd)
            writes.append(stream[pos])
            pos += 1
            continue
        raise GbMusicError(f"invalid command 0x{cmd:02X}")
    if pos < n and stream[pos] != CMD_END:
        raise GbMusicError("trailing data after the last frame")
    if pos + 1 != n:
        raise GbMusicError("trailing bytes after the end marker")
    return decoded


def _new_state():
    state = {
        "reg": {},
        "pulse": [{"active": False, "freq": None},
                  {"active": False, "freq": None}],
        "wave": {"active": False, "freq": None},
        "noise": {"active": False, "freq": None},
        "env_pos": 0,
        "env_acc": 0.0,
    }
    return state


def pt3_to_gb(data, *, name=""):
    """Return a Game Boy APU register stream for a PT3 module."""
    try:
        periods, frames_iter = pt3frames.replay(data, name=name)
    except pt3frames.Pt3MusicError as err:
        raise GbMusicError(str(err)) from err

    prev = _new_state()
    frames = [_emit_frame(frame, r6, env, periods, prev)
              for frame, r6, env in frames_iter]
    stream = _build_stream(frames)
    if _decode_ticks(stream, len(frames)) != frames:
        raise GbMusicError(f"{name or 'PT3'}: GB stream self-check failed")
    if len(stream) > GB_STREAM_MAX:
        raise GbMusicError(
            f"{name or 'PT3'}: {len(stream)}B stream exceeds the "
            f"{GB_STREAM_MAX}B limit; shorten the song")
    return stream


def main(argv=None):
    import argparse
    import sys

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pt3")
    ap.add_argument("-o", "--output", help="write the raw APU stream")
    args = ap.parse_args(argv)
    try:
        with open(args.pt3, "rb") as f:
            data = f.read()
        stream = pt3_to_gb(data, name=args.pt3)
    except OSError as err:
        print(f"gbmusic: {err}", file=sys.stderr)
        return 2
    except GbMusicError as err:
        print(f"gbmusic: {err}", file=sys.stderr)
        return 1
    if args.output:
        with open(args.output, "wb") as f:
            f.write(stream)
    print(f"{args.pt3}: {len(stream)}B APU stream")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
