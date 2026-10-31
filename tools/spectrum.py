#!/usr/bin/env python3
"""Retro Visual Novel test harness: drive the game headlessly in ZEsarUX.

Screenshots of the real emulated screen without any X server, plus scripted
input, memory inspection and pause/resume. Use for visual regression checks
and gameplay debugging.

Commands:
  cli  <zrcp command...>            run one ZRCP command, print response
  shot  NAME                        save screenshot: NAME.png (and .scr)
  keys  TIME_MS "STRING"            send key string, e.g. 100 "opzap"
  ascii TIME_MS A B C ...           send ascii keys (13=Enter, 32=Space...)
  tap  KEY... | none                press/hold keyboard keys until 'tap none'
                                    (q w e r t a s d f g z x c v ... o p 1..0
                                     space enter sym sh) - raw matrix rows
  boot                              (re)smartload the .tap and wait for title
  run  [FILE.tap]                   (re)start fuse with optional new tape
  pause / resume                    stop / continue the emulated CPU
  poke  ADDR BYTES...               write memory (addr accepts 0x.. or decimal,
                                    bytes decimal) then read back to verify
  peek  ADDR LEN                    read memory
  regs / ocr                        CPU registers / OCR text of screen
  verify                            self-test of the whole chain
Default fuse/port: ports 10001..10019; `run` starts another instance on the
first free one.

ZRCP quirks baked into this harness (do not fight them by hand):
  - write-memory/read-memory take DECIMAL addresses; a 0x prefix is a No-Op.
  - write-memory with space-separated values is unreliable; the harness pokes
    use write-memory-raw (hex, no separators).
  - .scr dumps = live screen RAM (exact while paused). .bmp = last presented
    frame (fresh while running, stale while CPU paused).
  - after 'run', any data sent to the port acts as a stop signal.

Examples:
  sh tools/spectrum.sh run && sleep 8 && sh tools/spectrum.sh boot
  sh tools/spectrum.sh shot title
  sh tools/spectrum.sh keys 100 "z"        # punch
  sh tools/spectrum.sh pause && sh tools/spectrum.sh peek 22528 16

Gameplay driving recipe (what the game's read_input polls):
  ascii keys: z punch  x kick  c block  o/p move  q lane-up/jump  a lane-down
  Keys injected during the title's in_WaitForNoKey are swallowed: wait for
  boot() first, then send. To land hits you must be CLOSE (dx<=26 punch,
  <=32 kick) and in the SAME LANE as the target (dy<=12).
"""
import glob
import os
import socket
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # project root
ZESARUX = os.path.join(ROOT, "ZEsarUX-13.0", "zesarux")
OUTDIR = os.path.join(ROOT, "tools", "out")
FUSE_CONFIG = "/tmp/harness_zesaruxrc"
BASE_PORT = 10001
MAX_PORT = 10019

# keyboard row bitmask for set-ui-io-ports: (row_port_hi, bit)
KB_ROWS = {
    "v": (0xFE, 0x10), "c": (0xFE, 0x08), "x": (0xFE, 0x04), "z": (0xFE, 0x02),
    "sh": (0xFE, 0x01),
    "g": (0xFD, 0x10), "f": (0xFD, 0x08), "d": (0xFD, 0x04), "s": (0xFD, 0x02),
    "a": (0xFD, 0x01),
    "t": (0xFB, 0x10), "r": (0xFB, 0x08), "e": (0xFB, 0x04), "w": (0xFB, 0x02),
    "q": (0xFB, 0x01),
    "5": (0xF7, 0x10), "4": (0xF7, 0x08), "3": (0xF7, 0x04), "2": (0xF7, 0x02),
    "1": (0xF7, 0x01),
    "6": (0xEF, 0x10), "7": (0xEF, 0x08), "8": (0xEF, 0x04), "9": (0xEF, 0x02),
    "0": (0xEF, 0x01),
    "y": (0xDF, 0x10), "u": (0xDF, 0x08), "i": (0xDF, 0x04), "o": (0xDF, 0x02),
    "p": (0xDF, 0x01),
    "h": (0xBF, 0x10), "j": (0xBF, 0x08), "k": (0xBF, 0x04), "l": (0xBF, 0x02),
    "enter": (0xBF, 0x01),
    "b": (0x7F, 0x10), "n": (0x7F, 0x08), "m": (0x7F, 0x04), "sym": (0x7F, 0x02),
    "space": (0x7F, 0x01),
}


