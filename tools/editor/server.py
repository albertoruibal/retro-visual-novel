#!/usr/bin/env python3
"""Multi-game HTML story editor for a banked-scene adventure.

A stdlib-only HTTP server (no Flask) that serves a single-page editor and a
small JSON API. A game is a folder with a ``game.md``, generated art
(``assets/gen``) and a ``build/`` tree of generated sources/bank images. In the desktop
(folder) model one or more game folders anywhere on disk are open — each added
with ``POST /api/open`` (removed with ``POST /api/close``) or seeded by the
``RVN_GAMES``/``RVN_GAME`` environment variables at startup — while with
nothing opened the editor falls back to the ``games/<slug>/`` workspace. New
games can be created with ``POST /api/new``. The editor
reads/writes the selected game's ``game.md`` through the shared
``tools/scenefile.py`` parser, generates art via the local
stable-diffusion.cpp (Qwen-Image) server, and can run that game's build.

Environment:
    STABLE_DIFFUSION_URL
                 base URL of the SD (image) server; if unset, image
                 generation is disabled and hidden in the UI
    Z88DK        z88dk toolchain root for the build  (default: a detected
                 Snap install at /snap/z88dk/current, else "/tmp/z88dk");
                 its bin/ is put on PATH and ZCCCFG=$Z88DK/lib/config
    CC65         cc65 toolchain root for the Commodore 64 / NES builds
                 (default: a detected cl65 on PATH); its bin/ is put on PATH
    RVN_SETTINGS   JSON file for editor-wide settings (server endpoints,
                 chosen in the top-bar Settings modal); wins over the variables above
                 (the old ZXAD_SETTINGS is still read as a fallback)
    EDITOR_PORT  HTTP port to listen on              (default 8765)
    EDITOR_HOST  bind address                        (default 127.0.0.1)

The model-server endpoints and the z88dk/cc65 toolchain paths can be set in the
UI (top-bar Settings) instead of the environment; a change takes effect
immediately and is persisted to the settings file. Pointing the editor at local
toolchains lets a packaged desktop app build without bundled compilers.

Run:
    python3 tools/editor/server.py
    # then open http://127.0.0.1:8765

Endpoints (``?game=<slug>`` selects the game; defaults to the first):
    GET    /api/games                 list games + selected slug
    POST   /api/games                 {"name","title"} -> create
    POST   /api/games/duplicate       {"game","name","title"} -> duplicate
    POST   /api/games/rename          {"game","name"} -> rename folder
    DELETE /api/games/<slug>          delete a game folder
    POST   /api/open                  {"path"} -> add an open game folder ("" clears)
    POST   /api/close                 {"game"} -> close one open game folder
    POST   /api/new                   {"parent","name","title"} -> new folder + open
    GET    /api/project               parse <game>/game.md -> project JSON
                                      (includes a `revision` content hash)
    GET    /api/targets               build-target registry + per-game options
    PUT    /api/project               write <game>/game.md (atomic, .bak kept);
                                      a stale `revision` -> 409 unless `force`
    GET    /api/raw                   read <game>/game.md verbatim
                                      -> {"text","revision"}
    PUT    /api/raw                   {"text","revision"} -> validate/write;
                                      a stale revision -> 409 unless `force`
    POST   /api/validate              {"text"} -> lint game.md without writing,
                                      plus {"outline"} scene/art/song/item/flag
                                      links for Source-tab Ctrl+click
    GET    /api/health                config + whether the image server is up
    GET    /api/settings              editable editor settings (image-server URL
                                      + z88dk_path)
    POST   /api/settings              {"stable_diffusion_url","z88dk_path",
                                      "cc65_path"} -> validate/persist + apply
                                      (blank URL disables; blank z88dk resets
                                      to $Z88DK, then a detected Snap install;
                                      blank cc65 resets to $CC65/detection)
    POST   /api/generate              {"game","art","overrides"} -> job id
    POST   /api/generate_ref          {"game","ref","overrides"} -> job id
    POST   /api/refine_art            {"game","art"} -> 2x img2img job id
    POST   /api/refine_ref            {"game","ref"} -> 2x img2img job id
    POST   /api/generate_all          {"game","missing"} -> job id
                                      (every art, or only arts with no image)
    GET    /api/job/<id>              generation status / result
    DELETE /api/job/<id>              stop a running generation job
    GET    /api/jobs                  list jobs
    GET    /api/image/<slug>/<art>    art source PNG (assets/art/<id>/<image>, ?file= a candidate)
    GET    /api/artimages/<slug>/<art> candidates in assets/art/<id>/ (name/mtime/size/active)
    DELETE /api/artimages/<slug>/<art>?file=<name>  delete one art candidate
    GET    /api/refimages/<slug>/<ref> candidates in assets/refs/<id>/ (name/mtime/size/active)
    DELETE /api/refimages/<slug>/<ref>?file=<name>  delete one reference candidate
    GET    /api/refimage/<slug>/<ref>  reference source PNG (?file= a candidate)
    GET    /api/preview/<slug>/<art>  Spectrum-quantisised band preview PNG
           ?target=zx48|sms|cpc|cpc464|msx1|msx2|gb  preview through that target's converter
    GET    /api/preview/<slug>/<art>/classic  same, standard 8x8 attributes
    GET    /api/preview/<slug>/<art>/bifrost  same, Bifrost* 8x1 attributes
           ?file= &crop= &lines= &dither= &match= &palette= &palette_colors= &saturation= ...
           pick a candidate / override the art's saved band height and conversion settings
           (dither is the preview target's live ## <id> value)
    POST   /api/upload_art            {"art","data"} -> new asset in assets/art/<id>/
    POST   /api/upload_ref            {"ref","data"} -> new asset in assets/refs/<id>/
    POST   /api/upload_song           {"song","data"} -> store a .pt3 module
    POST   /api/convert_song          {"song","data","opts"} -> MIDI -> .pt3
    POST   /api/reconvert_song        {"song","opts"} -> stored .mid -> .pt3
    GET    /api/song/<slug>/<id>      stream a game's assets/music/<id>.pt3
    GET    /api/songsource/<slug>/<id>  stored source .mid metadata (bytes/seconds)
    GET    /api/songpreview/<slug>/<id>  stream the .pt3 as a rendered WAV
    POST   /api/build                 {"game","targets"?} -> build selected systems
    GET    /api/build/<id>            build status + log tail
    GET    /api/tap/<slug>/<name>     game's built <name>.tap / .sna (ZX emulator)
    GET    /api/artifact/<slug>/<name> any built target artifact (.sms/.rom/.dsk/.gbc/.tap/.sna/.nex/.prg/.nes)
    GET    /play/<slug>/              exported web player (Emulator tab iframe)
    GET    /play/<slug>/<file>        static player, novel, emulator and file assets
    POST   /api/web_export            export the player plus the novel (when selected)
    GET    /api/webzip/<slug>         download the itch.io-ready player zip
    GET    /emulator/<file>           vendored web emulators (static/emulator/)
    GET    /monaco/<file>             vendored Monaco editor (static/monaco/)
    GET    /                         the editor SPA
    GET    /static/<file>            topic-split SPA JS/CSS (core.js, base.css, ...)
"""
import base64
import bisect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cc65path
import gamestore
import scenefile
import targets
import z88dkpath
import zxart
import webgame

