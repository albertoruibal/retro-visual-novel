"""Convert a PT3 module to a NES APU register stream.

The NES 2A03 APU is not AY compatible, so the PT3 module is replayed here with
the pinned ``spectrumizer`` decoder and the resulting per-50 Hz-frame AY state
is translated to NES register writes:

  * AY tone channels A/B -> pulse 1 / pulse 2.
  * AY tone channel C -> the triangle channel (on/off; the triangle has no
    volume control).
  * AY noise -> the APU noise channel.
  * AY hardware envelope -> a per-frame volume approximation.
  * Low AY notes that exceed the 11-bit timer are folded up an octave until
    they fit (pulse and triangle use different timer scales).

The emitted stream is read directly from banked PRG by
``src/nes/nes_audio_tick.s``.  A command is the register offset plus
``CMD_REG`` (``0x20..0x37`` for ``$4000..$4017``) followed by its value, a
wait run ``0x80 | (n - 1)``, an end marker ``0x00`` or a loop marker ``0x01``.
The player initialises the APU and the frame counter; the converter only
emits the per-frame changes.

``spectrumizer`` is an editor dependency (``tools/requirements.txt``); the
import is lazy so non-NES builds keep working when it is absent.
"""
from __future__ import annotations

import math

import pt3frames

AY_CLOCK = pt3frames.AY_CLOCK
FRAME_HZ = pt3frames.FRAME_HZ
NES_CPU = 1789773

CMD_END = 0x00
CMD_LOOP = 0x01
CMD_WAIT = 0x80
CMD_REG = 0x20

NES_STREAM_MAX = 0x4000 * 14

APU_P1_CTRL = 0x00
APU_P1_LO = 0x02
APU_P1_HI = 0x03
APU_P2_CTRL = 0x04
APU_P2_LO = 0x06
APU_P2_HI = 0x07
APU_TRI_CTRL = 0x08
APU_TRI_LO = 0x0A
APU_TRI_HI = 0x0B
APU_NOISE_CTRL = 0x0C
APU_NOISE_PERIOD = 0x0E
APU_NOISE_HI = 0x0F

NES_NOISE_PERIODS = (4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508,
                     762, 1016, 2034, 4068)


class NesMusicError(pt3frames.Pt3MusicError):
    """A PT3 module cannot be converted to a NES APU stream."""


def _period(periods, note, tone_ofs, scale):
    note = max(0, min(95, note))
    period = max(1, periods[note] + tone_ofs)
    while True:
        timer = int(round(NES_CPU * period / (scale * AY_CLOCK))) - 1
        if timer <= 0x7FF:
            break
        period = (period + 1) // 2
    return max(8, min(2047, timer))


def _pulse_timer(periods, note, tone_ofs):
    return _period(periods, note, tone_ofs, 1.0)


def _tri_timer(periods, note, tone_ofs):
    # The triangle steps 32 times per cycle, so its timer is half the pulse
    # timer for the same AY period.
    return _period(periods, note, tone_ofs, 2.0)


def _noise_period(ay_r6):
    target = AY_CLOCK / (16.0 * max(1, ay_r6 & 0x1F))
    best = None
    for index, cycles in enumerate(NES_NOISE_PERIODS):
        freq = NES_CPU / cycles
        err = abs(math.log(freq / target))
        if best is None or err < best[0]:
            best = (err, index)
    return best[1]


def _put(out, reg, value, last, force=False):
    value &= 0xFF
    if not force and last.get(reg) == value:
        return
    out.append(CMD_REG + reg)
    out.append(value)
    last[reg] = value


def _envelope_level(env, prev):
    env_period, env_shape, env_retrig = env
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
    return level