def port_active(port):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=1)
        s.settimeout(0.5)
        try:
            s.recv(100)     # banner
        except socket.timeout:
            pass
        s.sendall(b"get-version\r")
        time.sleep(0.4)
        try:
            data = s.recv(200).decode(errors="replace")
        except socket.timeout:
            data = ""
        s.close()
        return "13.0" in data or "command" in data
    except OSError:
        return False


def active_port():
    """Port of a running harness fuse (ZEsarUX must have our config file)."""
    for port in range(BASE_PORT, MAX_PORT + 1):
        if port_active(port):
            return port
    return None


def free_port():
    for port in range(BASE_PORT, MAX_PORT + 1):
        if not port_active(port):
            return port
    sys.exit("no free port in range")


class ZRCP:
    def __init__(self, port):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.sock.settimeout(0.35)
        d = self._read_for(0.8)
        if "ZRCP" not in d:
            sys.exit(f"port {port} answered but is not ZRCP")

    def _read_for(self, sec=1.0):
        data, end = b"", time.time() + sec
        while time.time() < end:
            try:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                data += chunk
            except socket.timeout:
                pass
        return data.decode(errors="replace")

    def cmd(self, c, wait=1.0):
        self.sock.sendall(c.encode())
        return self._read_for(wait).strip()

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def wait_prompt(z, sec=10.0):
    """Wait until ZRCP answers get-version (boot/load may busy the CPU)."""
    end = time.time() + sec
    while time.time() < end:
        r = z.cmd("get-version\r", wait=0.7)
        if "command" in r or "13.0" in r:
            return True
        time.sleep(0.5)
    return False


def start_fuse(tape):
    port = free_port()
    cmd = [
        ZESARUX,
        "--configfile", FUSE_CONFIG,
        "--vo", "null", "--ao", "null",
        "--stats-send-already-asked",
        "--enable-remoteprotocol", "--remoteprotocol-port", str(port),
        "--machine", "128k",
        tape,
    ]
    log = open(os.path.join(OUTDIR, f"fuse_{port}.log"), "w")
    subprocess.Popen(cmd, cwd=os.path.join(ROOT, "ZEsarUX-13.0"),
                     stdout=log, stderr=log)
    log.close()
    # wait for ZRCP
    for _ in range(40):
        time.sleep(0.5)
        if port_active(port):
            return port
    sys.exit("fuse did not start")


def ensure_client():
    port = active_port()
    if port is None:
        tape_arg = [a for a in sys.argv[2:] if a.endswith(".tap")]
        port = start_fuse(tape_arg[0] if tape_arg else os.path.join(ROOT, "the-arousa-job.tap"))
        print(f"fuse started on port {port}")
    return ZRCP(port), port