ROOT = gamestore.ROOT
STATIC = os.path.join(ROOT, "tools", "editor", "static")
EMULATOR = os.path.join(STATIC, "emulator")
MONACO = os.path.join(STATIC, "monaco")
# The editor talks to an image server on the host. The URL is presence-gated:
# an unset/empty variable disables generation and the UI hides it. The endpoint
# can also be chosen at runtime in the top-bar Settings modal; that choice is
# persisted to a small JSON file and wins over the environment variable (a
# blank stored value disables the feature, even if the variable set one).
_ENV_SD_URL = os.environ.get("STABLE_DIFFUSION_URL", "").strip().rstrip("/")
_ENV_Z88DK = os.environ.get("Z88DK", "").strip()
_ENV_CC65 = (os.environ.get("CC65") or os.environ.get("RVN_CC65") or "").strip()

STABLE_DIFFUSION_URL = ""
IMAGE_ENABLED = False
Z88DK_PATH = _ENV_Z88DK
CC65_PATH = _ENV_CC65


def z88dk_valid(path):
    """True if ``path`` looks like a z88dk tree (has its compiler/assembler).

    Used only as a UI hint: a bad path is still saved, so a game can be
    configured before the toolchain is installed.
    """
    if not path:
        return False
    if os.name == "nt":
        names = ("zcc.exe", "z88dk-z80asm.exe")
    else:
        names = ("zcc", "z88dk-z80asm")
    return any(os.path.exists(os.path.join(path, "bin", n)) for n in names)


def z88dk_effective_path():
    """The toolchain the build will use when no explicit path is set.

    A saved ``z88dk_path``/``$Z88DK`` wins; otherwise a Snap install is
    detected automatically, then the historical ``/tmp/z88dk`` fallback.
    """
    return Z88DK_PATH or z88dkpath.detected() or "/tmp/z88dk"


Z88DK_TOOLS = ("zcc", "z88dk-z80asm", "z88dk-appmake", "z88dk-zx0")


