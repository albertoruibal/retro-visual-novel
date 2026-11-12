#!/usr/bin/env python3
"""Read and write a game's game.md (game / art / ref / scene sections).

Shared by tools/gen_scenes.py (build) and tools/editor/server.py (UI) so the
two never disagree about the format. Keeping this dependency-free matters: the
editor imports it inside a stdlib-only server.
"""
import os
import re

PARAM_KEYS = ("seed", "steps", "cfg", "size", "width", "height")
# Default diffusion steps for the game-wide `# Game` generation settings.
STEPS_DEFAULT = 35
# Per-art `crop:` is a rectangle of the source, `x y w h` as percentages of
# the source dimensions (0..100); absent means the centred band-aspect window.
# Unlike PARAM_KEYS it is art-only and always persisted by the editor, so it is
# deliberately kept out of PARAM_KEYS (see server.py _drop_art_overrides).
# Mirrors zxart.crop_rect.
DEFAULT_CROP = None
# Recommended output size for the image model: 2x the 256x80 band (3.2:1 would
# be 512x160, but the taller 2:1 source keeps more detail for the per-art crop).
DEFAULT_WIDTH, DEFAULT_HEIGHT = 512, 256
# Art-band height in character rows (8px lines): 8..16 even, default 10 (the
# 256x80 band). A NIRVANA+ tile is 16px = 2 character rows, so the value must be
# even. It drives the engine's TOTAL_ROWS (= art_lines), the band workspace
# sizes and the text-band budget (rendered rows art_lines+1..22).
ART_LINES_DEFAULT = 10
ART_LINES_MIN = 8
ART_LINES_MAX = 16
# The ZX target used to be `zx` and used to store its band height as
# `art_lines`; keep reading both old spellings and rewrite them canonically.
_SYSTEM_OPTION_ALIASES = {
    ("zx", "art_lines"): ("art_lines", ART_LINES_DEFAULT),
    ("zx128", "art_lines"): ("art_lines", ART_LINES_DEFAULT),
}
# The 48K band height is a normal per-system option; its old `art_lines`
# spelling (shared with zx128) is read as `art_rows` but stays in its block.
_SYSTEM_KEY_ALIASES = {
    ("zx48", "art_lines"): "art_rows",
}
# A per-system `margin:` insets the converted picture inside the art band by N
# 8x8 cells on each side (0 = full band). The border uses the system's text_bg.
# A `prompt:` value is written as a first line plus continuation lines. A
# 2-space-indented continuation is a layout wrap and rejoins with a space; any
# other continuation (the 4-space indent a save emits, or a legacy unindented
# line) keeps its line break (see _prompt_lines/parse).
PROMPT_WRAP = 120
_PROMPT_INDENT = "  "
_PROMPT_BREAK_INDENT = _PROMPT_INDENT * 2
_OPT_RE = re.compile(r"(.+?)\s*->\s*(\S+)(.*)$")
# An option may end with `msg <text>`; the message is plain text and consumes
# the rest of the line, so it is split off before conditions/effects are read.
_OPT_MSG_RE = re.compile(r"(?:^|\s)msg\s+(.*)$", re.IGNORECASE | re.DOTALL)
# Tokens whose argument may itself be named `msg`; such a word is not the
# start of the trailing message clause.
_OPT_EFFECT_WORDS = {"if", "unless", "inscene", "set", "unset", "pick",
                     "leave"}
# A scene text or item description line carries its conditions after ` -> `:
#   The van is here. -> if seen_van unless has_diesel
# Unconditional lines have no arrow. The old prefix form
#   if <flag>: text   /   unless <flag>: text
# is still read (and normalised to the arrow form) so unmigrated games load.
_TEXT_COND_TAIL_RE = re.compile(
    r"^(.*)\s*->\s*((?:(?:if|unless)\s+\S+\s*)+)$")
_LEGACY_TEXT_COND_RE = re.compile(r"^((?:(?:if|unless)\s+\S+\s*)+):\s*")
# A song id is a bare token; `on`/`off` are reserved (legacy music tokens).
_SONG_ONOFF = ("on", "off")
# Option condition tokens: `if <flag-or-item>` and `unless <flag-or-item>`.
# An option may carry several of each; every condition must hold. Each is
# emitted as a (flag id, negated) pair in a per-option table.
_COND_RE = re.compile(r"\b(if|unless)\s+(\S+)")
# Per-option condition cap (see tools/gen_scenes.py and the editor validator).
MAX_CONDITIONS = 8
# Reserved build-time pseudo-flags. Each is true only in the build for its
# target; generators fold an `if`/`unless` on one into "always" or "never" and
# never assign it a runtime flag id. They are valid only in conditions.
SYSTEM_FLAGS = {
    "system_zx": ("zx128", "zx48"),
    "system_zx128": "zx128",
    "system_zx48": "zx48",
    "system_sms": "sms",
    "system_cpc": ("cpc", "cpc464"),
    "system_cpc464": "cpc464",
    "system_msx1": "msx1",
    "system_msx2": "msx2",
    "system_msx": ("msx1", "msx2"),
    "system_gb": "gb",
    "system_next": "next",
    "system_c64": "c64",
    "system_nes": "nes",
    "system_oric": "oric",
    "system_web": "web",
}
# Accepted values for a system's `dither:` option, mirroring zxart.DITHER_MODES.
DITHER_MODES = ("off", "bayer2", "bayer4", "bayer8", "noise", "floyd",
                "atkinson", "jarvis", "stucki", "sierra")
_DITHER_MODES = DITHER_MODES
# Targets without a per-pixel ordered/error-diffusion choice only distinguish
# a hard snap from Floyd-Steinberg (see their target options).
DEFAULT_DITHER = "off"
# Colour-distance metric for the NIRVANA+ cell search, mirroring zxart.
MATCH_MODES = ("rgb", "perceptual")
DEFAULT_MATCH = "rgb"
# Optional source-palette pre-reduction, mirroring zxart.PALETTE_MODES.
PALETTE_MODES = ("none", "spectrum", "adaptive")
DEFAULT_PALETTE = "none"
DEFAULT_PALETTE_COLORS = 16
# Optional high-resolution second pass for generation: a base 512x256 render is
# enlarged to 2x (or more) and re-sampled with the same prompt. The output PNG
# is the high-res image; the build still scales it to the art band.
HIRES_SCALES = (1.0, 2.0, 3.0, 4.0)
HIRES_STEPS_DEFAULT = 20
HIRES_DENOISE_DEFAULT = 0.4
REFINE_DENOISE_DEFAULT = 0.45
# Source colour adjustments applied before quantisation (1.0 = unchanged).
# These are `# Game` defaults that any `# Art` may override, like `crop:`; they
# are deliberately NOT in PARAM_KEYS, so the editor keeps them (see
# server._drop_art_overrides).
ADJUST_KEYS = ("saturation", "contrast", "brightness", "gamma")
DEFAULT_ADJUST = {"saturation": 1.0, "contrast": 1.0, "brightness": 1.0,
                  "gamma": 1.0}
ADJUST_RANGES = {"saturation": (0.0, 3.0), "contrast": (0.0, 3.0),
                 "brightness": (0.0, 3.0), "gamma": (0.25, 4.0)}
# The per-art / `# Game` conversion keys (a `# Art` value wins over the game's).
# Dither is deliberately absent: it is chosen per build system (`## <id>`).
CONV_KEYS = ("match", "palette", "palette_colors") + ADJUST_KEYS
# Each `## <art-id>` under `# Art` owns a folder of candidate source images,
# <game>/assets/art/<id>/, holding one PNG per generation/upload/edit (named
# with a `<action>-<epoch>` prefix). The per-art `image:` line names the chosen
# file; absent means the newest PNG in the folder. A flat legacy
# <game>/assets/gen/art_<id>.png (or <id>.png) is still read as a fallback so an
# unmigrated game keeps building. `image:` is art-only and always persisted, so
# (like crop:) it is deliberately kept out of PARAM_KEYS.
ART_ROOT = os.path.join("assets", "art")
ART_LEGACY_ROOT = os.path.join("assets", "gen")
# Reusable image-model references (`## <ref-id>` under `# References`): generation-only images that
# an art can name in its `refs:` line. They live in their own folder of
# candidates, `<game>/assets/refs/<id>/`, and are never packed into the game.
REF_ROOT = os.path.join("assets", "refs")
_ART_IMAGE_RE = re.compile(r"^[A-Za-z0-9._-]+\.png$")
_REF_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
# Canonical section headings: a top-level `# Section` owns `## <id>` entries.
# Legacy files used the inverse (`## Section` + `# art <id>`), still read.
_SECTION_TITLES = {
    "game": "Game",
    "system": "Systems",
    "art": "Art",
    "ref": "References",
    "song": "Songs",
    "item": "Items",
    "scene": "Scenes",
}
_SECTION_KINDS = {title.lower(): kind
                  for kind, title in _SECTION_TITLES.items()}
def _top_heading(line):
    """The canonical section kind for a level-one heading, else ``None``."""
    if not line.startswith("# "):
        return None
    return _SECTION_KINDS.get(line[2:].strip().lower())


def _entry_heading(line):
    """The id of a canonical ``## <id>`` entry heading, else ``None``."""
    if not line.startswith("## "):
        return None
    parts = line[3:].split()
    return parts[0] if parts else None
