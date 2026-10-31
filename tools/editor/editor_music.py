"""Music modules, MIDI slicing and spectrumizer conversion."""

from __future__ import annotations

from server import *  # noqa: F401,F403 - shared state and helpers

from editor_games import *
from editor_validation import *

def music_dir(slug):
    return os.path.join(_game_or_error(slug)["dir"], "assets", "music")



def song_path(slug, song_id):
    return os.path.join(music_dir(slug), f"{song_id}.pt3")



def _validate_song_module(data):
    """Check a .pt3 payload is a plausible, buffer-sized PT3 module.

    The VT2 player reads the module header, so a wrong file is silent at best;
    the size ceiling is the hard constraint (it is copied into resident RAM).
    """
    if len(data) > SONG_WS:
        raise ValueError(f"song is {len(data)} bytes; the player buffer holds "
                         f"at most {SONG_WS} (shorten the module)")
    if not data.startswith(PT3_MAGIC):
        raise ValueError("not a PT3 module (missing a Vortex Tracker / "
                         "ProTracker header)")


# ------------------------------------------------------------- MIDI slicing
# spectrumizer has no trim option, so an over-long MIDI is cut here (pure
# stdlib) to a start/end window before it is handed to the converter. Only the
# note/controller timeline is rewritten; the original upload is kept verbatim
# as assets/music/<id>.mid so a cut stays non-destructive.
MIDI_DEFAULT_TEMPO_US = 500000      # MIDI default: 120 bpm



def _midi_vlq_read(buf, i):
    """Read a MIDI variable-length quantity at ``i`` -> (value, next index)."""
    val = 0
    while True:
        if i >= len(buf):
            raise ValueError("truncated MIDI variable-length quantity")
        b = buf[i]
        i += 1
        val = (val << 7) | (b & 0x7F)
        if not b & 0x80:
            return val, i



def _midi_vlq_write(n):
    """Encode a non-negative int as a MIDI variable-length quantity."""
    n = max(0, int(n))
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)



def _midi_track_events(body):
    """Decode one MTrk chunk body into [(abs_tick, status, payload), ...].

    Channel messages keep their status byte and parameter bytes; meta events
    become status 0xFF with payload ``type-byte + data``; SysEx becomes status
    0xF0/0xF7 with the raw payload. Running status is expanded on decode.
    """
    events = []
    i = 0
    tick = 0
    running = None
    while i < len(body):
        delta, i = _midi_vlq_read(body, i)
        tick += delta
        if i >= len(body):
            break
        b = body[i]
        if b & 0x80:
            status = b
            i += 1
        elif running is not None:
            status = running
        else:
            raise ValueError("MIDI running status with no prior status")
        if status == 0xFF:
            if i >= len(body):
                raise ValueError("truncated MIDI meta event")
            mtype = body[i]
            i += 1
            mlen, i = _midi_vlq_read(body, i)
            payload = body[i:i + mlen]
            i += mlen
            if len(payload) != mlen:
                raise ValueError("truncated MIDI meta event")
            events.append((tick, 0xFF, bytes([mtype]) + payload))
            if mtype == 0x2F:               # end of track
                break
        elif status in (0xF0, 0xF7):
            mlen, i = _midi_vlq_read(body, i)
            payload = body[i:i + mlen]
            i += mlen
            if len(payload) != mlen:
                raise ValueError("truncated MIDI SysEx event")
            events.append((tick, status, payload))
            running = None
        elif 0x80 <= status <= 0xEF:
            running = status
            n = 1 if 0xC0 <= status <= 0xDF else 2
            params = body[i:i + n]
            i += n
            if len(params) != n:
                raise ValueError("truncated MIDI channel event")
            events.append((tick, status, bytes(params)))
        else:
            raise ValueError(f"unsupported MIDI status 0x{status:02x}")
    return events



