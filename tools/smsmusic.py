"""Convert a PT3 module to an SN76489 PSG stream for the Master System.

The AY-3-8910 and the Master System's SN76489 are not register compatible, so
the PT3 module is replayed here (using the pinned ``spectrumizer`` decoder) and
the resulting per-frame AY state is translated to SN76489 register writes:

  * AY tone channels A/B/C -> SN76489 channels 0/1/2.
  * AY noise -> the SN76489's single noise channel 3 (white noise).
  * AY hardware envelope -> a per-frame volume approximation.
  * Low AY notes that exceed the SN76489's 10-bit divider are folded up an
    octave until they fit.

The emitted stream uses PSGlib's native format (latch/data/wait bytes plus
substring compression), which the z88dk SMS runtime plays directly.  The
``SONG_WS_SIZE`` emitted for the game is the size of this compressed stream;
the ROM copy is ZX0-compressed separately by ``tools/gen_port.py``.

``spectrumizer`` is an editor dependency (``tools/requirements.txt``); the
import is lazy so non-SMS builds keep working when it is absent.
"""
from __future__ import annotations

AY_CLOCK = 1773400
SMS_PSG_CLOCK = 3579545
FRAME_HZ = 50
PSG_WS_MAX = 5888

# AY amplitude (0..15) -> SN76489 attenuation (0 = loudest, 15 = silent).
SN_ATT = (15, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 1, 0)


class SmsMusicError(Exception):
    """A PT3 module cannot be converted to an SMS PSG stream."""


def _spectrumizer():
    try:
        from spectrumizer.pt3 import player
        from spectrumizer import audio
    except ImportError as err:  # pragma: no cover - depends on the install
        raise SmsMusicError(
            "SMS music needs the pinned spectrumizer package; install "
            "tools/requirements.txt or use the editor Docker image") from err
    return player, audio


def _env_levels(shape):
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


_ENV_SHAPES = [_env_levels(s) for s in range(16)]


def _sn_period(periods, note, tone_ofs):
    note = max(0, min(95, note))
    ay_period = max(1, periods[note] + tone_ofs)
    n = int(round(SMS_PSG_CLOCK * ay_period / (2.0 * AY_CLOCK)))
    n = max(1, n)
    while n > 1023:                 # SN76489 has a 10-bit tone divider
        n = (n + 1) // 2
    return n


def _sn_noise_rate(ay_r6):
    return min(7, max(0, (ay_r6 or 1) >> 2))


def _volume(amp, env_level=None):
    if env_level is not None:
        amp = env_level
    return SN_ATT[max(0, min(15, amp))]


def _emit_frame(frame, r6, env, periods, prev):
    """Translate one 50 Hz AY frame to SN76489 writes; update ``prev``."""
    writes = bytearray()

    env_period, env_shape, env_retrig = env
    use_env = any(c[4] for c in frame)
    if use_env:
        levels, loop = _ENV_SHAPES[env_shape & 0x0F]
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
    else:
        level = None

    for ci, (note, amp, tone_on, noise_on, chan_env, tone_ofs) in enumerate(frame):
        if note is None or not tone_on:
            target = 15
        else:
            target = _volume(amp, level if chan_env else None)
        if note is not None and tone_on:
            n = _sn_period(periods, note, tone_ofs)
            if prev["tone"][ci] != n:
                writes.append(0x80 | (ci << 5) | (n & 0x0F))
                writes.append(0x40 | ((n >> 4) & 0x3F))
                prev["tone"][ci] = n
        if prev["volume"][ci] != target:
            writes.append(0x90 | (ci << 5) | target)
            prev["volume"][ci] = target

    noise_amp = max((c[1] for c in frame if c[3]), default=None)
    if noise_amp is None:
        if prev["noise_vol"] != 15:
            writes.append(0xF0 | 15)
            prev["noise_vol"] = 15
    else:
        rate = _sn_noise_rate(r6)
        if prev["noise_rate"] != rate:
            writes.append(0xE8 | rate)       # channel 3, white noise
            prev["noise_rate"] = rate
        v = _volume(noise_amp)
        if prev["noise_vol"] != v:
            writes.append(0xF0 | v)
            prev["noise_vol"] = v

    return writes


def _wait_run(n):
    out = bytearray()
    while n:
        chunk = min(8, n)
        out.append(0x38 + chunk - 1)
        n -= chunk
    return out