# A selectable word in a `text:` line is written `{{word}}` or `{{word|flag}}`;
# choosing it in-game sets `flag` (default: the word, lowercased with
# non-alphanumerics replaced by `_`). The engine highlights the word and joins
# it to the option cursor (src/zx/, guarded by HAVE_WORDS). Curly braces
# (not `[[...]]`) keep the marker out of markdown's link syntax in the editor.
_WORD_RE = re.compile(r"\{\{(.+?)\}\}")
# Colour tokens for the `# Game` text colours: `text_ink` (body text, normal
# option labels and unselected inventory items) and `highlight_ink` (selected
# entries, every selectable word and the selected inventory item). Values are
# the z88dk conio codes the engine's set_colors()
# passes through (the console masks them to the ZX attribute colour, so `yellow`
# uses 14 -> 6) plus the BRIGHT bit. Plain names are the bright variants the
# option menu uses; a `dim_` prefix clears bright. Kept here so the generator
# and editor agree.
WORD_INKS = {
    "black": (0, 1), "blue": (1, 1), "green": (2, 1), "cyan": (3, 1),
    "red": (4, 1), "magenta": (5, 1), "yellow": (14, 1), "white": (7, 1),
}
for _name in list(WORD_INKS):
    WORD_INKS["dim_" + _name] = (WORD_INKS[_name][0], 0)
DEFAULT_TEXT_INK = "dim_white"
DEFAULT_HIGHLIGHT_INK = "green"
DEFAULT_TEXT_BG = "black"
DEFAULT_WORD_SEL_INK = "green"
# Dismiss prompt shown at the bottom of an option's `msg` popup.
DEFAULT_POPUP_HINT = "Press a key"
# The ZX `## zx128 title_ink:` target option: the scene/item heading inherits the
# configured text colour unless the author picks a distinct Spectrum ink.
TITLE_INK_INHERIT = "text"
TITLE_INK_TOKENS = (TITLE_INK_INHERIT,) + tuple(WORD_INKS)
# The z88dk 4x8 console font has no accented glyphs, so the build remaps these
# letters onto otherwise-blank ASCII slots (gen_scenes.esc_bytes, with the
# matching 4x8 bitmaps in ACCENT_GLYPHS) and folds this punctuation to ASCII.
# Every other non-ASCII character is rejected by the build, so the editor's
# validator must accept exactly this set for the printable-text fields.
ACCENT_BYTES = {'Á': 0x5B, 'Ñ': 0x5C, 'á': 0x5D, 'é': 0x5E, 'í': 0x5F,
                'Ü': 0x60, 'ü': 0x7B, 'ñ': 0x7C, 'ó': 0x7D, 'ú': 0x7E,
                '¿': 0x7F}
ROMANISE = {'¡': '!', '“': '"', '”': '"', '‘': "'", '’': "'",
            '—': '-', '–': '-', '…': '...',
            'À': 'A', 'Â': 'A', 'Ã': 'A', 'Ä': 'A',
            'Ç': 'C', 'È': 'E', 'É': 'E', 'Ê': 'E', 'Ë': 'E',
            'Ì': 'I', 'Í': 'I', 'Î': 'I', 'Ï': 'I',
            'Ò': 'O', 'Ô': 'O', 'Õ': 'O', 'Ö': 'O',
            'Ù': 'U', 'Ú': 'U', 'Û': 'U',
            'à': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a',
            'ç': 'c', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'ì': 'i', 'î': 'i', 'ï': 'i',
            'ò': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
            'ù': 'u', 'û': 'u'}


def text_printable(s):
    """True if ``s`` prints on the Spectrum: printable ASCII + accent glyphs."""
    return all(32 <= ord(c) <= 126 or c in ACCENT_BYTES or c in ROMANISE
               for c in s or "")


def word_flag(word):
    """The flag a `{{word}}` with no explicit `|flag` sets."""
    return re.sub(r"[^0-9A-Za-z]+", "_", word).strip("_").lower()


def word_segments(line):
    """Split a text line into rendering segments for selectable words.

    Returns a list of ``(text, flag)`` pairs: ``flag`` is ``None`` for ordinary
    text and the flag name for a ``{{word|flag}}`` word (default ``word_flag``).
    Joined in order this is the rendered line; the engine prints the whole line
    in body colour and reprints each word in its highlight colour.
    """
    segs, pos = [], 0
    for m in _WORD_RE.finditer(line):
        if m.start() > pos:
            segs.append((line[pos:m.start()], None))
        body = m.group(1)
        word, sep, flag = body.partition("|")
        word = word.strip()
        flag = (flag.strip() if sep else "") or word_flag(word)
        segs.append((word, flag))
        pos = m.end()
    if pos < len(line) or not segs:
        segs.append((line[pos:], None))
    return segs


def parse_words(line):
    """``word_segments`` collapsed to ``(clean_text, [{"word", "flag"}])``."""
    segs = word_segments(line)
    clean = "".join(t for t, _ in segs)
    return clean, [{"word": t, "flag": f} for t, f in segs if f is not None]


def text_tokens(game):
    """Resolve the game's text/highlight/background colour tokens.

    ``highlight_ink`` falls back to the legacy ``word_sel_ink`` spelling, and
    an unknown token to the role default.
    """
    g = game or {}

    def one(key, default, legacy=""):
        v = str(g.get(key) or (g.get(legacy) if legacy else "")
                or "").strip().lower()
        return v if v in WORD_INKS else default

    return (one("text_ink", DEFAULT_TEXT_INK),
            one("highlight_ink", DEFAULT_HIGHLIGHT_INK, "word_sel_ink"),
            one("text_bg", DEFAULT_TEXT_BG))


def text_colours(game):
    """Resolve the text colour roles to ``(ink, bright)`` pairs.

    Returns ``{"text", "highlight", "bg"}``. An unknown token falls back to the
    role default so a typo never fails the build; the editor's validator
    reports it.
    """
    text, highlight, bg = text_tokens(game)
    return {"text": WORD_INKS[text], "highlight": WORD_INKS[highlight],
            "bg": WORD_INKS[bg]}


def option_conditions(text):
    """The `if`/`unless` conditions on an option, in source order.

    Returns a list of ``(kind, name)`` where kind is ``"if"`` or ``"unless"``.
    """
    return [(m.group(1), m.group(2))
            for m in _COND_RE.finditer(text or "")]


def split_option_msg(raw):
    """Split an option's trailing ``msg <text>`` clause from its core line.

    Returns ``(option_without_msg, message)``. The message consumes the rest
    of the line, so ``if``/``unless``/``set``/... tokens must appear before it.
    An absent clause returns the unchanged option and an empty message. The
    clause is only looked for after ``-> <target>`` so a label containing the
    word ``msg`` is never mistaken for one.
    """
    s = str(raw or "")
    start = 0
    arrow = s.find("->")
    if arrow >= 0:
        start = arrow + 2
        mt = re.match(r"\s*\S+", s[start:])
        if mt:
            start += mt.end()
    while True:
        m = _OPT_MSG_RE.search(s, start)
        if not m:
            return s, ""
        before = s[:m.start()].rstrip().rsplit(None, 1)
        if before and before[-1].lower() in _OPT_EFFECT_WORDS:
            start = m.start() + 1
            continue
        return s[:m.start()].rstrip(), m.group(1).strip()


def split_text_line(line):
    """Split a scene text / item desc line into ``(rendered, conditions)``.

    Conditions are postfix, after `` -> `` (e.g. ``The van is here. -> if
    seen_van unless has_diesel``). The legacy ``if <flag>: text`` prefix is
    still accepted and normalised by the caller. ``conditions`` is a list of
    ``(kind, name)`` pairs in source order.
    """
    s = str(line or "").strip()
    m = _TEXT_COND_TAIL_RE.match(s)
    if m:
        return m.group(1).strip(), option_conditions(m.group(2))
    m = _LEGACY_TEXT_COND_RE.match(s)
    if m:
        return s[m.end():].strip(), option_conditions(m.group(1))
    return s, []


def is_system_flag(name):
    """True for a reserved build-time system flag (see ``SYSTEM_FLAGS``)."""
    return str(name or "") in SYSTEM_FLAGS


def system_condition_holds(kind, name, system):
    """Evaluate one condition if it names a system flag, else ``None``.

    ``system`` is the target id being generated (`"zx128"`, `"cpc"`, ...); the web
    export uses `"web"`, so every native system flag is false there. A
    condition on an ordinary flag/item returns ``None`` and is left to the
    runtime engine.
    """
    target = SYSTEM_FLAGS.get(str(name or ""))
    if target is None:
        return None
    wanted = target if isinstance(target, tuple) else (target,)
    holds = str(system or "").strip().lower() in wanted
    return holds if kind == "if" else not holds


def filter_system_conditions(conditions, system):
    """Fold build-time system conditions into the generated data.

    Returns the remaining runtime conditions, or ``None`` when any system
    condition is false for ``system`` (the whole line/option must be dropped).
    """
    out = []
    for kind, name in conditions or []:
        holds = system_condition_holds(kind, name, system)
        if holds is None:
            out.append((kind, name))
        elif not holds:
            return None
    return out


def wrap_spans(text, width):
    """Word-wrap ``text`` like ``text_next_segment`` in the shared engine.

    Returns ``(start, end)`` spans of the wrapped rows. A row breaks at its
    last space; an overlong token is hard-split at ``width`` and runs of spaces
    after a break are skipped. Kept byte-for-byte compatible with the C
    renderer so the editor's row-budget checks match the screen.
    """
    s = str(text or "")
    width = max(1, int(width))
    spans = []
    i, n = 0, len(s)
    while i < n:
        end = min(i + width, n)
        last = -1
        for j in range(i, end):
            if s[j] == " ":
                last = j
        take = last if end < n and last > i else end
        spans.append((i, take))
        i = take
        while i < n and s[i] == " ":
            i += 1
    return spans


def wrap_text(text, width):
    """The wrapped rows of ``text`` (see ``wrap_spans``)."""
    return [str(text or "")[a:b] for a, b in wrap_spans(text, width)]


def text_rows(text, width):
    """How many screen rows ``text`` wraps to at ``width`` columns."""
    return len(wrap_spans(text, width))