def _midi_parse(data):
    """Parse a standard MIDI file -> (format, division, [track events]).

    SMPTE-timed files (negative division) and format 2 (independent tracks)
    are rejected: their timelines cannot be cut by a shared tick window.
    """
    if len(data) < 14 or data[0:4] != b"MThd":
        raise ValueError("not a MIDI file (missing the MThd header)")
    hlen = int.from_bytes(data[4:8], "big")
    fmt = int.from_bytes(data[8:10], "big")
    ntrk = int.from_bytes(data[10:12], "big")
    division = int.from_bytes(data[12:14], "big")
    if division & 0x8000:
        raise ValueError("SMPTE-timed MIDI is not supported")
    if fmt not in (0, 1):
        raise ValueError(f"unsupported MIDI format {fmt}")
    if not division:
        raise ValueError("MIDI header has no ticks-per-beat")
    pos = 8 + hlen
    tracks = []
    for _ in range(ntrk):
        if pos + 8 > len(data) or data[pos:pos + 4] != b"MTrk":
            raise ValueError("truncated MIDI track chunk")
        tlen = int.from_bytes(data[pos + 4:pos + 8], "big")
        body = data[pos + 8:pos + 8 + tlen]
        if len(body) != tlen:
            raise ValueError("truncated MIDI track chunk")
        pos += 8 + tlen
        tracks.append(_midi_track_events(body))
    return fmt, division, tracks



def _midi_tempo_map(tracks, division):
    """Build tick<->seconds converters and the tempo active at a tick.

    Returns (seconds_at, tick_at, us_at). Tempo changes are piecewise-constant,
    so both directions are exact; ticks are plain when the file has no tempo
    events (the 120 bpm default).
    """
    changes = []
    for evs in tracks:
        for tick, status, payload in evs:
            if status == 0xFF and payload[:1] == b"\x51" and len(payload) >= 4:
                changes.append((tick, int.from_bytes(payload[1:4], "big")))
    changes.sort()
    segs = []
    if not changes or changes[0][0] > 0:
        segs.append((0, MIDI_DEFAULT_TEMPO_US))
    for tick, us in changes:
        if segs and segs[-1][0] == tick:
            segs[-1] = (tick, us)
        elif segs and segs[-1][1] == us:
            continue
        else:
            segs.append((tick, us))
    starts = [t for t, _ in segs]
    secs = [0.0]
    for i in range(1, len(segs)):
        dt = starts[i] - starts[i - 1]
        secs.append(secs[-1] + dt / division * (segs[i - 1][1] / 1_000_000))

    def _seg(tick):
        return max(0, bisect.bisect_right(starts, tick) - 1)

    def seconds_at(tick):
        i = _seg(tick)
        return secs[i] + (tick - starts[i]) / division * (segs[i][1] / 1_000_000)

    def tick_at(seconds):
        if seconds <= 0:
            return 0
        i = max(0, bisect.bisect_right(secs, seconds) - 1)
        return int(starts[i] + (seconds - secs[i]) * 1_000_000 / segs[i][1]
                   * division)

    def us_at(tick):
        return segs[_seg(tick)][1]

    return seconds_at, tick_at, us_at



def _midi_encode(fmt, division, tracks):
    """Serialise [(abs_tick, status, payload), ...] tracks into MIDI bytes.

    Every track gets a fresh end-of-track meta; channel/sysex/meta events keep
    their explicit status byte (running status is not re-used).
    """
    out = bytearray(b"MThd")
    out += (6).to_bytes(4, "big")
    out += int(fmt).to_bytes(2, "big")
    out += len(tracks).to_bytes(2, "big")
    out += int(division).to_bytes(2, "big")
    for evs in tracks:
        body = bytearray()
        prev = 0
        for tick, status, payload in evs:
            body += _midi_vlq_write(tick - prev)
            prev = tick
            if status == 0xFF:
                # payload is type-byte + data; MIDI wants FF <type> <len> <data>.
                body += bytes([0xFF, payload[0]])
                body += _midi_vlq_write(len(payload) - 1) + payload[1:]
            elif status in (0xF0, 0xF7):
                body += bytes([status]) + _midi_vlq_write(len(payload)) + payload
            else:
                body += bytes([status]) + payload
        body += b"\x00\xFF\x2F\x00"        # delta 0, end of track
        out += b"MTrk" + len(body).to_bytes(4, "big") + body
    return bytes(out)