def z88dk_missing_tools(path=None):
    """The build tools not found in ``path``'s ``bin/``."""
    path = z88dk_effective_path() if path is None else str(path or "").strip()
    if not path:
        return list(Z88DK_TOOLS)
    bindir = os.path.join(path, "bin")
    return [name for name in Z88DK_TOOLS
            if shutil.which(name, path=bindir) is None]


def z88dk_ready(path=None):
    """True if the toolchain has every host tool the builds invoke."""
    return not z88dk_missing_tools(path)


def cc65_valid(path):
    """True if ``path`` looks like a cc65 install (has cl65/ca65)."""
    return cc65path.looks_like(path)


def cc65_effective_path():
    """The cc65 root used for the Commodore 64 / NES builds."""
    return CC65_PATH or cc65path.detected()


def cc65_missing_tools(path=None):
    """The cc65 host tools not found for the configured root."""
    path = cc65_effective_path() if path is None else str(path or "").strip()
    return cc65path.missing_tools(path)


def cc65_ready(path=None):
    return bool(cc65_effective_path() if path is None else path) and \
        not cc65_missing_tools(path)


def _default_settings_path():
    """Where to persist editor-wide settings when RVN_SETTINGS is unset.

    A settings file from the previous brand (``zx-novel``, or the older
    ``zxadventure``) is migrated to the retro-visual-novel location once, so an
    existing install keeps its saved z88dk / model-server choices.
    """
    if sys.platform == "darwin":
        cfg = os.path.join(os.path.expanduser("~"), "Library",
                           "Application Support")
    elif os.name == "nt":
        cfg = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        cfg = os.environ.get("XDG_CONFIG_HOME") or \
            os.path.join(os.path.expanduser("~"), ".config")
    new = os.path.join(cfg, "retro-visual-novel", "settings.json")
    for old in (os.path.join(cfg, "zx-novel", "settings.json"),
                os.path.join(cfg, "zxadventure", "settings.json")):
        if os.path.exists(new):
            break
        if not os.path.exists(old):
            continue
        try:
            os.makedirs(os.path.dirname(new), exist_ok=True)
            shutil.copy2(old, new)
        except OSError:
            return old
    return new


# Electron passes its userData settings.json here so the UI choice and the
# remembered last game share one file.
SETTINGS_PATH = (os.environ.get("RVN_SETTINGS")
                 or os.environ.get("ZXAD_SETTINGS")
                 or _default_settings_path())


def _read_settings_file():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:                          # noqa: BLE001 - missing/garbled
        return {}


def _save_settings_file(patch):
    data = _read_settings_file()               # keep unrelated keys (lastGame)
    data.update(patch)
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, SETTINGS_PATH)
    except Exception:                          # noqa: BLE001 - best effort
        return
    _settings.update(patch)


_SETTING_MODULES = ("editor_games", "editor_images", "editor_music",
                   "editor_build")
_SETTING_NAMES = ("STABLE_DIFFUSION_URL", "IMAGE_ENABLED", "Z88DK_PATH",
                  "CC65_PATH")


def _sync_setting_modules():
    """Copy changed live settings into the feature modules' globals."""
    for name in _SETTING_MODULES:
        mod = sys.modules.get(name)
        if mod is None:
            continue
        for key in _SETTING_NAMES:
            setattr(mod, key, globals()[key])


def settings_payload():
    return {"stable_diffusion_url": STABLE_DIFFUSION_URL,
            "image_enabled": IMAGE_ENABLED,
            "z88dk_path": Z88DK_PATH, "z88dk_valid": z88dk_valid(Z88DK_PATH),
            "z88dk_default": _ENV_Z88DK or z88dkpath.detected() or "/tmp/z88dk",
            "z88dk_effective": z88dk_effective_path(),
            "z88dk_available": z88dk_ready(),
            "z88dk_missing": z88dk_missing_tools(),
            "cc65_path": CC65_PATH, "cc65_valid": cc65_valid(CC65_PATH),
            "cc65_default": _ENV_CC65 or cc65path.detected(),
            "cc65_effective": cc65_effective_path(),
            "cc65_available": cc65_ready(),
            "cc65_missing": cc65_missing_tools(),
            "settings_path": SETTINGS_PATH}