def fmt_text_line(text, conditions):
    """Render a text/desc line with postfix conditions (the canonical form)."""
    text = str(text or "").strip()
    conds = [(k, n) for k, n in (conditions or []) if n]
    if not conds:
        return text
    tokens = " ".join(f"{kind} {name}" for kind, name in conds)
    return f"{text} -> {tokens}" if text else f"-> {tokens}"

# Re-emitted (one line) at the top of every save so an editor write keeps the
# file's banner: the author-facing format documentation lives in
# docs/authoring.md.
# Prose is ignored on parse (it does not start with a section heading), and the
# first line is ``# game.md — ...``; the section head must therefore match a
# whole heading token, not just the prefix, or the banner would open a section.
HEADER = """\
# game.md — authoring format for a game's art, scenes, items and songs
""".splitlines()


def _param(rest, key, cast):
    m = re.search(rf"\b{key}\s*[:=]\s*(\S+)", rest)
    return cast(m.group(1)) if m else None


def _parse_params(rest, into):
    for key, cast in (("seed", int), ("steps", int), ("cfg", float),
                      ("size", int), ("width", int), ("height", int)):
        v = _param(rest, key, cast)
        if v is not None:
            into[key] = v
    return into


def canonical_target_id(target_id):
    """Canonical target id for a (possibly legacy) system name.

    The registry keeps old ids as aliases (``zx`` -> ``zx128``); without the
    registry (standalone scenefile use) the name is returned unchanged.
    """
    name = str(target_id or "").strip().lower()
    if not name:
        return name
    try:
        import targets
    except Exception:               # noqa: BLE001 - optional build registry
        return name
    target = targets.get_target(name)
    return target.id if target is not None else name


def _target_meta():
    """Target ids and game-key options from the build registry.

    Returns ``(ids, {(target_id, option_key): (game_key, default)})``. The
    registry import is lazy so scenefile still works on its own if the target
    package is unavailable (then only the legacy ``<id>_<key>`` extras
    round-trip).
    """
    try:
        import targets
    except Exception:               # noqa: BLE001 - optional build registry
        return set(), {}
    ids, game_opts = set(), {}
    for target in targets.all_targets().values():
        ids.add(target.id)
        for option in target.options:
            if option.game_key:
                game_opts[(target.id, option.key)] = (option.game_key,
                                                      option.default)
    return ids, game_opts


def _set_game_option(game, key, raw):
    """Apply a target option that lives as a top-level ``# Game`` setting."""
    if key == "art_lines":
        try:
            game["art_lines"] = int(raw or ART_LINES_DEFAULT)
        except (TypeError, ValueError):
            game["art_lines"] = ART_LINES_DEFAULT
    else:
        game[key] = raw