def midi_seconds(data):
    """Duration of a MIDI blob in seconds (for the source-length readout)."""
    _fmt, division, tracks = _midi_parse(data)
    seconds_at, _, _ = _midi_tempo_map(tracks, division)
    end = max((evs[-1][0] if evs else 0) for evs in tracks) if tracks else 0
    return seconds_at(end)



def slice_midi(data, start=0.0, end=0.0):
    """Cut a MIDI to the [start, end) second window and return new bytes.

    ``end`` of 0 means "to the end". Notes already sounding at ``start`` are
    re-triggered at tick 0 and notes still held at ``end`` are released there,
    so no note hangs across a cut. The tempo/time-signature active at ``start``
    is re-emitted at tick 0 (tempo changes inside the window are kept).
    """
    fmt, division, tracks = _midi_parse(data)
    seconds_at, tick_at, us_at = _midi_tempo_map(tracks, division)
    total = max((evs[-1][0] if evs else 0) for evs in tracks) if tracks else 0
    start = max(0.0, float(start or 0.0))
    end = float(end or 0.0)
    if end and end <= start:
        raise ValueError("cut end must come after the cut start")
    if start > 0 and start >= seconds_at(total):
        raise ValueError("cut start is past the end of the source")
    start_tick = tick_at(start) if start > 0 else 0
    end_tick = tick_at(end) if end > 0 else None
    if end_tick is not None and end_tick >= total:
        end_tick = None                    # the end cut is a no-op
    if end_tick is not None and end_tick <= start_tick:
        raise ValueError("the cut leaves an empty range")

    def is_on(status, payload):
        return 0x80 <= status <= 0x9F and payload[1] > 0

    def is_off(status, payload):
        return (0x80 <= status <= 0x8F
                or (0x90 <= status <= 0x9F and payload[1] == 0))

    def timesig_at(tick):
        sig = None
        for evs in tracks:
            for t, status, payload in evs:
                if t <= tick and status == 0xFF and payload[:1] == b"\x58":
                    if sig is None or t >= sig[0]:
                        sig = (t, payload)
        return sig[1] if sig else None

    result = []
    for evs in tracks:
        start_active = {}                  # (channel, note) -> velocity
        for tick, status, payload in evs:
            if tick >= start_tick:
                break
            if is_off(status, payload):
                start_active.pop((status & 0x0F, payload[0]), None)
            elif is_on(status, payload):
                start_active[(status & 0x0F, payload[0])] = payload[1]
        kept = []
        active = {}
        for tick, status, payload in evs:
            if status == 0xFF and payload[:1] == b"\x2F":
                continue
            if tick < start_tick:
                continue
            if end_tick is not None and tick >= end_tick:
                continue
            new_tick = tick - start_tick
            kept.append((new_tick, status, payload))
            if is_on(status, payload):
                active[(status & 0x0F, payload[0])] = payload[1]
            elif is_off(status, payload):
                active.pop((status & 0x0F, payload[0]), None)
        for (chan, note), vel in start_active.items():
            kept.insert(0, (0, 0x90 | chan, bytes([note, vel])))
        last = max((t for t, _, _ in kept), default=0)
        for (chan, note) in list(active):
            kept.append((last, 0x80 | chan, bytes([note, 0])))
        kept.sort(key=lambda e: e[0])
        result.append(kept)

    if start_tick > 0:
        head = [(0, 0xFF, b"\x51" + us_at(start_tick).to_bytes(3, "big"))]
        sig = timesig_at(start_tick)
        if sig:
            head.append((0, 0xFF, sig))
        if result:
            result[0] = head + result[0]

    if not any(0x80 <= s <= 0x9F for evs in result for _, s, _ in evs):
        raise ValueError("the cut leaves no notes; widen the range")
    return _midi_encode(fmt, division, result)