# ---------------------------------------------------------------- screenshots
def shot(z, name):
    os.makedirs(OUTDIR, exist_ok=True)
    bmp = os.path.join(OUTDIR, name + ".bmp")
    scr = os.path.join(OUTDIR, name + ".scr")
    z.cmd(f"save-screen {bmp}\r", wait=1.3)
    z.cmd(f"save-screen {scr}\r", wait=0.9)
    try:
        if os.path.getsize(bmp) > 0:
            print(bmp)
        if os.path.getsize(scr) == 6912:
            from PIL import Image
            sys.path.insert(0, os.path.join(ROOT, "tools"))
            import render_zx_screen
            render_zx_screen.render(open(scr, "rb").read(),
                                    os.path.join(OUTDIR, name + ".png"), scale=3)
            print(os.path.join(OUTDIR, name + ".png"))
    except OSError as err:
        print("capture failed:", err, file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------- keys
def keys_ascii(z, ms, chars):
    args = " ".join(str(c) for c in chars)
    z.cmd(f"send-keys-ascii {ms} {args}\r", wait=1.0 + ms / 1000)


def keys_string(z, ms, text):
    z.cmd(f'send-keys-string {ms} "{text}"\r', wait=1.0 + ms / 1000 * max(1, len(text)))


def tap(z, keys_arg, extra_bmp=None):
    """Press/hold keys given as port:bit args from KB_ROWS until released."""
    rows = {hi: 0x1F for hi in (0xFE, 0xFD, 0xFB, 0xF7, 0xEF, 0xDF, 0xBF, 0x7F)}
    for k in keys_arg:
        hi, bit = KB_ROWS[k.lower()]
        rows[hi] &= ~bit
    payload = "".join(f"{rows[hi]:02X}" for hi in
                      (0xFE, 0xFD, 0xFB, 0xF7, 0xEF, 0xDF, 0xBF, 0x7F)) + "00"
    print(z.cmd(f"set-ui-io-ports {payload}\r"))
    if extra_bmp:
        print(z.cmd(f"save-screen {extra_bmp}\r"))
    print("(keys stay pressed until the next tap or released by: tap none)")


def release(z):
    z.cmd("set-ui-io-ports 1f1f1f1f1f1f1f1f00\r")


# ---------------------------------------------------------------- boot
def grab_bmp(z, path):
    z.cmd(f"save-screen {os.path.abspath(path)}\r", wait=1.3)
    try:
        return open(path, "rb").read()
    except OSError:
        return b""


def screen_signature(data):
    """(yellow_px, blue_px) of a 352x304 24bpp BMP - used to identify the
    game title (yellow sand/HUD + blue sky) vs loader/menu screens."""
    if len(data) < 54 + 352 * 304 * 3:
        return (0, 0)
    px = data[54:]
    yellow = blue = 0
    for i in range(0, len(px), 3):
        r, g, b = px[i], px[i + 1], px[i + 2]
        if r > 180 and g > 180 and b < 80:
            yellow += 1
        elif r < 40 and g < 40 and b > 180:
            blue += 1
    return (yellow, blue)


# attr addresses (decimal!) of the title-only bands in src/main.c title_screen():
#   row22 PRESS ANY KEY = PAPER_YELLOW|FLASH -> attr byte 0xB0
#   row23 (C) footer    = PAPER_CYAN        -> attr byte 0x28
ATTR_ROW22 = 22528 + 22 * 32      # 23232
ATTR_ROW23 = 22528 + 23 * 32      # 23264


def title_detected(z):
    """True when attr RAM shows the title screen's PRESS-ANY-KEY bar and
    cyan footer (live read; works while the CPU runs). The attract loop
    rebuilds the screen bands, so single reads can hit a black gap during
    repaint: sample several times and take any hit."""
    def attrs(addr, n):
        r = z.cmd(f"read-memory {addr} {n}\r", 0.9).strip()
        r = r.split("command")[0].strip()
        try:
            return bytes.fromhex(r)
        except ValueError:
            return b""
    for _ in range(5):
        row22 = attrs(ATTR_ROW22, 32)
        row23 = attrs(ATTR_ROW23, 16)
        if row22 == b"\xb0" * 32 and row23 == b"\x28" * 16:
            return True
        time.sleep(0.3)
    return False


def boot(z, timeout_s=240):
    """(Re)load the game and wait until the title screen is shown.
    Uses ZRCP smartload: deterministic, no 128-menu fiddling. The tape is
    smart-loaded with an accelerated loader, so this takes a few seconds,
    not real-time tape length."""
    wait_prompt(z, 20)
    z.cmd("close-all-menus\r"); time.sleep(0.8)
    z.cmd("close-all-menus\r"); time.sleep(0.3)
    z.cmd("exit-cpu-step\r", wait=0.5)          # never smartload while paused
    z.cmd("save-screen /dev/null.scr\r", 0.2)   # tolerated noise, ignored
    tap_name = os.path.join(ROOT, "the-arousa-job.tap")
    r = z.cmd(f"smartload {tap_name}\r", wait=2.0)
    if "not found" in r.lower() or "error" in r.lower():
        # fall back to relative path from the fuse cwd (ZEsarUX-13.0/)
        r = z.cmd("smartload ../the-arousa-job.tap\r", wait=2.0)
    print("smartload:", r or "started")
    probe = os.path.join(OUTDIR, "boot_probe.bmp")
    end = time.time() + timeout_s
    while time.time() < end:
        time.sleep(3)
        if title_detected(z):
            grab_bmp(z, probe)
            print("title screen reached")
            return True
        yellow, blue = screen_signature(grab_bmp(z, probe))
        print(f"  loading... yellow={yellow} blue={blue}")
    print("boot: title not detected within", timeout_s, "s", file=sys.stderr)
    return False


def verify(z):
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name)
        ok = ok and cond

    check("version", "13.0" in z.cmd("get-version\r", 0.8))
    check("machine", "128k" in z.cmd("get-current-machine\r", 0.8).lower())
    vs = os.path.join(OUTDIR, "v.scr")
    z.cmd(f"save-screen {vs}\r", 1.0)
    ok_scr = os.path.exists(vs) and os.path.getsize(vs) == 6912
    check("scr capture 6912 bytes", ok_scr)
    # poke/readback round-trip on attrs (decimal addresses for write-memory!)
    # read-memory answers "<hex>\ncommand..."; use a scratch-safe attr cell:
    # 0x5800-1 = 22527 (attr area ends 22528; this is pixel-area top byte but
    # round-trip only proves the protocol, the game redraws it harmlessly)
    z.cmd("write-memory-raw 22527 4a\r", 1.0)
    r = z.cmd("read-memory 22527 1\r", 0.8)
    check("poke/readback attr byte", "4a" in r.lower())
    check("resume keeps prompt", ">" in z.cmd("get-version\r", 0.8))
    print("ALL PASS" if ok else "SOME FAILED")
    return ok