def apply_settings(settings):
    """Adopt stored settings, falling back to the environment defaults.

    A key that is present (even blank) overrides its variable, so clearing the
    field in the UI can disable a feature the environment had enabled. The
    z88dk path is different: a blank value falls back to ``$Z88DK`` (the
    toolchain location is a path, not a feature switch).
    """
    global STABLE_DIFFUSION_URL, IMAGE_ENABLED, Z88DK_PATH, CC65_PATH
    sd = settings.get("stable_diffusion_url")
    tool = settings.get("z88dk_path")
    cc65 = settings.get("cc65_path")
    STABLE_DIFFUSION_URL = (str(sd).strip().rstrip("/")
                            if sd is not None else _ENV_SD_URL)
    Z88DK_PATH = str(tool).strip() if tool is not None and str(tool).strip() \
        else _ENV_Z88DK
    CC65_PATH = str(cc65).strip() if cc65 is not None and str(cc65).strip() \
        else _ENV_CC65
    if CC65_PATH:
        os.environ["CC65"] = CC65_PATH
    else:
        os.environ.pop("CC65", None)
    IMAGE_ENABLED = bool(STABLE_DIFFUSION_URL)
    _sync_setting_modules()
    return settings_payload()


def save_settings(body):
    """Validate + persist a settings patch from the UI, then apply it."""
    patch = {}
    if "stable_diffusion_url" in body:
        url = str(body.get("stable_diffusion_url") or "").strip().rstrip("/")
        if url and not re.match(r"^https?://", url):
            raise ValueError("stable_diffusion_url must be an http(s) URL")
        patch["stable_diffusion_url"] = url
    if "z88dk_path" in body:
        # A path, not a feature toggle: any string is accepted and the payload's
        # ``z88dk_valid`` tells the UI whether it is a usable toolchain.
        patch["z88dk_path"] = str(body.get("z88dk_path") or "").strip()
    if "cc65_path" in body:
        patch["cc65_path"] = str(body.get("cc65_path") or "").strip()
    if patch:
        _save_settings_file(patch)
        apply_settings(_read_settings_file())
    return settings_payload()


_settings = _read_settings_file()
apply_settings(_settings)
HOST = os.environ.get("EDITOR_HOST", "127.0.0.1")
PORT = int(os.environ.get("EDITOR_PORT", "8765"))

_lock = threading.Lock()
_jobs = {}
_builds = {}
_interrupts = set()   # job ids asked to stop; jobs poll this and give up

# The +zx classic console is 64 columns wide. Body text and item descriptions
# word-wrap at 62 columns (leaving the last cells for the scroll markers); the
# editor counts those wrapped rows against the band. Option labels and titles
# stay single-line with the same 62-column cap.
TEXT_COLS = 62
OPT_COLS = 62
# An item display name is printed into the inventory band, which indents past
# the '<' marker column and stops short of the '>' marker at the right edge, so
# a name must fit the single band line of 58 columns (see tools/gen_scenes.py).
ITEM_NAME_COLS = 58


def health():
    version = ""
    reachable = False
    if IMAGE_ENABLED:
        try:
            with urllib.request.urlopen(f"{STABLE_DIFFUSION_URL}/sdapi/v1/options", timeout=2) as r:
                json.load(r)
            reachable = True
        except urllib.error.HTTPError:
            reachable = True                   # server is up, just 404s
        except Exception:                      # noqa: BLE001
            reachable = False
        try:
            with urllib.request.urlopen(f"{STABLE_DIFFUSION_URL}/sdapi/v1/sd-models", timeout=2) as r:
                models = json.load(r)
                if models:
                    version = models[0].get("model_name", "")
        except Exception:                      # noqa: BLE001
            pass
    return {"stable_diffusion_url": STABLE_DIFFUSION_URL, "reachable": reachable, "model": version,
            "image_enabled": IMAGE_ENABLED, "port": PORT,
            "z88dk_path": Z88DK_PATH, "z88dk_valid": z88dk_valid(Z88DK_PATH),
            "z88dk_available": z88dk_ready(),
            "z88dk_missing": z88dk_missing_tools(),
            "cc65_path": CC65_PATH, "cc65_valid": cc65_valid(CC65_PATH),
            "cc65_available": cc65_ready(),
            "cc65_missing": cc65_missing_tools()}


# -------------------------------------------------------------------- server
# Shared constants used by the feature modules.
PT3_MAGIC = (b"Vortex Tracker", b"ProTracker 3.")
ART_FIELD_NEEDS = ("refs", "image", "crop") + tuple(scenefile.CONV_KEYS)
SONG_WS = 4158
SONG_MAX_BYTES = 4 * 1024 * 1024
SONG_MIDI_MAX_BYTES = 4 * 1024 * 1024
SONG_TOKENS = ("on", "off")
SONG_RENDER_TIMEOUT = 300
CONVERT_TIMEOUT = 120
CONVERT_STYLES = ("faithful", "chiptune")
CONVERT_BASSES = ("normal", "envelope", "envelope-tone")
CONVERT_FLAGS = ("auto_transpose", "vibrato")
MAX_UPLOAD_BYTES = 16 * 1024 * 1024
REF_MAX_SIDE = 1024
MIDI_DEFAULT_TEMPO_US = 500000      # MIDI default: 120 bpm