def parse(md):
    """Parse game.md text or path into {"game", "arts", "refs", "scenes", ...}.

    game:   {"title", "prompt", "seed", "steps", "cfg", "size", "width",
             "height", "art_lines", "start", "flags", "items", "songs",
             "music", "match", "palette", "palette_colors",
             "saturation", "contrast", "brightness", "gamma", "password",
             "password_label", "popup_hint", "carry", "inventory_drop",
             "inventory_back", "text_ink", "highlight_ink", "text_bg",
             "word_sel_ink"}
    arts:   [{"id", "prompt", "refs":[...], "image", "seed", "steps", "cfg",
              "size", "width", "height", "crop", <every CONV_KEYS key, None
              when inherited>}]
    refs:   [{"id", "prompt", "image", "seed", "steps", "cfg", "size",
              "width", "height"}]  (generation-only reference images)
    scenes: [{"id", "title", "art", "ending", "text":[...], "opts":[...]}]
    item_meta: {id: {"name": str, "desc": [str, ...], "opts": [str, ...]}}
               (only `## <item-id>` blocks under `# Items`; `name` is "" when the item has no
               display-name override)

    opts keep their raw author string ("label -> target if flag ...") so the
    generator and the editor both round-trip the exact text.
    """
    if isinstance(md, str) and os.path.exists(md):
        text = open(md, encoding="utf-8").read()
    else:
        text = md

    game = {"kind": "game", "title": "", "prompt": "", "seed": 42,
            "steps": STEPS_DEFAULT,
            "cfg": 6.0, "size": 256, "width": None, "height": None,
            "art_lines": ART_LINES_DEFAULT,
            "start": [], "targets": [], "extras": {},
            "flags": [], "items": [], "songs": [], "music": None,
            "password": "", "carry": 0,
            "password_label": "", "popup_hint": "",
            "inventory_drop": "", "inventory_back": "",
            "text_ink": "", "highlight_ink": "", "text_bg": "",
            "item_ink": "", "word_ink": "", "word_sel_ink": "",
            "negative_prompt": "",
            "hires": 1.0, "hires_steps": HIRES_STEPS_DEFAULT,
            "hires_denoise": HIRES_DENOISE_DEFAULT,
            "refine_denoise": REFINE_DENOISE_DEFAULT,
            "match": None, "palette": None, "palette_colors": None,
            "saturation": None, "contrast": None, "brightness": None,
            "gamma": None}
    arts, refs, scenes = [], [], []
    item_meta = {}
    cur, mode = None, None
    section, style = None, None
    target_ids, game_opts = _target_meta()
    system_order, system_options = [], {}
    legacy_dither = None

    for raw in text.splitlines():
        line = raw.rstrip("\n")
        s = line.strip()

        if cur is not None and mode in ("prompt", "negative") \
                and line[:1].isspace() and (s or line != ""):
            key = "prompt" if mode == "prompt" else "negative_prompt"
            indent = len(line) - len(line.lstrip(" "))
            soft = s and indent == len(_PROMPT_INDENT)
            cur[key] += (" " if soft else "\n") + s
            continue
        sec = _top_heading(line)
        if sec is not None:
            section, style = sec, "canonical"
            cur = game if sec == "game" else None
            mode = None
            continue
        ident = _entry_heading(line)
        if ident is not None:
            if style == "canonical" and section not in (None, "game"):
                if section == "art":
                    cur = {"kind": "art", "id": ident, "prompt": "",
                           "seed": None, "steps": None, "cfg": None,
                           "size": None, "width": None, "height": None,
                           "crop": None, "image": None, "refs": []}
                    for _k in CONV_KEYS:
                        cur[_k] = None
                    arts.append(cur)
                elif section == "ref":
                    cur = {"kind": "ref", "id": ident, "prompt": "",
                           "seed": None, "steps": None, "cfg": None,
                           "size": None, "width": None, "height": None,
                           "image": None}
                    refs.append(cur)
                elif section == "song":
                    # AI prompt blocks no longer exist; skip old sections.
                    cur = None
                elif section == "item":
                    cur = item_meta.setdefault(
                        ident, {"kind": "item", "id": ident, "name": "",
                                "desc": [], "opts": []})
                elif section == "scene":
                    cur = {"kind": "scene", "id": ident, "title": "",
                           "art": None, "ending": None, "music": None,
                           "text": [], "opts": []}
                    scenes.append(cur)
                elif section == "system":
                    sid = canonical_target_id(ident.lower())
                    if sid and sid not in system_options:
                        system_options[sid] = {}
                        system_order.append(sid)
                    cur = {"kind": "system", "id": sid}
                mode = None
            else:
                cur, mode = None, None
            continue
        if line.strip() == "# game":
            section, style = "game", "legacy"
            cur, mode = game, None
        elif line.startswith("# art "):
            section, style = "art", "legacy"
            aid = line.split(None, 2)[2].strip()
            cur = {"kind": "art", "id": aid, "prompt": "", "seed": None,
                   "steps": None, "cfg": None, "size": None, "width": None,
                   "height": None, "crop": None, "image": None, "refs": []}
            for _k in CONV_KEYS:
                cur[_k] = None
            arts.append(cur)
            mode = None
        elif line.startswith("# ref "):
            section, style = "ref", "legacy"
            rid = line.split(None, 2)[2].strip()
            cur = {"kind": "ref", "id": rid, "prompt": "", "seed": None,
                   "steps": None, "cfg": None, "size": None, "width": None,
                   "height": None, "image": None}
            refs.append(cur)
            mode = None
        elif line.startswith("# song "):
            section, style = "song", "legacy"
            cur = None
            mode = None
        elif line.startswith("# item "):
            section, style = "item", "legacy"
            iid = line.split(None, 2)[2].strip()
            cur = item_meta.setdefault(iid, {"kind": "item", "id": iid,
                                             "name": "", "desc": [],
                                             "opts": []})
            mode = None
        elif line.startswith("# scene "):
            section, style = "scene", "legacy"
            words = line.split(None, 3)
            cur = {"kind": "scene", "id": words[2],
                   "title": words[3] if len(words) > 3 else "",
                   "art": None, "ending": None, "music": None,
                   "text": [], "opts": []}
            scenes.append(cur)
            mode = None
        elif line.startswith("# system "):
            section, style = "system", "legacy"
            words = line.split(None, 2)
            sid = canonical_target_id(
                words[2].strip().lower() if len(words) > 2 else "")
            if sid and sid not in system_options:
                system_options[sid] = {}
                system_order.append(sid)
            cur = {"kind": "system", "id": sid}
            mode = None
        elif cur is not None:
            if cur.get("kind") == "system":
                if s.startswith("#"):
                    mode = None
                elif s and ":" in s:
                    key, _, val = s.partition(":")
                    key = key.strip()
                    sid = cur["id"]
                    if key in ("text_ink", "highlight_ink", "text_bg"):
                        # Text colours are Game-tab settings; ignore stale
                        # per-system overrides so a save drops them.
                        continue
                    if sid and re.match(r"^[a-z][a-z0-9_]*$", key):
                        key_alias = _SYSTEM_KEY_ALIASES.get((sid, key))
                        if key_alias:
                            system_options[sid][key_alias] = val.strip()
                            continue
                        game_key = (game_opts.get((sid, key))
                                    or _SYSTEM_OPTION_ALIASES.get((sid, key)))
                        if game_key:
                            _set_game_option(game, game_key[0], val.strip())
                        else:
                            system_options[sid][key] = val.strip()
                continue
            if s.startswith("#"):
                mode = None
            elif s.startswith("title:") and cur is game:
                mode = None
                cur["title"] = s[6:].strip()
            elif s.startswith("prompt:"):
                mode = "prompt"
                cur["prompt"] = s[7:].strip()
            elif s.startswith("negative_prompt:"):
                mode = "negative" if cur is game else None
                if cur is game:
                    cur["negative_prompt"] = s[16:].strip()
            elif s.startswith("desc:") and cur.get("kind") == "item":
                mode = "desc"
                cur["desc"] = [fmt_text_line(*split_text_line(s[5:]))]
            elif s.startswith("name:") and cur.get("kind") == "item":
                mode = None
                cur["name"] = s[5:].strip()
            elif s.startswith("name:") and cur.get("kind") == "scene":
                mode = None
                cur["title"] = s[5:].strip()
            elif s.startswith("start:"):
                mode = None
                cur["start"] = s[6:].replace(",", " ").split()
            elif s.startswith("flags:") and cur is game:
                mode = None
                cur["flags"] = s[6:].replace(",", " ").split()
            elif s.startswith("items:") and cur is game:
                mode = None
                cur["items"] = s[6:].replace(",", " ").split()
            elif s.startswith("songs:") and cur is game:
                mode = None
                cur["songs"] = s[6:].replace(",", " ").split()
            elif s.startswith("targets:") and cur is game:
                mode = None
                cur["targets"] = [t for t in s[8:].replace(",", " ").split()
                                  if t]
            elif s.startswith("art:"):
                cur["art"] = s[4:].strip()
            elif s.startswith("ending:"):
                cur["ending"] = s[7:].strip()
            elif s.startswith("music:"):
                cur["music"] = s[6:].strip()
            elif s.startswith("dither:") and cur.get("kind") in ("game", "art"):
                # Legacy global/per-art setting. Dither is now selected per
                # system; keep a global value for migration, drop art ones.
                mode = None
                if cur is game:
                    legacy_dither = s[7:].strip().lower() or DEFAULT_DITHER
            elif s.startswith("match:") and cur.get("kind") in ("game", "art"):
                mode = None
                cur["match"] = s[6:].strip().lower() or DEFAULT_MATCH
            elif s.startswith("palette_colors:") \
                    and cur.get("kind") in ("game", "art"):
                mode = None
                v = s[15:].strip()
                try:
                    cur["palette_colors"] = int(v)
                except ValueError:
                    cur["palette_colors"] = None
            elif s.startswith("palette:") and cur.get("kind") in ("game", "art"):
                mode = None
                cur["palette"] = s[8:].strip().lower() or DEFAULT_PALETTE
            elif cur.get("kind") in ("game", "art") and any(
                    s.startswith(k + ":") for k in ADJUST_KEYS):
                mode = None
                key, _, val = s.partition(":")
                try:
                    cur[key] = float(val.strip())
                except ValueError:
                    cur[key] = None
            elif s.startswith("hires:"):
                mode = None
                if cur is game:
                    v = s[6:].strip().lower()
                    if v in ("off", "", "1", "1x"):
                        cur["hires"] = 1.0
                    else:
                        try:
                            cur["hires"] = float(v.rstrip("x"))
                        except ValueError:
                            cur["hires"] = 1.0
            elif s.startswith("hires_steps:"):
                mode = None
                if cur is game:
                    try:
                        cur["hires_steps"] = int(s[12:].strip())
                    except ValueError:
                        cur["hires_steps"] = HIRES_STEPS_DEFAULT
            elif s.startswith("hires_denoise:"):
                mode = None
                if cur is game:
                    try:
                        cur["hires_denoise"] = float(s[14:].strip())
                    except ValueError:
                        cur["hires_denoise"] = HIRES_DENOISE_DEFAULT
            elif s.startswith("refine_denoise:"):
                mode = None
                if cur is game:
                    try:
                        cur["refine_denoise"] = float(s[15:].strip())
                    except ValueError:
                        cur["refine_denoise"] = REFINE_DENOISE_DEFAULT
            elif s.startswith("password:") and cur is game:
                mode = None
                cur["password"] = s[9:].strip()
            elif s.startswith("password_label:") and cur is game:
                mode = None
                cur["password_label"] = s[15:].strip()
            elif s.startswith("popup_hint:") and cur is game:
                mode = None
                cur["popup_hint"] = s[11:].strip()
            elif s.startswith("inventory_drop:") and cur is game:
                mode = None
                cur["inventory_drop"] = s[15:].strip()
            elif s.startswith("inventory_back:") and cur is game:
                mode = None
                cur["inventory_back"] = s[15:].strip()
            elif s.startswith("text_ink:") and cur is game:
                mode = None
                cur["text_ink"] = s[9:].strip()
            elif s.startswith("highlight_ink:") and cur is game:
                mode = None
                cur["highlight_ink"] = s[14:].strip()
            elif s.startswith("text_bg:") and cur is game:
                mode = None
                cur["text_bg"] = s[8:].strip()
            elif s.startswith("item_ink:") and cur is game:
                mode = None               # legacy: consumed, then dropped on save
                cur["item_ink"] = s[9:].strip()
            elif s.startswith("word_ink:") and cur is game:
                mode = None               # legacy: consumed, then dropped on save
                cur["word_ink"] = s[9:].strip()
            elif s.startswith("word_sel_ink:") and cur is game:
                mode = None
                cur["word_sel_ink"] = s[13:].strip()
            elif s.startswith("art_lines:") and cur is game:
                mode = None
                try:
                    cur["art_lines"] = int(s[10:].strip() or ART_LINES_DEFAULT)
                except ValueError:
                    cur["art_lines"] = ART_LINES_DEFAULT
            elif s.startswith("carry:") and cur is game:
                mode = None
                cur["carry"] = int(s[6:].strip() or 0)
            elif s.startswith("opt:"):
                mode = "opt"
                cur.setdefault("opts", []).append(s[4:].strip())
            elif s == "text:":
                mode = "text"
            elif s.startswith("refs:") and cur.get("kind") == "art":
                mode = None
                toks = s[5:].replace(",", " ").split()
                cur["refs"] = list(dict.fromkeys(t for t in toks if t))
            elif s.startswith("image:") and cur.get("kind") in ("art", "ref"):
                mode = None
                name = s[6:].strip()
                cur["image"] = name if valid_art_image(name) else None
            elif s.startswith("crop:") and cur.get("kind") == "art":
                mode = None
                toks = s[5:].replace(",", " ").split()
                if len(toks) == 4:
                    try:
                        cur["crop"] = [float(t) for t in toks]
                    except ValueError:
                        pass
            elif any(s.startswith(k + ":") for k in PARAM_KEYS):
                mode = None
                _parse_params(s, cur)
            elif s and mode in ("prompt", "negative"):
                key = "prompt" if mode == "prompt" else "negative_prompt"
                cur[key] += "\n" + s
            elif s and mode == "text":
                cur["text"].append(fmt_text_line(*split_text_line(s)))
            elif s and mode == "desc":
                cur["desc"].append(fmt_text_line(*split_text_line(s)))
            elif s and mode == "opt":
                cur["opts"][-1] += " " + s
            elif cur is game and mode is None and ":" in s:
                key, _, val = s.partition(":")
                key = key.strip()
                if re.match(r"^[a-z][a-z0-9_]*$", key):
                    prefix, sep, suffix = key.partition("_")
                    if sep and suffix == "art_lines" \
                            and prefix in target_ids:
                        key = prefix + "_art_rows"
                    cur.setdefault("extras", {})[key] = val.strip()

    # A Systems section selects its systems and stores each option as the
    # legacy `<id>_<key>` extra, so the build/editor share one option store.
    for sid in system_order:
        for key, val in system_options[sid].items():
            game["extras"][f"{sid}_{key}"] = val
    if system_order:
        game["targets"] = system_order
    # The old shared ZX `art_lines` also set the 48K band. Keep those games
    # unchanged now that `## zx48 art_rows` is independent: copy a non-default
    # legacy value into the 48K extras only when its block omits it.
    selected = [canonical_target_id(t) for t in (game.get("targets") or [])
                if str(t).strip()] or ["zx128"]
    if "zx48" in selected and "zx48_art_rows" not in game["extras"]:
        legacy_lines = art_lines(game)
        if legacy_lines != ART_LINES_DEFAULT:
            game["extras"]["zx48_art_rows"] = str(legacy_lines)
    # Migrate a legacy global dither to every selected system that has no
    # per-system value yet. A per-art dither cannot map to systems and is dropped.
    if legacy_dither in _DITHER_MODES and legacy_dither != DEFAULT_DITHER:
        selected = system_order or [
            canonical_target_id(t) for t in (game.get("targets") or [])
            if str(t).strip()] or ["zx128"]
        for sid in selected:
            game["extras"].setdefault(f"{sid}_dither", legacy_dither)

    for a in arts + refs:
        for k in PARAM_KEYS:
            if a.get(k) is None:
                a[k] = game[k]
    # A reference id is unique; a duplicate heading keeps the first section.
    seen_refs = set()
    unique_refs = []
    for r in refs:
        if r["id"] in seen_refs:
            continue
        seen_refs.add(r["id"])
        unique_refs.append(r)
    return {"game": game, "arts": arts, "refs": unique_refs,
            "scenes": scenes, "item_meta": item_meta}