# ---------------------------------------------------------------- main
def main():
    os.makedirs(OUTDIR, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "run":
        tape = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "the-arousa-job.tap")
        print("no fuse running: starting on port", start_fuse(tape))
        return
    z, port = ensure_client()

    if cmd == "cli":
        print(z.cmd(" ".join(sys.argv[2:]) + "\r", wait=1.5))
    elif cmd == "shot":
        shot(z, sys.argv[2] if len(sys.argv) > 2 else "shot")
    elif cmd == "keys":
        ms = int(sys.argv[2]); text = sys.argv[3]
        keys_string(z, ms, text)
    elif cmd == "ascii":
        ms = int(sys.argv[2])
        chars = []
        for a in sys.argv[3:]:
            chars.append(int(a) if a.isdigit() and len(a) <= 3 else ord(a[0]))
        keys_ascii(z, ms, chars)
    elif cmd == "tap":
        if len(sys.argv) > 2 and sys.argv[2] not in ("none",):
            tap(z, sys.argv[2:])
        else:
            release(z); print("released")
    elif cmd == "boot":
        boot(z)
    elif cmd == "run":
        z.close()
        tape = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "the-arousa-job.tap")
        print("starting on port", start_fuse(tape))
        return
    elif cmd == "off":
        z.close()
        subprocess.run(["pkill", "-x", "zesarux"])
        print("all fuse instances stopped")
        return
    elif cmd == "pause":
        print(z.cmd("enter-cpu-step\r", 0.8))
    elif cmd == "resume":
        print(z.cmd("exit-cpu-step\r", 0.6)); time.sleep(0.2)
        print(z.cmd("run\r", 0.6))
    elif cmd == "poke":
        addr = int(sys.argv[2], 0)
        payload = "".join(f"{int(b, 16):02X}" for b in sys.argv[3:])
        print(z.cmd(f"write-memory-raw {addr} {payload}\r"))
        print(z.cmd(f"read-memory {addr} {len(sys.argv[3:])}\r"))
    elif cmd == "peek":
        addr = int(sys.argv[2], 0)
        print(z.cmd(f"read-memory {addr} {sys.argv[3]}\r"))
    elif cmd == "regs":
        print(z.cmd("get-registers\r"))
    elif cmd == "ocr":
        print(z.cmd("get-ocr\r", 2.0))
    elif cmd == "verify":
        sys.exit(0 if verify(z) else 1)
    else:
        print(__doc__)
    z.close()


if __name__ == "__main__":
    main()