# The functional modules import the shared constants/state above with
# ``from server import *`` and export their own API back here. When this file
# runs as a script, ``server`` is not yet a module name; alias it so the
# feature modules share this instance instead of loading a second copy.
sys.modules.setdefault("server", sys.modules[__name__])
__all__ = [name for name in globals() if not name.startswith("__")]
from editor_validation import *  # noqa: E402,F401,F403
from editor_games import *  # noqa: E402,F401,F403
from editor_images import *  # noqa: E402,F401,F403
from editor_music import *  # noqa: E402,F401,F403
from editor_build import *  # noqa: E402,F401,F403
from editor_web import *  # noqa: E402,F401,F403
from editor_static import *  # noqa: E402,F401,F403


class Handler(BaseHTTPRequestHandler):
    server_version = "StoryEditor/2.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[editor] " + fmt % args + "\n")

    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length", "0"))
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode())

    def _game_arg(self, body=None):
        # The active game is always selected via ?game=; request bodies may
        # legitimately contain other "game" keys (e.g. the project's # Game
        # settings) so they are never consulted here.
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return q.get("game", [None])[0]

    def do_GET(self):
        path = urllib.parse.unquote(self.path.split("?", 1)[0])
        try:
            if path in ("/", "/index.html"):
                return self._send(200, open(os.path.join(STATIC, "index.html"),
                                            "rb").read(), "text/html")
            if path.startswith("/static/"):
                name = os.path.basename(path)
                full = os.path.join(STATIC, name)
                ctype = ("text/javascript" if name.endswith(".js")
                         else "text/css" if name.endswith(".css")
                         else "image/svg+xml" if name.endswith(".svg")
                         else "image/png" if name.endswith(".png")
                         else "application/octet-stream")
                return self._send(200, open(full, "rb").read(), ctype)
            m = re.match(r"^/play/([^/\\]+)/$", path)
            if m:
                data, mt = web_exported_file(m.group(1), "index.html")
                return self._send(200, data, mt)
            m = re.match(r"^/play/([^/\\]+)$", path)
            if m:
                return self._send(301, b"", "text/plain",
                                  {"Location": "/play/"
                                   + urllib.parse.quote(m.group(1)) + "/"})
            m = re.match(r"^/play/([^/\\]+)/(.+)$", path)
            if m:
                data, mt = web_exported_file(m.group(1), m.group(2))
                return self._send(200, data, mt)
            m = re.match(r"^/api/webzip/([^/\\]+)$", path)
            if m:
                data = web_zip(m.group(1))
                fname = webgame.zip_filename(m.group(1))
                return self._send(200, data, "application/zip", {
                    "Content-Disposition": f'attachment; filename="{fname}"'})
            if path == "/api/games":
                games = gamestore.list_games()
                selected = gamestore.resolve(self._game_arg())
                return self._send(200, {"games": games,
                                        "folder": bool(gamestore.opened()),
                                        "selected": selected["slug"] if selected else None})
            if path == "/api/project":
                return self._send(200, project_json(self._game_arg()))
            if path == "/api/targets":
                doc = None
                slug = self._game_arg()
                if slug:
                    try:
                        game = _game_or_error(slug)
                        doc = scenefile.parse(os.path.join(game["dir"], "game.md"))
                    except Exception:               # noqa: BLE001 - no game yet
                        doc = None
                return self._send(200, targets.targets_json(doc))
            if path == "/api/raw":
                md = _game_md_path(self._game_arg())
                if not os.path.exists(md):
                    return self._send(404, {"error": "game.md does not exist yet"})
                return self._send(200, {"text": open(md, encoding="utf-8").read(),
                                        "revision": _game_md_revision(md)})
            if path == "/api/health":
                return self._send(200, health())
            if path == "/api/settings":
                return self._send(200, settings_payload())
            if path == "/api/jobs":
                return self._send(200, list(_jobs.values()))
            if path.startswith("/api/job/"):
                jid = path[len("/api/job/"):]
                return self._send(200 if jid in _jobs else 404,
                                  _jobs.get(jid, {"error": "no such job"}))
            if path.startswith("/api/build/"):
                bid = path[len("/api/build/"):]
                return self._send(200 if bid in _builds else 404,
                                  _builds.get(bid, {"error": "no such build"}))
            m = re.match(r"^/api/artimages/([^/\\]+)/([^/\\]+)$", path)
            if m:
                game = _game_or_error(m.group(1))
                art_id = m.group(2)
                doc = scenefile.parse(os.path.join(game["dir"], "game.md"))
                art = _find_art(doc, art_id)
                active = scenefile.art_image_name(art or {}) \
                    or (os.path.basename(_art_image_path(game, art))
                        if art else None)
                files = []
                for p in scenefile.list_art_images(_art_root(game["dir"]),
                                                   art_id):
                    name = os.path.basename(p)
                    files.append({"file": name,
                                  "mtime": int(os.path.getmtime(p)),
                                  "size": os.path.getsize(p),
                                  "active": name == active})
                return self._send(200, {"game": m.group(1), "art": art_id,
                                        "image": active, "files": files})
            m = re.match(r"^/api/refimages/([^/\\]+)/([^/\\]+)$", path)
            if m:
                game = _game_or_error(m.group(1))
                ref_id = m.group(2)
                if not scenefile.valid_ref_id(ref_id):
                    return self._send(404, {"error": "no reference"})
                doc = scenefile.parse(os.path.join(game["dir"], "game.md"))
                ref = _find_ref(doc, ref_id)
                active = scenefile.ref_image_name(ref or {}) \
                    or (os.path.basename(_ref_image_path(game, ref))
                        if ref else None)
                files = []
                for p in scenefile.list_ref_images(_ref_root(game["dir"]),
                                                   ref_id):
                    name = os.path.basename(p)
                    files.append({"file": name,
                                  "mtime": int(os.path.getmtime(p)),
                                  "size": os.path.getsize(p),
                                  "active": name == active})
                return self._send(200, {"game": m.group(1), "ref": ref_id,
                                        "image": active, "files": files})
            m = re.match(r"^/api/refimage/([^/\\]+)/([^/\\]+)$", path)
            if m:
                game = _game_or_error(m.group(1))
                if not scenefile.valid_ref_id(m.group(2)):
                    return self._send(404, {"error": "no reference"})
                qs = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query)
                want = qs.get("file", [None])[0] or None
                doc = scenefile.parse(os.path.join(game["dir"], "game.md"))
                ref = _find_ref(doc, m.group(2))
                if want is not None and scenefile.valid_art_image(want):
                    full = os.path.join(_ref_root(game["dir"]), m.group(2),
                                        want)
                else:
                    full = _ref_image_path(game, ref) if ref else None
                if not full or not os.path.exists(full):
                    return self._send(404, {"error": "no image"})
                return self._send(200, open(full, "rb").read(), "image/png")
            m = re.match(r"^/api/image/([^/\\]+)/([^/\\]+)$", path)
            if m:
                game = _game_or_error(m.group(1))
                qs = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query)
                want = qs.get("file", [None])[0] or None
                doc = scenefile.parse(os.path.join(game["dir"], "game.md"))
                art = _find_art(doc, m.group(2))
                if want is not None and scenefile.valid_art_image(want):
                    full = os.path.join(_art_root(game["dir"]), m.group(2),
                                        want)
                else:
                    full = _art_image_path(game, art) if art else None
                if not full or not os.path.exists(full):
                    return self._send(404, {"error": "no image"})
                return self._send(200, open(full, "rb").read(), "image/png")
            m = re.match(r"^/api/song/([^/\\]+)/([^/\\]+)$", path)
            if m:
                full = song_path(m.group(1), m.group(2))
                if not os.path.exists(full):
                    return self._send(404, {"error": "no module"})
                return self._send(200, open(full, "rb").read(),
                                  "application/octet-stream")
            m = re.match(r"^/api/songsource/([^/\\]+)/([^/\\]+)$", path)
            if m:
                return self._send(200, song_source_info(m.group(1), m.group(2)))
            m = re.match(r"^/api/songpreview/([^/\\]+)/([^/\\]+)$", path)
            if m:
                return self._send(200, song_wav_bytes(m.group(1), m.group(2)),
                                  "audio/wav")
            m = re.match(r"^/api/preview/([^/\\]+)/([^/\\]+)(?:/(bifrost|classic))?$",
                         path)
            if m:
                qs = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query)
                target_id = (qs.get("target", [""])[0] or "").strip().lower()
                target = targets.get_target(target_id)
                canonical_id = target.id if target else target_id
                if target is not None and target.preview is not None:
                    data = target_art_preview_bytes(
                        m.group(1), m.group(2), target_id,
                        crop=qs.get("crop", [None])[0],
                        file=qs.get("file", [None])[0],
                        lines=qs.get("lines", [None])[0],
                        overrides=_preview_overrides(qs),
                        target_rows=qs.get("rows", [None])[0])
                else:
                    data = art_preview_bytes(m.group(1), m.group(2),
                                             mode=m.group(3) or "nirvana",
                                             crop=qs.get("crop", [None])[0],
                                             file=qs.get("file", [None])[0],
                                             lines=qs.get("lines", [None])[0],
                                             overrides=_preview_overrides(qs))
                if data is None:
                    return self._send(404, {"error": "no image"})
                return self._send(200, data, "image/png")
            if path == "/api/build":
                return self._send(200, list(_builds.values()))
            m = re.match(r"^/api/tap/([^/\\]+)/([^/\\]+)$", path)
            if m:
                data, mt = tap_file(m.group(1), m.group(2))
                return self._send(200, data, mt)
            m = re.match(r"^/api/artifact/([^/\\]+)/([^/\\]+)$", path)
            if m:
                data, mt = artifact_file(m.group(1), m.group(2))
                return self._send(200, data, mt)
            m = re.match(r"^/emulator/([A-Za-z0-9_./-]+)$", path)
            if m:
                data, mt = emulator_file(m.group(1))
                return self._send(200, data, mt)
            m = re.match(r"^/monaco/([A-Za-z0-9_./-]+)$", path)
            if m:
                data, mt = monaco_file(m.group(1))
                return self._send(200, data, mt)
            return self._send(404, {"error": "not found"})
        except KeyError as e:
            return self._send(404, {"error": str(e)})
        except FileNotFoundError as e:
            return self._send(404, {"error": str(e)})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:      # noqa: BLE001
            return self._send(500, {"error": str(e)})

    def do_PUT(self):
        try:
            body = self._read_json()
            slug = self._game_arg(body)
            path = urllib.parse.unquote(self.path.split("?", 1)[0])
            if path == "/api/raw":
                text = body.get("text")
                if not isinstance(text, str) or not text.strip():
                    return self._send(400, {"error": "missing or empty text"})
                try:
                    _write_game_md(slug, text, None if body.get("force")
                                   else body.get("revision"))
                except _ValidationFailed as e:
                    return self._send(400, {"error": str(e), "issues": e.issues})
                except _SaveConflict as e:
                    return self._send(409, {"error": str(e), "conflict": True,
                                            "revision": e.revision})
                return self._send(200, project_json(slug))
            scenefile.serialize(body)           # validate before writing
            g = body.get("game") or {}
            scenefile.assign_flags(body.get("scenes") or [],
                                   g.get("start", []),
                                   g.get("flags", []),
                                   scenefile.declared_items(
                                       g, body.get("item_meta")),
                                   item_meta=body.get("item_meta"))  # clash
            save_project(body, slug, None if body.get("force")
                         else body.get("revision"))
            return self._send(200, project_json(slug))
        except KeyError as e:
            return self._send(404, {"error": str(e)})
        except _SaveConflict as e:
            return self._send(409, {"error": str(e), "conflict": True,
                                    "revision": e.revision})
        except Exception as e:      # noqa: BLE001
            return self._send(400, {"error": str(e)})

    def do_POST(self):
        path = urllib.parse.unquote(self.path.split("?", 1)[0])
        try:
            body = self._read_json()
            if path == "/api/games":
                g = gamestore.create(body.get("name"), body.get("title"))
                return self._send(201, {"game": g})
            if path == "/api/games/duplicate":
                g = gamestore.duplicate(body.get("game"), body.get("name"),
                                        body.get("title"))
                return self._send(201, {"game": g})
            if path == "/api/games/rename":
                g = gamestore.rename(body.get("game"), body.get("name"))
                return self._send(200, {"game": g})
            if path == "/api/open":
                # Folder-open model: add a game folder anywhere on disk to the
                # open set (it does not replace the games already open). An
                # empty/missing path clears them and uses the workspace.
                try:
                    g = gamestore.open_folder(body.get("path"))
                except FileNotFoundError as e:
                    return self._send(400, {"error": str(e)})
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                return self._send(200, {"game": g,
                                        "games": gamestore.list_games()})
            if path == "/api/close":
                # Remove one open game folder (by slug or path); its files are
                # untouched, it just leaves the tab list.
                try:
                    g = gamestore.close_folder(body.get("game") or body.get("path"))
                except FileNotFoundError as e:
                    return self._send(400, {"error": str(e)})
                return self._send(200, {"closed": g["slug"],
                                        "games": gamestore.list_games()})
            if path == "/api/new":
                g = gamestore.create_at(body.get("parent"), body.get("name"),
                                        body.get("title"))
                gamestore.open_folder(g["dir"])
                return self._send(201, {"game": g})
            if path == "/api/generate":
                art = body.get("art") or body.get("id")
                jid = start_generate(self._game_arg(body), art,
                                     body.get("overrides"))
                return self._send(202, {"job": jid})
            if path == "/api/generate_ref":
                ref = body.get("ref") or body.get("id")
                jid = start_generate_ref(self._game_arg(body), ref,
                                         body.get("overrides"))
                return self._send(202, {"job": jid})
            if path == "/api/refine_art":
                art = body.get("art") or body.get("id")
                jid = start_refine_art(self._game_arg(body), art,
                                      body.get("overrides"))
                return self._send(202, {"job": jid})
            if path == "/api/refine_ref":
                ref = body.get("ref") or body.get("id")
                jid = start_refine_ref(self._game_arg(body), ref,
                                      body.get("overrides"))
                return self._send(202, {"job": jid})
            if path == "/api/generate_all":
                jid = start_generate_all(self._game_arg(body),
                                         bool(body.get("missing")))
                return self._send(202, {"job": jid})
            if path == "/api/upload_art":
                art = body.get("art") or body.get("id")
                r = upload_art(self._game_arg(body), art, body.get("data", ""))
                return self._send(200, r)
            if path == "/api/upload_ref":
                ref = body.get("ref") or body.get("id")
                r = upload_ref(self._game_arg(body), ref, body.get("data", ""),
                               body.get("kind") or "up")
                return self._send(200, r)
            if path == "/api/upload_song":
                song = body.get("song") or body.get("id")
                r = upload_song(self._game_arg(body), song,
                                body.get("data", ""))
                return self._send(200, r)
            if path == "/api/convert_song":
                song = body.get("song") or body.get("id")
                r = convert_song(self._game_arg(body), song,
                                 body.get("name"), body.get("data", ""),
                                 body.get("opts"))
                return self._send(200, r)
            if path == "/api/reconvert_song":
                song = body.get("song") or body.get("id")
                r = reconvert_song(self._game_arg(body), song,
                                   body.get("name"), body.get("opts"))
                return self._send(200, r)
            if path == "/api/build":
                req = body.get("targets") if isinstance(body, dict) else None
                bid = start_build(self._game_arg(body), req)
                return self._send(202, {"build": bid})
            if path == "/api/web_export":
                return self._send(200, web_export(self._game_arg(body)))
            if path == "/api/validate":
                text = body.get("text")
                if not isinstance(text, str):
                    return self._send(400, {"error": "missing text"})
                return self._send(200, {
                    "issues": lint_game_md(self._game_arg(body), text),
                    "outline": scenefile.outline_links(text)})
            if path == "/api/settings":
                return self._send(200, save_settings(body))
            return self._send(404, {"error": "not found"})
        except KeyError as e:
            return self._send(404, {"error": str(e)})
        except (ValueError, FileExistsError, FileNotFoundError) as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:      # noqa: BLE001
            return self._send(400, {"error": str(e)})

    def do_DELETE(self):
        path = urllib.parse.unquote(self.path.split("?", 1)[0])
        try:
            m = re.match(r"^/api/job/([^/]+)$", path)
            if m:
                return self._send(200, cancel_generate(m.group(1)))
            m = re.match(r"^/api/artimages/([^/\\]+)/([^/\\]+)$", path)
            if m:
                qs = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query)
                filename = qs.get("file", [None])[0] or ""
                return self._send(200, delete_art_image(
                    m.group(1), m.group(2), filename))
            m = re.match(r"^/api/refimages/([^/\\]+)/([^/\\]+)$", path)
            if m:
                qs = urllib.parse.parse_qs(
                    urllib.parse.urlparse(self.path).query)
                filename = qs.get("file", [None])[0] or ""
                return self._send(200, delete_ref_image(
                    m.group(1), m.group(2), filename))
            m = re.match(r"^/api/games/([A-Za-z0-9_-]+)$", path)
            if m:
                gamestore.delete(m.group(1))
                return self._send(200, {"deleted": m.group(1)})
            return self._send(404, {"error": "not found"})
        except KeyError as e:
            return self._send(404, {"error": str(e)})
        except FileNotFoundError as e:
            return self._send(404, {"error": str(e)})
        except Exception as e:      # noqa: BLE001
            return self._send(400, {"error": str(e)})


def main():
    opened = gamestore.opened()
    print("Story editor")
    if opened:
        print(f"  games   : {len(opened)} open")
        for path in opened:
            print(f"            {path}")
    else:
        games = gamestore.list_games()
        print(f"  games   : {len(games)} under {gamestore.GAMES_DIR}")
    print(f"  sd      : {STABLE_DIFFUSION_URL or '(disabled)'}")
    eff = z88dk_effective_path()
    ok = " (ok)" if z88dk_ready() else " (not found)"
    print(f"  z88dk   : {eff}{ok}")
    eff = cc65_effective_path() or "(not set)"
    ok = " (ok)" if cc65_ready() else " (not found)"
    print(f"  cc65    : {eff}{ok}")
    print(f"  open    : http://{HOST}:{PORT}")
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