def outline_links(text):
    """Map game.md references to their definition, for editor Ctrl+click.

    Returns a list of ``{"kind", "id", "line", "startColumn", "endColumn",
    "defLine", "defStartColumn", "defEndColumn"}`` (1-based line/column) for
    every scene/art/song/item/flag reference whose definition is present in the
    buffer. The Source tab's Monaco definition provider turns each into a
    Ctrl+click jump. A definition is a ``## <id>`` entry heading under its
    section (or a legacy ``# Scenes``/``# Art``/``# Items`` heading) or a
    ``flags:``/``items:``/``songs:``/``start:`` entry,
    preferring the earliest such declaration over later uses and falling back to
    the first use when nothing declares the name. A malformed file yields
    ``[]`` (the validator reports the error).
    """
    try:
        doc = parse(text)
    except Exception:               # noqa: BLE001 - a bad line breaks the parse
        return []
    try:
        _, item_list, _ = assign_flags(
            doc["scenes"], doc["game"].get("start", []),
            doc["game"].get("flags", []),
            declared_items(doc["game"], doc.get("item_meta")),
            item_meta=doc.get("item_meta"))
    except Exception:               # noqa: BLE001 - classify best-effort only
        item_list = []
    items = set(item_list)

    def kind_of(name):
        """A flag-context name is an item when ``assign_flags`` made it one."""
        return "item" if name in items else "flag"

    # Each occurrence: (kind, id, 1-based line, 0-based col span, priority).
    # The lowest priority (then earliest line) occurrence of a (kind, id) is its
    # definition; every other occurrence links to it.
    occ = []

    def add(kind, name, line, cs, ce, prio):
        name = (name or "").strip()
        if name:
            occ.append({"kind": kind, "id": name, "line": line,
                        "cs": cs, "ce": ce, "prio": prio})

    def field(rawn, key):
        """(col0 start, col0 end, token) of the first token after ``key``."""
        k = rawn.find(key)
        if k < 0:
            return -1, -1, ""
        m = re.match(r"\s*(\S+)", rawn[k + len(key):])
        if not m:
            return -1, -1, ""
        s = k + len(key) + m.start(1)
        return s, k + len(key) + m.end(1), m.group(1)

    def add_opt(rawn, line):
        core, _msg = split_option_msg(rawn)
        arrow = core.find("->")
        if arrow < 0:
            return
        after = core[arrow + 2:]
        mt = re.match(r"\s*(\S+)", after)
        if not mt:
            return
        tgt = mt.group(1)
        # An item option may target a scene or use `-> -` (return to the
        # current scene). A scene option uses `-> -` to re-enter that same
        # scene, so only then link the dash to the containing scene.
        if tgt == "-":
            if section == "scene" and cur_scene:
                add("scene", cur_scene, line, arrow + 2 + mt.start(1),
                    arrow + 2 + mt.end(1), 2)
        else:
            add("scene", tgt, line, arrow + 2 + mt.start(1),
                arrow + 2 + mt.end(1), 2)
        base = arrow + 2 + mt.end()
        for km in re.finditer(
                r"\b(if|unless|set|unset|pick|leave|inscene)\s+(\S+)",
                after[mt.end():]):
            kw, name = km.group(1), km.group(2)
            cs = base + km.start(2)
            if kw == "inscene":
                add("scene", name, line, cs, cs + len(name), 3)
            elif kw in ("pick", "leave"):
                add("item", name, line, cs, cs + len(name), 3)
            elif kw in ("set", "unset"):
                add(kind_of(name), name, line, cs, cs + len(name), 3)
            else:               # if / unless: item when declared, else flag
                add(kind_of(name), name, line, cs, cs + len(name), 3)

    def cond_spans(rawn):
        """(rendered_start, rendered_end, [(kind, name, start, end)])."""
        m = re.search(r"->\s*((?:(?:if|unless)\s+\S+\s*)+)$", rawn)
        if m:
            base = m.start(1)
            return 0, m.start(), [
                (cm.group(1), cm.group(2), base + cm.start(2),
                 base + cm.end(2))
                for cm in re.finditer(r"\b(if|unless)\s+(\S+)", m.group(1))]
        lead = len(rawn) - len(rawn.lstrip())
        m = _LEGACY_TEXT_COND_RE.match(rawn[lead:])
        if m:
            base = lead
            return base + m.end(), len(rawn), [
                (cm.group(1), cm.group(2), base + cm.start(2),
                 base + cm.end(2))
                for cm in re.finditer(r"\b(if|unless)\s+(\S+)", m.group(1))]
        return 0, len(rawn), []

    def add_text(rawn, line):
        start, end, conds = cond_spans(rawn)
        for _kind, name, cs, ce in conds:
            add(kind_of(name), name, line, cs, ce, 3)
        rendered = rawn[start:end]
        for wm in _WORD_RE.finditer(rendered):
            word_part, sep, flag_part = wm.group(1).partition("|")
            if sep:
                name = flag_part.strip()
                if name:
                    lead = len(flag_part) - len(flag_part.lstrip())
                    cs = start + wm.start(1) + len(word_part) + 1 + lead
                    add(kind_of(name), name, line, cs, cs + len(name), 3)
            else:
                word = word_part.strip()
                if word:
                    lead = len(word_part) - len(word_part.lstrip())
                    cs = start + wm.start(1) + lead
                    add(kind_of(word_flag(word)), word_flag(word), line,
                        cs, cs + len(word), 3)

    def add_cond(rawn, line):
        """Conditions on an item desc line (`desc:` line or a continuation)."""
        m = re.match(r"^(\s*desc:\s*)", rawn)
        offset = m.end() if m else 0
        _start, _end, conds = cond_spans(rawn[offset:])
        for _kind, name, cs, ce in conds:
            add(kind_of(name), name, line, offset + cs, offset + ce, 3)

    section, style, mode = None, None, None
    cur_scene = None
    for i, rawn in enumerate(text.splitlines()):
        line = i + 1
        stripped = rawn.strip()
        sec = _top_heading(rawn)
        if sec is not None:
            section, style, mode = sec, "canonical", None
            cur_scene = None
            continue
        ident = _entry_heading(rawn)
        if ident is not None:
            if style == "canonical" and section in ("art", "ref", "item",
                                                    "scene"):
                cs = rawn.index(ident, 3)
                add(section, ident, line, cs, cs + len(ident), 0)
                cur_scene = ident if section == "scene" else None
            else:
                mode = None
            continue
        if rawn.startswith("# "):
            words = rawn.split(None, 2)
            if len(words) >= 3 and words[1] in ("art", "ref", "item",
                                                "scene"):
                section, style, mode = words[1], "legacy", None
                cur_scene = (words[2].split()[0]
                             if words[1] == "scene" else None)
                prefix = "# " + words[1] + " "
                cs = len(prefix)
                ce = cs + len(words[2].split()[0])
                add(words[1], words[2].split()[0], line, cs, ce, 0)
            else:
                section, style, mode = None, None, None
            continue
        if section == "game":
            m = re.match(r"^\s*(start|flags|items|songs):(.*)$", rawn)
            if m:
                kind = {"start": "item", "flags": "flag",
                        "items": "item", "songs": "song"}[m.group(1)]
                base = m.start(2)
                for tm in re.finditer(r"[^\s,]+", m.group(2)):
                    add(kind, tm.group(0), line, base + tm.start(),
                        base + tm.end(), 1)
                continue
            if stripped.startswith("music:"):
                cs, ce, name = field(rawn, "music:")
                if name and name.lower() not in _SONG_ONOFF:
                    add("song", name, line, cs, ce, 2)
            continue
        if section == "scene":
            if stripped.startswith("art:"):
                mode = None
                cs, ce, name = field(rawn, "art:")
                if name:
                    add("art", name, line, cs, ce, 2)
            elif stripped.startswith("ending:"):
                mode = None
                cs, ce, name = field(rawn, "ending:")
                if name:
                    add(kind_of(name), name, line, cs, ce, 2)
            elif stripped.startswith("music:"):
                mode = None
                cs, ce, name = field(rawn, "music:")
                if name and name.lower() not in _SONG_ONOFF:
                    add("song", name, line, cs, ce, 2)
            elif stripped == "text:":
                mode = "text"
            elif stripped.startswith("opt:"):
                mode = "opt"
                add_opt(rawn, line)
            elif stripped and mode == "opt":
                add_opt(rawn, line)
            elif stripped and mode == "text":
                add_text(rawn, line)
            elif stripped:
                mode = None
            continue
        if section == "art":
            if stripped.startswith("refs:"):
                toks = stripped[5:].replace(",", " ").split()
                base = rawn.find("refs:") + 5
                pos = rawn.find(stripped[5:], base)
                for tm in re.finditer(r"\S+", stripped[5:]):
                    name = tm.group(0)
                    add("ref", name, line, pos + tm.start(),
                        pos + tm.end(), 3)
            continue
        if section == "item":
            if stripped.startswith("opt:"):
                mode = "opt"
                add_opt(rawn, line)
            elif stripped and mode == "opt":
                add_opt(rawn, line)
            elif stripped.startswith("desc:"):
                mode = "desc"
                add_cond(rawn, line)
            elif stripped and mode == "desc":
                add_cond(rawn, line)
            elif stripped:
                mode = None
            continue

    defs = {}
    for o in occ:
        key = (o["kind"], o["id"])
        cur = defs.get(key)
        if cur is None or (o["prio"], o["line"], o["cs"]) < \
                (cur["prio"], cur["line"], cur["cs"]):
            defs[key] = o

    links, seen = [], set()
    for o in occ:
        d = defs.get((o["kind"], o["id"]))
        if d is None or (o["line"], o["cs"]) == (d["line"], d["cs"]):
            continue
        if (o["line"], o["cs"], o["ce"]) in seen:
            continue
        seen.add((o["line"], o["cs"], o["ce"]))
        links.append({"kind": o["kind"], "id": o["id"],
                      "line": o["line"],
                      "startColumn": o["cs"] + 1, "endColumn": o["ce"] + 1,
                      "defLine": d["line"],
                      "defStartColumn": d["cs"] + 1,
                      "defEndColumn": d["ce"] + 1})
    return links