def upload_song(slug, song_id, data):
    """Store a user-supplied .pt3 module for a declared song.

    ``data`` is base64 (or a ``data:`` URL). The song must already be declared
    in ``# Game songs:`` so game.md and the file tree cannot drift apart.
    """
    game = _game_or_error(slug)
    doc = project_json(slug)
    if song_id not in doc["game"].get("songs", []):
        raise KeyError(f"unknown song '{song_id}' (declare it in songs: first)")
    if not _valid_song_id(song_id):
        raise ValueError(f"invalid song id {song_id!r}")
    raw = data.split(",", 1)[-1] if data.startswith("data:") else data
    try:
        blob = base64.b64decode(raw, validate=True)
    except Exception:
        raise ValueError("upload is not valid base64 data")
    if not blob:
        raise ValueError("empty upload")
    if len(blob) > SONG_MAX_BYTES:
        raise ValueError("module too large (max 4 MB)")
    _validate_song_module(blob)
    mdir = music_dir(slug)
    os.makedirs(mdir, exist_ok=True)
    out = os.path.join(mdir, f"{song_id}.pt3")
    with _lock:
        open(out, "wb").write(blob)
    return {"song": song_id, "bytes": len(blob)}



def _opt_int(opts, key, lo, hi, default=0):
    """Coerce ``opts[key]`` to an int clamped to [lo, hi], else ``default``."""
    try:
        return max(lo, min(hi, int(opts.get(key, default))))
    except (TypeError, ValueError):
        return default



def _convert_opts(opts):
    """Allowlist an editor conversion-options dict into spectrumizer flags.

    Unknown keys are ignored and values coerced to their declared domain so a
    malformed request cannot smuggle arbitrary arguments onto the CLI. Options
    left at spectrumizer's own default are omitted, so the flag set only grows
    when the editor deviates.
    """
    opts = opts if isinstance(opts, dict) else {}
    argv = []
    style = str(opts.get("style", "")).strip().lower()
    if style in CONVERT_STYLES:
        argv += ["--style", style]
    bass = str(opts.get("bass", "")).strip().lower()
    if bass in CONVERT_BASSES:
        argv += ["--bass", bass]
    transpose = _opt_int(opts, "transpose", -24, 24)
    if transpose:
        argv += ["--transpose", str(transpose)]
    rows = _opt_int(opts, "rows_per_beat", 1, 16, 4)
    if rows != 4:
        argv += ["--rows-per-beat", str(rows)]
    speed = _opt_int(opts, "speed", 0, 255)
    if speed:
        argv += ["--speed", str(speed)]
    author = str(opts.get("author") or "").strip()[:32]
    if author:
        argv += ["--author", author]
    loop = _opt_int(opts, "loop_pos", 0, 255)
    if loop:
        argv += ["--loop-pos", str(loop)]
    for flag in CONVERT_FLAGS:
        if opts.get(flag):
            argv.append("--" + flag.replace("_", "-"))
    if opts.get("no_dynamics"):
        argv.append("--no-dynamics")
    voice = str(opts.get("channel_c") or "").strip().lower()
    if voice == "arps":                # --arps / --echo are mutually exclusive
        argv.append("--arps")
        arp = _opt_int(opts, "arp_speed", 1, 8, 1)
        if arp != 1:
            argv += ["--arp-speed", str(arp)]
    elif voice == "echo":
        argv.append("--echo")
    return argv



def _trim_range(opts):
    """Parse the editor's optional cut window from ``opts`` -> (start, end).

    Blank/absent means 0 (the start/end of the source). Bad values are ignored
    like the other conversion options.
    """
    opts = opts if isinstance(opts, dict) else {}

    def _secs(key):
        try:
            return max(0.0, float(opts.get(key, 0) or 0))
        except (TypeError, ValueError):
            return 0.0

    return _secs("trim_start"), _secs("trim_end")