def _compress(data):
    """PSGlib substring compression, referencing literal bytes only.

    PSGlib has a single return address, so a repeated block must not itself
    contain another repeat opcode.
    """
    n = len(data)
    literal = bytearray(n)
    comp_pos = [-1] * n
    hist = {}
    out = bytearray()
    pos = 0
    while pos < n:
        best_pos = best_len = 0
        if pos + 4 <= n:
            key = bytes(data[pos:pos + 4])
            for p in hist.get(key, ())[-256:]:
                l = 0
                while (l < 51 and pos + l < n and literal[p + l]
                       and data[p + l] == data[pos + l]):
                    l += 1
                if l > best_len:
                    best_pos, best_len = p, l
        if best_len >= 4:
            off = comp_pos[best_pos]
            if off < 0 or off > 0xFFFF:
                raise SmsMusicError("PSG substring offset out of range")
            out.append(0x08 + best_len - 4)
            out += off.to_bytes(2, "little")
            pos += best_len
        else:
            comp_pos[pos] = len(out)
            out.append(data[pos])
            literal[pos] = 1
            if pos + 4 <= n:
                hist.setdefault(bytes(data[pos:pos + 4]), []).append(pos)
            pos += 1
    return bytes(out)


def _verify(comp, plain):
    """Replay a compressed stream the way PSGlib does and compare bytes."""
    out = bytearray()
    ptr = 0
    ret = 0
    remaining = 0
    n = len(comp)
    while ptr < n:
        pos = ptr
        in_sub = remaining != 0
        b = comp[ptr]
        ptr += 1
        if remaining:
            remaining -= 1
            if not remaining:
                ptr = ret
        if b < 0x08:
            out.append(b)
            if b == 0:
                break
        elif b < 0x38:
            if in_sub:
                raise SmsMusicError("nested PSG substring")
            length = b - 4
            if ptr + 2 > n:
                raise SmsMusicError("truncated PSG substring offset")
            off = comp[ptr] | (comp[ptr + 1] << 8)
            ptr += 2
            if off >= pos:
                raise SmsMusicError(
                    f"PSG substring points forward (off={off} pos={pos} "
                    f"len={length})")
            if off + length > n:
                raise SmsMusicError("PSG substring runs past the stream")
            if any(0x08 <= c < 0x38 for c in comp[off:off + length]):
                raise SmsMusicError("nested PSG substring")
            ret, remaining = ptr, length
            ptr = off
        else:
            out.append(b)
    return bytes(out)


def pt3_to_psg(data, *, name=""):
    """Return a PSGlib-compatible SN76489 stream for a PT3 module."""
    player, audio = _spectrumizer()
    try:
        module = player.parse_module(data)
    except ValueError as err:
        raise SmsMusicError(f"{name or 'PT3'}: {err}") from err
    warnings = player.foreign_warnings(module)
    if warnings:
        raise SmsMusicError(
            f"{name or 'PT3'}: unsupported PT3 feature(s): " + "; ".join(warnings))
    periods = audio.build_pt3_table()

    frames = []
    prev = {
        "tone": [None, None, None],
        "volume": [None, None, None],
        "noise_rate": None,
        "noise_vol": None,
        "env_pos": 0,
        "env_acc": 0.0,
    }
    for frame, r6, env in player.iter_frames(module):
        frames.append(_emit_frame(frame, r6, env, periods, prev))

    plain = bytearray()
    empty = 0
    for writes in frames:
        if not writes:
            empty += 1
            continue
        if empty:
            plain += _wait_run(empty)
            empty = 0
        plain += writes
        plain.append(0x38)
    if empty:
        plain += _wait_run(empty)
    plain.append(0x00)

    comp = _compress(plain)
    if _verify(comp, plain) != bytes(plain):
        raise SmsMusicError(f"{name or 'PT3'}: PSG compression self-check failed")
    if len(comp) > PSG_WS_MAX:
        raise SmsMusicError(
            f"{name or 'PT3'}: {len(comp)}B PSG stream exceeds the {PSG_WS_MAX}B "
            "SMS music workspace; shorten the song")
    return comp


def main(argv=None):
    import argparse
    import sys

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pt3")
    ap.add_argument("-o", "--output", help="write the compressed PSG stream")
    args = ap.parse_args(argv)
    try:
        with open(args.pt3, "rb") as f:
            data = f.read()
        psg = pt3_to_psg(data, name=args.pt3)
    except OSError as err:
        print(f"smsmusic: {err}", file=sys.stderr)
        return 2
    except SmsMusicError as err:
        print(f"smsmusic: {err}", file=sys.stderr)
        return 1
    if args.output:
        with open(args.output, "wb") as f:
            f.write(psg)
    print(f"{args.pt3}: {len(psg)}B PSG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