def declared_items(game, item_meta=None):
    """Inventory item ids: the `items:` list plus every `# Items` entry.

    A `## <item-id>` block supplements (never replaces) the `items:` list, so
    it merely confirms an id exists and carries its description. Order is the
    declared `items:` order, then any section-only ids in file order.
    """
    names = list((game or {}).get("items", []))
    for n in (item_meta or {}):
        if n not in names:
            names.append(n)
    return names


def item_display_names(game, item_meta=None):
    """Map each inventory item id to its display name (the id when unnamed).

    Every declared item (the `items:` list plus every `# Items` entry) maps to
    the `name:` of its section, falling back to the id itself. The engine shows
    this name on the inventory band and item screen while the id stays the token
    used in `pick`/`leave`/`if`; an item with no section is simply its id.
    """
    names = {}
    for n in declared_items(game, item_meta):
        disp = str(((item_meta or {}).get(n) or {}).get("name") or "").strip()
        names[n] = disp or n
    return names


FLAG_BASE = 0
ITEM_BASE = 128
MAX_FLAGS = 128
MAX_ITEMS = 64
SCENE_NONE = 255
FLAG_NONE = 255


def assign_flags(blocks, start_names=(), declared_flags=(),
                 declared_items=(), item_names=None, item_meta=None):
    """Collect every named flag into one id space 0..191.

    Names get ids in first-appearance order: explicit declarations first
    (`# Game flags:` / `items:`), then `start:` names, then usage. A name is an
    inventory item when it is declared under `items:`, listed in `start:` or
    used with `pick`/`leave`; anything else is a game flag. Items take ids from
    ITEM_BASE so the engine can iterate them contiguously; returns (flag_map,
    item_list, order). Kept here so generator and editor agree.

    ``item_names`` optionally maps an item id to its display name (see
    ``item_display_names``); item ids are then ordered by that display name so
    the in-game band and the editor list read alphabetically on screen. Without
    it the id itself is the sort key (display name == id).

    ``item_meta`` is the ``# Items`` entries (id -> {desc, opts}); an item
    option's effects name flags (or items), so they are collected too.
    ``if``/``unless`` conditions only test names: they must already be declared
    or assigned elsewhere and do not create a flag/item. An ``inscene`` token
    names a scene, not a flag, and is ignored here.

    A name explicitly declared under both ``flags:`` and ``items:``, or two
    names differing only by case, is an error (the engine's id space is flat).
    Usage is not strict: an item (declared, in ``start:`` or ``pick``/``leave``)
    may still be tested/effected as a flag, since items are flags.
    """
    order, is_item = [], set()

    def note(name, item=False):
        if not name:
            return
        if name in SYSTEM_FLAGS:
            raise ValueError(
                f"{name!r} is a build-time system flag; use it only in "
                "if/unless conditions")
        if name not in order:
            order.append(name)
        if item:
            is_item.add(name)

    for name in declared_flags:
        note(name, item=False)
    for name in declared_items:
        note(name, item=True)
    # start names are inventory items, even if only `if`-tested later
    for name in start_names:
        note(name, item=True)
    # an explicit flag must not also be an explicit item
    both = (set(declared_flags) & set(declared_items))
    if both:
        raise ValueError(
            f"{sorted(both)[0]!r} is declared as both a flag and an item")

    for b in blocks:
        note(b.get("ending"))
        for t in b.get("text", []):
            # A `{{word|flag}}` marker makes the word set its flag. Conditions
            # only *test* names, so they must already exist (declared or set
            # elsewhere) rather than introducing a flag.
            rendered, _conds = split_text_line(t)
            for w in parse_words(rendered)[1]:
                note(w["flag"])
        for o in b["opts"]:
            core, _msg = split_option_msg(o)
            m = _OPT_RE.match(core)
            if not m:
                continue
            rest = m.group(3)
            for key in ("set", "unset"):
                for mm in re.finditer(rf"\b{key}\s+(\S+)", rest):
                    note(mm.group(1))
            for mm in re.finditer(r"\bleave\s+(\S+)", rest):
                note(mm.group(1), item=True)
            for mm in re.finditer(r"\bpick\s+(\S+)", rest):
                note(mm.group(1), item=True)

    for meta in (item_meta or {}).values():
        # Item options name flags/items like a scene option. `inscene` is a
        # scene id, not a flag, and description conditions only test names.
        for o in meta.get("opts", []):
            core, _msg = split_option_msg(o)
            m = _OPT_RE.match(core)
            if not m:
                continue
            rest = m.group(3)
            for key in ("set", "unset"):
                for mm in re.finditer(rf"\b{key}\s+(\S+)", rest):
                    note(mm.group(1))
            for mm in re.finditer(r"\bleave\s+(\S+)", rest):
                note(mm.group(1), item=True)
            for mm in re.finditer(r"\bpick\s+(\S+)", rest):
                note(mm.group(1), item=True)

    folded = {}
    for n in order:
        low = n.lower()
        if low in folded and folded[low] != n:
            raise ValueError(
                f"flag/item names {folded[low]!r} and {n!r} collide")
        folded[low] = n
    # Item ids are contiguous from ITEM_BASE and the in-game inventory band
    # walks them in id order, so order the items by display name: the band then
    # reads alphabetically on screen (falling back to the id when unnamed).
    disp = item_names or {}
    item_list = sorted((n for n in order if n in is_item),
                       key=lambda n: (disp.get(n) or n).lower())
    flag_map = {}
    lo = 0
    for name in order:
        if name in is_item:
            flag_map[name] = ITEM_BASE + item_list.index(name)
        else:
            flag_map[name] = FLAG_BASE + lo
            lo += 1
    if lo > MAX_FLAGS:
        raise ValueError(f"too many flags ({lo} > {MAX_FLAGS})")
    if len(item_list) > MAX_ITEMS:
        raise ValueError(f"too many items ({len(item_list)} > {MAX_ITEMS})")
    return flag_map, item_list, order


def resolve_song(entry, game=None):
    """Resolve the song id a scene should play, or ``None`` for silence.

    ``entry`` is the scene (its ``music:`` override) and ``game`` the ``# Game``
    section (default). A scene's value wins; a bare token that is not ``off``
    is a song id, and ``on`` means "the game's default, else the first declared
    song". An absent value falls through to the game default, and a game with
    no default and no songs is silent, so existing games are unchanged.
    """
    def token_of(e):
        return str(e.get("music")).strip() if e and e.get("music") else None

    tok = token_of(entry)
    if tok is None:
        tok = token_of(game)
    songs = (game or {}).get("songs") or []
    if tok is None:
        return None
    low = tok.lower()
    if low == "off":
        return None
    if low == "on":
        return songs[0] if songs else None
    return tok


def valid_art_image(name):
    """True if ``name`` is a safe PNG basename usable as an `image:` value."""
    return bool(name) and "/" not in name and "\\" not in name \
        and name not in (".", "..") and _ART_IMAGE_RE.match(name) is not None


def valid_ref_id(name):
    """True if ``name`` is a safe reference id (it also names its image folder)."""
    return bool(_REF_ID_RE.match(str(name or "")))


def art_image_name(art):
    """The art's explicit `image:` filename, or None (newest/legacy fallback)."""
    name = str((art or {}).get("image") or "").strip()
    return name if valid_art_image(name) else None


def ref_image_name(ref):
    """The reference's explicit `image:` filename, or None (newest fallback)."""
    name = str((ref or {}).get("image") or "").strip()
    return name if valid_art_image(name) else None


def ref_dir(ref_root, ref_id):
    """The folder holding a reference's candidate images."""
    return os.path.join(ref_root, ref_id)


def list_ref_images(ref_root, ref_id):
    """Candidate PNG paths for a reference, newest-mtime first."""
    if not valid_ref_id(ref_id):
        return []
    d = ref_dir(ref_root, ref_id)
    if not os.path.isdir(d):
        return []
    out = []
    for name in os.listdir(d):
        p = os.path.join(d, name)
        if valid_art_image(name) and os.path.isfile(p):
            out.append(p)
    out.sort(key=lambda p: (-os.path.getmtime(p), os.path.basename(p)))
    return out


def resolve_ref_image(ref_root, ref):
    """The source PNG for a reference, or None when it has no image yet."""
    rid = (ref or {}).get("id")
    if not rid or not valid_ref_id(rid):
        return None
    name = ref_image_name(ref)
    if name:
        return os.path.join(ref_dir(ref_root, rid), name)
    imgs = list_ref_images(ref_root, rid)
    return imgs[0] if imgs else None


def art_dir(art_root, art_id):
    """The folder holding an art's candidate images (``art_root`` is assets/art)."""
    return os.path.join(art_root, art_id)


def list_art_images(art_root, art_id):
    """Candidate PNG paths for an art, newest-mtime first (ties by name).

    Only safe PNG basenames are returned, so a hand-dropped file cannot escape
    the art's folder.
    """
    d = art_dir(art_root, art_id)
    if not os.path.isdir(d):
        return []
    out = []
    for name in os.listdir(d):
        p = os.path.join(d, name)
        if valid_art_image(name) and os.path.isfile(p):
            out.append(p)
    out.sort(key=lambda p: (-os.path.getmtime(p), os.path.basename(p)))
    return out


def resolve_art_image(art_root, art, legacy_dir=None):
    """The source PNG for an art, or None when it has no image yet.

    An explicit ``image:`` wins (returned even if the file is missing, so the
    build/validator can report the broken pointer); otherwise the newest
    candidate in the art's folder, then a flat legacy ``art_<id>.png`` /
    ``<id>.png`` under ``legacy_dir`` (assets/gen).
    """
    aid = (art or {}).get("id")
    if not aid:
        return None
    name = art_image_name(art)
    if name:
        return os.path.join(art_dir(art_root, aid), name)
    imgs = list_art_images(art_root, aid)
    if imgs:
        return imgs[0]
    if legacy_dir:
        for leg in (f"art_{aid}.png", f"{aid}.png"):
            p = os.path.join(legacy_dir, leg)
            if os.path.isfile(p):
                return p
    return None