def _run_spectrumizer(midi, opts, name):
    """Run the spectrumizer CLI on ``midi`` bytes -> a validated .pt3 blob."""
    with tempfile.TemporaryDirectory(prefix="rvn-") as tmp:
        mid_path = os.path.join(tmp, "in.mid")
        pt3_path = os.path.join(tmp, "out.pt3")
        with open(mid_path, "wb") as f:
            f.write(midi)
        argv = [sys.executable, "-m", "spectrumizer", mid_path, "-o", pt3_path]
        if name:
            argv += ["--name", str(name)[:32]]
        argv += _convert_opts(opts)
        try:
            proc = subprocess.run(argv, cwd=ROOT, capture_output=True,
                                  text=True, timeout=CONVERT_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise ValueError(f"conversion timed out after {CONVERT_TIMEOUT}s")
        if proc.returncode != 0 or not os.path.exists(pt3_path):
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()
            detail = tail[-1] if tail else "no output"
            raise ValueError(f"spectrumizer could not convert this MIDI: {detail}")
        return open(pt3_path, "rb").read()



def _convert_midi(midi, opts, name):
    """Cut (if asked) and convert MIDI bytes -> (pt3 blob, cut info or None)."""
    start, end = _trim_range(opts)
    source = slice_midi(midi, start, end) if (start or end) else midi
    blob = _run_spectrumizer(source, opts, name)
    try:
        _validate_song_module(blob)
    except ValueError as e:
        raise ValueError(f"{e}. Try chiptune style, --auto-transpose, or a "
                         "shorter source — e.g. a smaller cut range "
                         "(nothing was written).")
    cut = {"start": start, "end": end} if (start or end) else None
    return blob, cut



def convert_song(slug, song_id, name, data, opts=None):
    """Convert an uploaded MIDI to a .pt3 for a declared song.

    Runs the ``spectrumizer`` CLI (Docker image) on the MIDI in ``data`` and
    stores the module as ``assets/music/<id>.pt3``. ``opts`` may carry a
    ``trim_start``/``trim_end`` (seconds) cut window; the cut is applied in
    memory only, and the original upload is kept verbatim as
    ``assets/music/<id>.mid`` so the cut stays non-destructive (re-runnable via
    ``reconvert_song``). The module must pass the same PT3/buffer checks as a
    direct upload.
    """
    _game_or_error(slug)
    doc = project_json(slug)
    if song_id not in doc["game"].get("songs", []):
        raise KeyError(f"unknown song '{song_id}' (declare it in songs: first)")
    if not _valid_song_id(song_id):
        raise ValueError(f"invalid song id {song_id!r}")
    raw = data.split(",", 1)[-1] if data.startswith("data:") else data
    try:
        midi = base64.b64decode(raw, validate=True)
    except Exception:
        raise ValueError("upload is not valid base64 data")
    if not midi:
        raise ValueError("empty upload")
    if len(midi) > SONG_MIDI_MAX_BYTES:
        raise ValueError("MIDI too large (max 4 MB)")
    if b"MThd" not in midi[:16]:
        raise ValueError("upload does not look like a MIDI file")
    mdir = music_dir(slug)
    os.makedirs(mdir, exist_ok=True)
    blob, cut = _convert_and_store(slug, song_id, midi, opts, name)
    return {"song": song_id, "bytes": len(blob), "mid_bytes": len(midi),
            "cut": cut}



def _convert_and_store(slug, song_id, midi, opts, name):
    """Convert MIDI bytes and write ``<id>.pt3`` + ``<id>.mid`` -> (blob, cut).

    Used by an uploaded MIDI (``convert_song``) and a re-conversion; both take
    the identical spectrumizer + validation path and leave the same re-runnable
    ``.mid`` source behind.
    """
    mdir = music_dir(slug)
    os.makedirs(mdir, exist_ok=True)
    blob, cut = _convert_midi(midi, opts, name)
    with _lock:
        open(os.path.join(mdir, f"{song_id}.pt3"), "wb").write(blob)
        open(os.path.join(mdir, f"{song_id}.mid"), "wb").write(midi)
    return blob, cut



def reconvert_song(slug, song_id, name, opts=None):
    """Rebuild a song's .pt3 from its stored ``assets/music/<id>.mid``.

    Lets the Music tab re-run the converter with a different cut window or
    style without re-uploading the MIDI. The raw source is never rewritten.
    """
    _game_or_error(slug)
    doc = project_json(slug)
    if song_id not in doc["game"].get("songs", []):
        raise KeyError(f"unknown song '{song_id}' (declare it in songs: first)")
    if not _valid_song_id(song_id):
        raise ValueError(f"invalid song id {song_id!r}")
    mid = os.path.join(music_dir(slug), f"{song_id}.mid")
    if not os.path.exists(mid):
        raise FileNotFoundError(f"song '{song_id}' has no stored .mid source; "
                                "upload a MIDI with Convert first")
    midi = open(mid, "rb").read()
    blob, cut = _convert_midi(midi, opts, name)
    with _lock:
        open(os.path.join(music_dir(slug), f"{song_id}.pt3"), "wb").write(blob)
    return {"song": song_id, "bytes": len(blob), "mid_bytes": len(midi),
            "source": True, "cut": cut}



def song_source_info(slug, song_id):
    """Metadata for a song's stored ``.mid`` source (byte size + duration)."""
    if not _valid_song_id(song_id):
        raise ValueError(f"invalid song id {song_id!r}")
    path = os.path.join(music_dir(slug), f"{song_id}.mid")
    if not os.path.exists(path):
        return {"song": song_id, "exists": False}
    data = open(path, "rb").read()
    try:
        secs = midi_seconds(data)
    except ValueError:
        secs = None
    return {"song": song_id, "exists": True, "bytes": len(data),
            "seconds": secs}


def song_wav_bytes(slug, song_id):
    """Render a song's .pt3 to a WAV with spectrumizer's software AY.

    Cached under ``assets/gen/song_<id>.wav`` and re-rendered only when the
    module changes (mtime/size), so repeat previews are instant. Rendered at
    22050 Hz mono to keep the file small; the audition is faithful for
    spectrumizer-made modules and approximate for foreign ones (its decoder
    warns about tokens/tone tables outside the subset it emits).
    """
    if not _valid_song_id(song_id):
        raise ValueError(f"invalid song id {song_id!r}")
    game = _game_or_error(slug)
    pt3 = song_path(slug, song_id)
    if not os.path.exists(pt3):
        raise FileNotFoundError(f"song '{song_id}' has no .pt3 module yet")
    gen = os.path.join(game["dir"], "assets", "gen")
    os.makedirs(gen, exist_ok=True)
    out = os.path.join(gen, f"song_{song_id}.wav")
    src_mt = os.path.getmtime(pt3)
    if (os.path.exists(out) and os.path.getmtime(out) >= src_mt
            and os.path.getsize(out) > 44):
        return open(out, "rb").read()
    argv = [sys.executable, "-m", "spectrumizer.play", pt3, "-o", out,
            "--no-play", "-q", "--rate", "22050", "--stereo", "mono"]
    try:
        proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                              timeout=SONG_RENDER_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ValueError(f"song render timed out after {SONG_RENDER_TIMEOUT}s")
    if proc.returncode != 0 or not os.path.exists(out):
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = tail[-1] if tail else "no output"
        raise ValueError(f"could not render this module: {detail}")
    return open(out, "rb").read()



__all__ = [
    'music_dir',
    'song_path',
    '_validate_song_module',
    '_midi_vlq_read',
    '_midi_vlq_write',
    '_midi_track_events',
    '_midi_parse',
    '_midi_tempo_map',
    '_midi_encode',
    'midi_seconds',
    'slice_midi',
    'upload_song',
    '_opt_int',
    '_convert_opts',
    '_trim_range',
    '_run_spectrumizer',
    '_convert_midi',
    'convert_song',
    '_convert_and_store',
    'reconvert_song',
    'song_source_info',
    'song_wav_bytes',
]