def _emit_frame(frame, r6, env, periods, prev):
    out = bytearray()
    last = prev["reg"]
    use_env = any(c[4] for c in frame)
    level = _envelope_level(env, prev) if use_env else None

    for ci in range(2):
        note, amp, tone_on, _noise_on, chan_env, tone_ofs = frame[ci]
        st = prev["pulse"][ci]
        if note is None or not tone_on:
            vol = 0
        else:
            vol = level if chan_env else amp
        ctrl_reg = APU_P1_CTRL + ci * 4
        lo_reg = APU_P1_LO + ci * 4
        hi_reg = APU_P1_HI + ci * 4
        if vol <= 0:
            if st["active"] or last.get(ctrl_reg) != 0x30:
                _put(out, ctrl_reg, 0x30, last)
            st["active"] = False
            continue
        _put(out, ctrl_reg, 0xB0 | min(15, max(0, vol)), last)
        timer = _pulse_timer(periods, note, tone_ofs)
        if timer != st["timer"] or not st["active"]:
            _put(out, lo_reg, timer & 0xFF, last)
            _put(out, hi_reg, 0xF8 | ((timer >> 8) & 0x07), last,
                 force=True)
            st["timer"], st["active"] = timer, True

    note, amp, tone_on, _noise_on, chan_env, tone_ofs = frame[2]
    st = prev["triangle"]
    vol = 0 if note is None or not tone_on else (level if chan_env else amp)
    if vol <= 0:
        if st["active"] or last.get(APU_TRI_CTRL) != 0:
            _put(out, APU_TRI_CTRL, 0, last)
        st["active"] = False
    else:
        trigger = not st["active"]
        if trigger:
            _put(out, APU_TRI_CTRL, 0x81, last)
        timer = _tri_timer(periods, note, tone_ofs)
        if timer != st["timer"] or trigger:
            _put(out, APU_TRI_LO, timer & 0xFF, last)
            _put(out, APU_TRI_HI, 0xF8 | ((timer >> 8) & 0x07), last,
                 force=trigger)
            st["timer"], st["active"] = timer, True

    noise_vol = 0
    for _note, amp, _tone_on, noise_on, chan_env, _tone_ofs in frame:
        if noise_on:
            v = level if chan_env else amp
            if v > noise_vol:
                noise_vol = v
    st = prev["noise"]
    if noise_vol <= 0:
        if st["active"] or last.get(APU_NOISE_CTRL) != 0x30:
            _put(out, APU_NOISE_CTRL, 0x30, last)
        st["active"] = False
    else:
        _put(out, APU_NOISE_CTRL, 0x30 | min(15, max(0, noise_vol)), last)
        rate = _noise_period(r6)
        if rate != st["rate"]:
            _put(out, APU_NOISE_PERIOD, rate, last)
            st["rate"] = rate
        if not st["active"]:
            _put(out, APU_NOISE_HI, 0xF8, last, force=True)
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
            raise NesMusicError("stream ended before the last frame")
        cmd = stream[pos]
        pos += 1
        if cmd == CMD_END:
            raise NesMusicError("stream ended before the last frame")
        if cmd == CMD_LOOP:
            raise NesMusicError("unexpected loop marker")
        if cmd >= CMD_WAIT:
            decoded.append(bytes(writes))
            writes.clear()
            extra = cmd & 0x7F
            if len(decoded) + extra > ticks:
                raise NesMusicError("wait run overshoots the last frame")
            decoded.extend([b""] * extra)
            continue
        if CMD_REG <= cmd < CMD_REG + 0x18:
            if pos >= n:
                raise NesMusicError("truncated register write")
            writes.append(cmd)
            writes.append(stream[pos])
            pos += 1
            continue
        raise NesMusicError(f"invalid command 0x{cmd:02X}")
    if pos < n and stream[pos] != CMD_END:
        raise NesMusicError("trailing data after the last frame")
    if pos + 1 != n:
        raise NesMusicError("trailing bytes after the end marker")
    return decoded


def _new_state():
    return {
        "reg": {},
        "pulse": [{"active": False, "timer": None},
                  {"active": False, "timer": None}],
        "triangle": {"active": False, "timer": None},
        "noise": {"active": False, "rate": None},
        "env_pos": 0,
        "env_acc": 0.0,
    }


def pt3_to_nes(data, *, name=""):
    """Return a NES APU register stream for a PT3 module."""
    try:
        periods, frames_iter = pt3frames.replay(data, name=name)
    except pt3frames.Pt3MusicError as err:
        raise NesMusicError(str(err)) from err

    prev = _new_state()
    frames = [_emit_frame(frame, r6, env, periods, prev)
              for frame, r6, env in frames_iter]
    stream = _build_stream(frames)
    if _decode_ticks(stream, len(frames)) != frames:
        raise NesMusicError(f"{name or 'PT3'}: NES stream self-check failed")
    if len(stream) > NES_STREAM_MAX:
        raise NesMusicError(
            f"{name or 'PT3'}: {len(stream)}B stream exceeds the "
            f"{NES_STREAM_MAX}B limit; shorten the song")
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
        stream = pt3_to_nes(data, name=args.pt3)
    except OSError as err:
        print(f"nesmusic: {err}", file=sys.stderr)
        return 2
    except NesMusicError as err:
        print(f"nesmusic: {err}", file=sys.stderr)
        return 1
    if args.output:
        with open(args.output, "wb") as f:
            f.write(stream)
    print(f"{args.pt3}: {len(stream)}B NES APU stream")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