def hires_scale(game):
    """The high-resolution second-pass scale (1.0 = off), clamped to 1..4."""
    try:
        v = float((game or {}).get("hires") or 1.0)
    except (TypeError, ValueError):
        return 1.0
    return min(4.0, max(1.0, v))


def hires_options(game):
    """Resolve the optional high-res pass to SD API fields (1x = disabled)."""
    scale = hires_scale(game)
    try:
        steps = int((game or {}).get("hires_steps", HIRES_STEPS_DEFAULT))
    except (TypeError, ValueError):
        steps = HIRES_STEPS_DEFAULT
    try:
        denoise = float((game or {}).get("hires_denoise", HIRES_DENOISE_DEFAULT))
    except (TypeError, ValueError):
        denoise = HIRES_DENOISE_DEFAULT
    return {"scale": scale, "steps": max(1, steps),
            "denoise": min(1.0, max(0.0, denoise))}


def output_dimensions(entry, game):
    """The PNG size a generation writes, including the high-res pass."""
    w, h = dimensions(entry, game)
    s = hires_scale(game)
    return int(round(w * s)), int(round(h * s))


def refine_denoise(game):
    """Denoising strength for the 'refine current image' 2x pass."""
    try:
        v = float((game or {}).get("refine_denoise", REFINE_DENOISE_DEFAULT))
    except (TypeError, ValueError):
        v = REFINE_DENOISE_DEFAULT
    return min(1.0, max(0.0, v))


def dimensions(entry, game):
    """Resolve an art/game entry to (width, height) output pixels.

    ``width``/``height`` win; a missing axis falls back to the legacy square
    ``size``, and with neither set the default is the recommended band source,
    512x256 (2:1). The default 256x80 art band is 3.2:1 (see ``art_lines``), so
    a 512x256 source crops vertically (see ``art_crop``).
    """
    size = entry.get("size") or game.get("size")
    w = entry.get("width") or game.get("width")
    h = entry.get("height") or game.get("height")
    if w is not None and h is not None:
        return int(w), int(h)
    if size is not None:
        s = int(size)
        return int(w or s), int(h or s)
    return int(w or DEFAULT_WIDTH), int(h or DEFAULT_HEIGHT)


def art_crop(entry, game=None):
    """Resolve an art's crop rectangle to ``[x, y, w, h]`` (percent, 0..100).

    Returns ``None`` when unset, meaning the centred band-aspect window (see
    ``zxart.crop_rect``). A malformed value also falls back to ``None``. The
    editor's resizable box keeps the art band's aspect (``32/art_lines``), so the
    region scales to the band undistorted.
    """
    v = (entry or {}).get("crop")
    if v is None:
        v = (game or {}).get("crop")
    if v is None:
        return None
    if isinstance(v, (list, tuple)) and len(v) == 4:
        out = []
        for t in v:
            try:
                out.append(float(t))
            except (TypeError, ValueError):
                return None
        return out
    return None


def system_dither(game, target_id):
    """Resolve one build system's dither mode (see ``zxart.DITHER_MODES``).

    Dither is stored in the system's ``## <id>`` block as ``dither:`` (the
    legacy ``<id>_dither`` extra). A missing, legacy-boolean or unknown value
    maps to ``off`` so a hand-edited file still builds.
    """
    sid = canonical_target_id(target_id)
    if not sid:
        return DEFAULT_DITHER
    d = ((game or {}).get("extras") or {}).get(f"{sid}_dither")
    if d is False:
        return DEFAULT_DITHER
    if not isinstance(d, str):
        return DEFAULT_DITHER
    return d.strip().lower() if d.strip().lower() in _DITHER_MODES \
        else DEFAULT_DITHER


def system_margin(game, target_id):
    """Resolve one build system's art margin in 8x8 cells (see ``ART_MARGIN_CELL``).

    Stored in the system's ``## <id>`` block as ``margin:`` (the legacy
    ``<id>_margin`` extra). Missing, non-numeric or negative values map to 0 so
    a hand-edited file still builds. Too-large values are clamped by the
    converter so the picture always keeps at least one pixel.
    """
    sid = canonical_target_id(target_id)
    if not sid:
        return 0
    raw = ((game or {}).get("extras") or {}).get(f"{sid}_margin")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


def _as_float(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def conversion_options(entry, game=None, target_id=None):
    """Resolve an art's complete conversion settings for one build system.

    Returns ``{"crop", "dither", "margin", "match", "palette",
    "palette_colors", "adjust"}`` where ``adjust`` is ``{saturation, contrast,
    brightness, gamma}``. ``dither`` and ``margin`` come from ``target_id``'s
    ``## <id>`` block (see ``system_dither``/``system_margin``); the other
    values come from ``entry`` (an art) when set, else from ``game`` (the
    ``# Game`` section), else the built-in default.
    Invalid or out-of-range values fall back to the default (the editor's
    validator reports them) so a hand-edited file still builds. The build and
    the editor previews share this one resolver.
    """
    g = game or {}

    def pick(key):
        v = (entry or {}).get(key)
        return g.get(key) if v is None else v

    dither = system_dither(g, target_id)
    sid = canonical_target_id(target_id)
    raw_mono = ((g.get("extras") or {}).get(f"{sid}_mono")
                if sid else None)
    mono = str(raw_mono).strip().lower() in ("1", "true", "on", "yes")

    match = pick("match")
    if not isinstance(match, str) or match not in MATCH_MODES:
        match = DEFAULT_MATCH

    palette = pick("palette")
    if not isinstance(palette, str) or palette not in PALETTE_MODES:
        palette = DEFAULT_PALETTE

    pc = pick("palette_colors")
    try:
        pc = int(pc)
    except (TypeError, ValueError):
        pc = DEFAULT_PALETTE_COLORS
    pc = max(2, min(256, pc))

    adjust = {}
    for key in ADJUST_KEYS:
        lo, hi = ADJUST_RANGES[key]
        adjust[key] = _clamp(_as_float(pick(key), 1.0), lo, hi)

    return {"crop": art_crop(entry, g), "dither": dither,
            "margin": system_margin(g, target_id), "match": match,
            "palette": palette, "palette_colors": pc, "adjust": adjust,
            "mono": mono}


def art_lines(game):
    """Resolve a game's art-band height in character rows (even, 8..16).

    A NIRVANA+ tile is 16px = 2 character rows, so the value must be even: the
    band is ``8 * art_lines`` px tall and the engine races ``art_lines``
    attribute rows (1..art_lines), leaving rows ``art_lines+1..22`` for text and
    row 23 for the inventory band. 10 (the default) is the 256x80 band. An
    absent, odd or out-of-range value falls back to the nearest valid even value
    (the editor reports a hand-edited odd value).
    """
    try:
        n = int((game or {}).get("art_lines", ART_LINES_DEFAULT))
    except (TypeError, ValueError):
        return ART_LINES_DEFAULT
    if n < ART_LINES_MIN:
        return ART_LINES_MIN
    if n > ART_LINES_MAX:
        return ART_LINES_MAX
    return n - (n & 1)


def _prompt_lines(text, width=PROMPT_WRAP, key="prompt"):
    """Render a ``prompt:`` value as its first line plus continuations.

    The first line carries the ``key: `` prefix. Each following line of the
    value is written with ``_PROMPT_BREAK_INDENT`` (an empty line as the bare
    indent), so the parser reads it back as a newline. A long line is wrapped
    at ``width`` with ``_PROMPT_INDENT`` continuations; the parser rejoins
    those with a single space, so layout wrapping never changes the value.
    Words are wrapped without touching the value: a break is only taken at a
    single space, so a run of two or more spaces stays on one line (and an
    over-long word or run overflows rather than being altered). The empty
    value keeps a bare ``prompt: `` line.
    """
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    prefix = f"{key}: "
    if not text:
        return [prefix]
    lines = []
    for i, hard in enumerate(text.split("\n")):
        hard = hard.strip()
        start = prefix if i == 0 else _PROMPT_BREAK_INDENT
        if not hard:
            lines.append(start)
            continue
        cur = start
        has_word = False
        gap = ""
        for tok in re.findall(r"\S+|\s+", hard):
            if tok.isspace():
                gap = tok
                continue
            if has_word and len(gap) == 1 \
                    and len(cur) + len(gap) + len(tok) > width:
                lines.append(cur)
                cur = _PROMPT_INDENT + tok
            else:
                cur += (gap if has_word else "") + tok
            has_word = True
            gap = ""
        lines.append(cur)
    return lines


def reference_prompt_suffix(refs):
    """Qwen-Image wording that points the prompt at its conditioning images.

    A single reference is named naturally; several are numbered so the model
    can map each ``extra_images`` entry (sent in author order) to its role.
    """
    n = len([r for r in (refs or []) if r])
    if n == 0:
        return ""
    if n == 1:
        return "keep the same design as in the reference image"
    if n == 2:
        return "keep the same designs as in image 1 and image 2"
    middle = ", ".join(f"image {i}" for i in range(2, n))
    return f"keep the same designs as in image 1, {middle} and image {n}"


def compose_prompt(game_prompt, art_prompt, refs=None):
    """Prefix the shared style prompt and point at any reference images."""
    g = (game_prompt or "").strip().rstrip(",")
    a = (art_prompt or "").strip()
    prompt = f"{g}, {a}" if g and a else (g or a)
    suffix = reference_prompt_suffix(refs)
    if suffix:
        prompt = f"{prompt}, {suffix}" if prompt else suffix
    return prompt


def password_label(game):
    """The boot-screen prompt line, defaulting to ``Enter the password:``."""
    g = game or {}
    return str(g.get("password_label") or "").strip() or "Enter the password:"


def popup_hint(game):
    """The dismiss prompt shown in an option's ``msg`` popup."""
    g = game or {}
    return str(g.get("popup_hint") or "").strip() or DEFAULT_POPUP_HINT


def inventory_strings(game):
    """Resolve the item screen's strings.

    Returns ``{"drop", "back"}``: the labels of the item screen's Drop and Back
    entries. A blank/absent ``inventory_*`` key falls back to the built-in
    default. Mirrors the engine's paged inventory blob (tools/gen_scenes.py).
    """
    g = game or {}

    def pick(key, default):
        v = str(g.get(key) or "").strip()
        return v or default

    return {
        "drop": pick("inventory_drop", "Drop"),
        "back": pick("inventory_back", "Back"),
    }


def serialize(doc):
    """Render a project dict back to game.md text (canonical layout)."""
    g = doc["game"]
    # Selected systems come from `game.targets` (parsed from the Systems
    # section; legacy `targets:` still reads). Every selected system gets a
    # block, and its non-default options move from `extras` into that block.
    selected = list(dict.fromkeys(
        canonical_target_id(t) for t in (g.get("targets") or [])
        if str(t).strip()))
    selected = selected or ["zx128"]
    target_ids, game_opts = _target_meta()
    system_opts = {sid: {} for sid in selected}
    leftover = {}
    for key in sorted((g.get("extras") or {})):
        val = g["extras"][key]
        if val is None or str(val) == "":
            continue
        prefix, sep, suffix = key.partition("_")
        prefix = canonical_target_id(prefix) if sep else prefix
        if sep and prefix in target_ids:
            if suffix in ("text_ink", "highlight_ink", "text_bg"):
                continue
            if prefix in system_opts:
                # The old `art_lines` spelling is canonicalised to the shared
                # `art_rows` key so a save never emits both.
                if suffix == "art_lines":
                    suffix = "art_rows"
                system_opts[prefix][suffix] = val
        else:
            leftover[key] = val
    for (sid, okey), (gkey, default) in game_opts.items():
        if sid not in system_opts:
            continue
        raw = g.get(gkey)
        if raw is None or str(raw).strip() == "":
            continue
        if str(raw) != str(default):
            system_opts[sid][okey] = raw
    out = []
    out.extend(HEADER)
    out.append("")
    out.append("# Game")
    out.append("")
    if g.get("title"):
        out.append(f"title: {g['title'].strip()}")
    out.extend(_prompt_lines(g.get("prompt", "")))
    if (g.get("negative_prompt") or "").strip():
        out.extend(_prompt_lines(g["negative_prompt"], key="negative_prompt"))
    if g.get("start"):
        out.append("start: " + ", ".join(g["start"]))
    if g.get("flags"):
        out.append("flags: " + ", ".join(g["flags"]))
    if g.get("items"):
        out.append("items: " + ", ".join(g["items"]))
    if g.get("songs"):
        out.append("songs: " + ", ".join(g["songs"]))
    if g.get("music"):
        out.append(f"music: {str(g['music']).strip()}")
    gconv = conversion_options(g, g)
    if gconv["match"] != DEFAULT_MATCH:
        out.append(f"match: {gconv['match']}")
    if gconv["palette"] != DEFAULT_PALETTE:
        out.append(f"palette: {gconv['palette']}")
        if gconv["palette"] == "adaptive" \
                and gconv["palette_colors"] != DEFAULT_PALETTE_COLORS:
            out.append(f"palette_colors: {gconv['palette_colors']}")
    for key in ADJUST_KEYS:
        if gconv["adjust"][key] != DEFAULT_ADJUST[key]:
            out.append(f"{key}: {gconv['adjust'][key]:g}")
    hscale = hires_scale(g)
    if hscale > 1.0:
        out.append(f"hires: {hscale:g}x")
        if int(g.get("hires_steps", HIRES_STEPS_DEFAULT)) != HIRES_STEPS_DEFAULT:
            out.append(f"hires_steps: {int(g['hires_steps'])}")
        if float(g.get("hires_denoise", HIRES_DENOISE_DEFAULT)) != HIRES_DENOISE_DEFAULT:
            out.append(f"hires_denoise: {float(g['hires_denoise']):g}")
    rden = float(g.get("refine_denoise", REFINE_DENOISE_DEFAULT))
    if rden != REFINE_DENOISE_DEFAULT:
        out.append(f"refine_denoise: {rden:g}")
    if (g.get("password") or "").strip():
        out.append(f"password: {g['password'].strip()}")
    if (g.get("password_label") or "").strip():
        out.append(f"password_label: {g['password_label'].strip()}")
    if (g.get("popup_hint") or "").strip():
        out.append(f"popup_hint: {g['popup_hint'].strip()}")
    for key in ("inventory_drop", "inventory_back"):
        if (g.get(key) or "").strip():
            out.append(f"{key}: {g[key].strip()}")
    colour_keys = (
        ("text_ink", g.get("text_ink"), DEFAULT_TEXT_INK),
        ("highlight_ink", g.get("highlight_ink") or g.get("word_sel_ink"),
         DEFAULT_HIGHLIGHT_INK),
        ("text_bg", g.get("text_bg"), DEFAULT_TEXT_BG),
    )
    for key, raw, default in colour_keys:
        v = str(raw or "").strip()
        if v and v.lower() != default:
            out.append(f"{key}: {v}")
    if int(g.get("carry", 0) or 0) > 0:
        out.append(f"carry: {int(g['carry'])}")
    for key in sorted(leftover):
        out.append(f"{key}: {leftover[key]}")
    out.append(f"seed: {int(g.get('seed', 42))}")
    out.append(f"steps: {int(g.get('steps', STEPS_DEFAULT))}")
    out.append(f"cfg: {float(g.get('cfg', 6.0)):g}")
    w, h = dimensions(g, g)
    out.append(f"width: {w}")
    out.append(f"height: {h}")
    out.append("")
    out.append("# Systems")
    out.append("")
    for sid in selected:
        out.append(f"## {sid}")
        opts = system_opts.get(sid) or {}
        for key in sorted(opts):
            out.append(f"{key}: {opts[key]}")
        out.append("")
    out.append("# Art")
    out.append("")
    for a in doc["arts"]:
        out.append(f"## {a['id']}")
        out.extend(_prompt_lines(a.get("prompt", "")))
        if a.get("refs"):
            out.append("refs: " + " ".join(a["refs"]))
        img = art_image_name(a)
        if img:
            out.append(f"image: {img}")
        for k in PARAM_KEYS:
            if a.get(k) is not None and a.get(k) != g.get(k):
                v = f"{float(a[k]):g}" if k == "cfg" else str(int(a[k]))
                out.append(f"{k}: {v}")
        cr = art_crop(a)
        if cr is not None:
            out.append("crop: " + " ".join(str(int(round(x))) for x in cr))
        aconv = conversion_options(a, g)
        if a.get("match") is not None and aconv["match"] != gconv["match"]:
            out.append(f"match: {aconv['match']}")
        if a.get("palette") is not None and aconv["palette"] != gconv["palette"]:
            out.append(f"palette: {aconv['palette']}")
        if a.get("palette_colors") is not None \
                and aconv["palette_colors"] != gconv["palette_colors"]:
            out.append(f"palette_colors: {aconv['palette_colors']}")
        for key in ADJUST_KEYS:
            if a.get(key) is not None \
                    and aconv["adjust"][key] != gconv["adjust"][key]:
                out.append(f"{key}: {aconv['adjust'][key]:g}")
        out.append("")
    refs = doc.get("refs") or []
    if refs:
        out.append("# References")
        out.append("")
        for r in refs:
            out.append(f"## {r['id']}")
            out.extend(_prompt_lines(r.get("prompt", "")))
            img = ref_image_name(r)
            if img:
                out.append(f"image: {img}")
            for k in PARAM_KEYS:
                if r.get(k) is not None and r.get(k) != g.get(k):
                    v = f"{float(r[k]):g}" if k == "cfg" else str(int(r[k]))
                    out.append(f"{k}: {v}")
            out.append("")
    item_meta = doc.get("item_meta") or {}
    item_block = []
    for iid in declared_items(g, item_meta):
        meta = item_meta.get(iid) or {}
        name = str(meta.get("name") or "").strip()
        lines = [fmt_text_line(*split_text_line(str(x)))
                 for x in (meta.get("desc") or [])]
        lines = [x for x in lines if x]
        opts = [str(x).strip() for x in (meta.get("opts") or [])]
        opts = [x for x in opts if x]
        if not lines and not opts and (not name or name == iid):
            continue
        item_block.append(f"## {iid}")
        if name and name != iid:
            item_block.append(f"name: {name}")
        if lines:
            item_block.append(f"desc: {lines[0]}")
            for ln in lines[1:]:
                item_block.append(f"  {ln}")
        for o in opts:
            item_block.append(f"opt: {o}")
        item_block.append("")
    if item_block:
        out.append("# Items")
        out.append("")
        out.extend(item_block)
    out.append("# Scenes")
    out.append("")
    for s in doc["scenes"]:
        out.append(f"## {s['id']}")
        title = str(s.get("title", "") or "").strip()
        if title:
            out.append(f"name: {title}")
        out.append(f"art: {s.get('art', '')}")
        if s.get("ending"):
            out.append(f"ending: {s['ending']}")
        if s.get("music"):
            out.append(f"music: {str(s['music']).strip()}")
        out.append("text:")
        for t in s.get("text", []):
            t = fmt_text_line(*split_text_line(t))
            if t:
                out.append(f"  {t}")
        for o in s.get("opts", []):
            out.append(f"opt: {o}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"
