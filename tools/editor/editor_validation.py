"""Validation and linting for game.md (project, scenes, art, items)."""

from __future__ import annotations

import targets

from server import *  # noqa: F401,F403 - shared state and helpers

def _conv_issues(entry, g, section, sid, issues, need_field):
    """Validate one entry's source-conversion settings.

    A value outside the accepted set/range silently falls back to its default at
    build time, so each is reported. For an art, ``need`` is the offending key
    so the Source tab can underline the art's own line; for the game the issue
    id is the key itself (``_annotate_lines`` finds the ``key:`` line).
    """
    def add(key, msg):
        it = {"level": "warn", "section": section,
              "id": key if section == "game" else sid, "msg": msg}
        if need_field:
            it["need"] = key
        issues.append(it)

    d = entry.get("dither")
    if d not in (True, False, None) and d not in scenefile.DITHER_MODES:
        add("dither", f"unknown dither '{d}'; using "
                      f"{scenefile.conversion_options(entry, g)['dither']}")
    m = entry.get("match")
    if m is not None and (not isinstance(m, str)
                          or m not in scenefile.MATCH_MODES):
        add("match", f"unknown match '{m}'; using {scenefile.DEFAULT_MATCH}")
    p = entry.get("palette")
    if p is not None and (not isinstance(p, str)
                          or p not in scenefile.PALETTE_MODES):
        add("palette", f"unknown palette '{p}'; using "
                       f"{scenefile.DEFAULT_PALETTE}")
    pc = entry.get("palette_colors")
    if pc is not None:
        try:
            pcv = int(pc)
        except (TypeError, ValueError):
            pcv = None
        if pcv is None or not 2 <= pcv <= 256:
            add("palette_colors", "palette_colors must be 2..256; using "
                                  f"{scenefile.DEFAULT_PALETTE_COLORS}")
    for key in scenefile.ADJUST_KEYS:
        v = entry.get(key)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            fv = None
        lo, hi = scenefile.ADJUST_RANGES[key]
        if fv is None or not lo <= fv <= hi:
            add(key, f"{key} must be {lo:g}..{hi:g}; using 1")


def _cond_sets(conditions):
    """Split conditions into (must be set, must be clear) name sets."""
    need, clear = set(), set()
    for kind, name in conditions or []:
        if not name:
            continue
        (need if kind == "if" else clear).add(name)
    return need, clear


def _max_visible_rows(entries, scene_bits=None, item_names=(), carry=0):
    """Worst-case visible rows over every satisfiable flag/item combination.

    ``entries`` are ``(rows, required_set, clear_set, scene, pick_item)``;
    ``scene`` is an ``inscene`` id or ``None``. A subset is possible when no
    name is both required set and clear, all its ``inscene`` values agree, and
    a ``pick`` entry still has room under ``carry``. The maximum satisfiable
    subset weight is exactly the maximum over all flag/item assignments,
    without enumerating every flag (2^14 subsets at most).
    """
    n = len(entries)
    if not n:
        return 0
    names = sorted({name for _rows, need, clear, _scene, _pick in entries
                    for name in need | clear})
    bits = {name: 1 << i for i, name in enumerate(names)}
    item_mask = 0
    for name in item_names:
        item_mask |= bits.get(name, 0)
    req = [0] * n
    clr = [0] * n
    row = [0] * n
    scene = [0] * n
    picks = [0] * n
    for i, (rows, need, clear, sid, pick) in enumerate(entries):
        row[i] = rows
        for name in need:
            req[i] |= bits[name]
        for name in clear:
            clr[i] |= bits[name]
        if sid is not None:
            scene[i] = (scene_bits or {}).get(sid, 0)
        if pick:
            picks[i] = bits.get(pick, 0)
    size = 1 << n
    reqs = [0] * size
    clrs = [0] * size
    rows = [0] * size
    scenes = [0] * size
    picked = [0] * size
    best = 0
    for mask in range(1, size):
        lsb = mask & -mask
        i = lsb.bit_length() - 1
        prev = mask ^ lsb
        rv = reqs[prev] | req[i]
        cv = clrs[prev] | clr[i]
        sv = scenes[prev] | scene[i]
        pv = picked[prev] | picks[i]
        reqs[mask], clrs[mask], scenes[mask], picked[mask] = rv, cv, sv, pv
        total = rows[prev] + row[i]
        rows[mask] = total
        if rv & cv or (sv and (sv & (sv - 1))):
            continue
        if pv and carry > 0 and bin(rv & item_mask).count("1") >= carry:
            continue
        if total > best:
            best = total
    return best


def _crossed_words(rendered, width):
    """Selectable words that a wrap would split across two screen rows."""
    clean, _words = scenefile.parse_words(rendered)
    spans = scenefile.wrap_spans(clean, width)
    if len(spans) <= 1:
        return []
    crossed, pos = [], 0
    for text, flag in scenefile.word_segments(rendered):
        if flag is not None and text:
            start, end = pos, pos + len(text)
            if not any(a <= start and end <= b for a, b in spans):
                crossed.append(text)
        pos += len(text)
    return crossed


# ------------------------------------------------------------------ project

def _validate(doc, slug):
    """Static checks mirrored from the build limits; returns a list of issues.

    Each issue: {"level": "error"|"warn", "section": "art"/"scene"/"song",
    "id": ..., "msg": ...}. ``slug`` locates the game's files (art PNGs and
    song .pt3 modules).
    """
    issues = []
    from editor_games import _art_root, _ref_root
    from editor_music import song_path
    game = gamestore.resolve(slug)
    gen_dir = gamestore.gen_dir(slug) or ""
    art_root = _art_root(game["dir"]) if game else ""
    ref_root = _ref_root(game["dir"]) if game else ""
    g = doc["game"]
    arts = doc["arts"]
    refs = doc.get("refs") or []
    scenes = doc["scenes"]
    art_ids = [a["id"] for a in arts]
    ref_ids = [r["id"] for r in refs]
    scene_ids = [s["id"] for s in scenes]
    # Art band height in character rows (even 8..16); it drives the scene row
    # budget and how many item-description lines fit (see below).
    band_lines = scenefile.art_lines(g)
    # The row budget below is the ZX layout. Next uses the same layout with its
    # own art_rows/menu options, so validate the tighter of the selected ZX
    # systems (and fold the matching system_* conditions).
    selected_systems = targets.selected_targets(doc)
    fit_system = "zx"
    zx_target = targets.get_target("zx")
    next_target = targets.get_target("next")
    zx_popup = bool(zx_target and "zx" in selected_systems
                    and targets.target_options(doc, zx_target).get("menu"))
    if next_target is not None and "next" in selected_systems:
        next_opts = targets.target_options(doc, next_target)
        next_rows = int(next_opts.get("art_rows") or 10)
        if "zx" not in selected_systems or next_rows > band_lines:
            band_lines = next_rows
            fit_system = "next"
            zx_popup = bool(next_opts.get("menu"))

    for dup in {x for x in art_ids if art_ids.count(x) > 1}:
        issues.append({"level": "error", "section": "art", "id": dup,
                       "msg": "duplicate art id"})
    for a in arts:
        if not _valid_art_id(a["id"]):
            issues.append({"level": "error", "section": "art", "id": a["id"],
                           "msg": "art id must be letters, digits, - or _ "
                                  "(it names the art's image folder)"})
    for dup in {x for x in scene_ids if scene_ids.count(x) > 1}:
        issues.append({"level": "error", "section": "scene", "id": dup,
                       "msg": "duplicate scene id"})

    reachable = set()
    if scene_ids:
        reachable.add(scene_ids[0])
        # An item option can navigate too. An item is reachable from anywhere
        # it can be held, so seed its targets rather than trying to model the
        # inventory; this stays conservative and avoids false "unreachable".
        for meta in (doc.get("item_meta") or {}).values():
            for o in meta.get("opts", []):
                m = re.match(r"(.+?)\s*->\s*(\S+)", o)
                if m and m.group(2) in scene_ids:
                    reachable.add(m.group(2))
        changed = True
        while changed:
            changed = False
            for s in scenes:
                if s["id"] not in reachable:
                    continue
                for o in s["opts"]:
                    m = re.match(r"(.+?)\s*->\s*(\S+)", o)
                    if m and m.group(2) in scene_ids and m.group(2) not in reachable:
                        reachable.add(m.group(2))
                        changed = True

    # Names that already exist: explicit declarations (including section-only
    # `# Items` ids) and everything assigned by an effect. Conditions only test
    # these names and never create one, so a typo cannot silently add a flag.
    item_meta = doc.get("item_meta") or {}
    declared = (list(g.get("flags", []))
                + list(scenefile.declared_items(g, item_meta)))
    given = set(g.get("start", [])) | set(declared) | set(scenefile.SYSTEM_FLAGS)
    for s in scenes:
        if s.get("ending"):
            given.add(s["ending"])
        # A `{{word|flag}}` marker sets its flag when chosen, like an option's
        # `set`.
        for t in s.get("text", []):
            rendered, _conds = scenefile.split_text_line(t)
            for w in scenefile.parse_words(rendered)[1]:
                given.add(w["flag"])
        for o in s["opts"]:
            for key in ("set", "unset", "pick", "leave"):
                for m in re.finditer(rf"\b{key}\s+(\S+)", o):
                    given.add(m.group(1))

    # `# Items` option effects name flags/items too.
    for meta in item_meta.values():
        for o in meta.get("opts", []):
            for key in ("set", "unset", "pick", "leave"):
                for m in re.finditer(rf"\b{key}\s+(\S+)", o):
                    given.add(m.group(1))

    # Build-time `system_*` pseudo-flags are valid only in conditions. They
    # never become real flags/items, so reject them where the format needs one.
    def check_reserved(section, ident, need, name):
        if scenefile.is_system_flag(name):
            issues.append({"level": "error", "section": section, "id": ident,
                           "need": need,
                           "msg": f"'{name}' is a build-time system flag; "
                                  "use it only in if/unless conditions"})

    for key in ("flags", "items"):
        for name in g.get(key, []):
            check_reserved("game", name, None, name)
    for name in g.get("start", []):
        check_reserved("game", name, None, name)
    for s in scenes:
        check_reserved("scene", s["id"], None, s.get("ending"))
        for t in s.get("text", []):
            rendered, _conds = scenefile.split_text_line(t)
            for w in scenefile.parse_words(rendered)[1]:
                check_reserved("scene", s["id"], t, w["flag"])
        for o in s.get("opts", []):
            for key in ("set", "unset", "pick", "leave"):
                for m in re.finditer(rf"\b{key}\s+(\S+)", o):
                    check_reserved("scene", s["id"], o, m.group(1))
    for iid, meta in item_meta.items():
        for o in meta.get("opts", []):
            for key in ("set", "unset", "pick", "leave"):
                for m in re.finditer(rf"\b{key}\s+(\S+)", o):
                    check_reserved("item", iid, o, m.group(1))

    # Explicit flag/item declarations must be unique and not clash.
    seen = {}
    for kind, names in (("flags", g.get("flags", [])),
                        ("items", g.get("items", []))):
        for name in names:
            low = name.lower()
            if low in seen:
                msg = (f"duplicate {kind[:-1]} '{name}'" if seen[low] == kind
                       else f"'{name}' is declared as both {seen[low]} and {kind}")
                issues.append({"level": "error", "section": "game",
                               "id": name, "msg": msg})
            else:
                seen[low] = kind
    # A declared name that is never referenced is likely a leftover.
    used = set(g.get("start", []))
    for s in scenes:
        if s.get("ending"):
            used.add(s["ending"])
        for t in s.get("text", []):
            rendered, conds = scenefile.split_text_line(t)
            for _kind, name in conds:
                used.add(name)
            for w in scenefile.parse_words(rendered)[1]:
                used.add(w["flag"])
        for o in s["opts"]:
            for _kind, name in scenefile.option_conditions(o):
                used.add(name)
            for key in ("set", "unset", "pick", "leave"):
                for m in re.finditer(rf"\b{key}\s+(\S+)", o):
                    used.add(m.group(1))
    for meta in item_meta.values():
        for t in meta.get("desc", []):
            for _kind, name in scenefile.split_text_line(t)[1]:
                used.add(name)
        for o in meta.get("opts", []):
            for _kind, name in scenefile.option_conditions(o):
                used.add(name)
            for key in ("set", "unset", "pick", "leave"):
                for m in re.finditer(rf"\b{key}\s+(\S+)", o):
                    used.add(m.group(1))
    for kind in ("flags", "items"):
        for name in g.get(kind, []):
            if name not in used:
                issues.append({"level": "warn", "section": "game", "id": name,
                               "msg": f"declared {kind[:-1]} '{name}' is never used"})

    # `# Items` sections carry inventory descriptions and their own options.
    # The id joins the item list (like a `pick`/`leave` name) but is not a game
    # flag; descriptions and entries wrap, and the pinned item screen must fit
    # the worst case across every flag/item combination.
    for name in item_meta:
        if name in g.get("flags", []):
            issues.append({"level": "error", "section": "game", "id": name,
                           "msg": f"'{name}' has an # Items entry but is "
                                  "declared in flags:"})
    carry = int(g.get("carry", 0) or 0)
    scene_bits = {sid: 1 << i for i, sid in enumerate(scene_ids)}
    inv_ui = scenefile.inventory_strings(g)
    item_names = (set(scenefile.declared_items(g, item_meta))
                  | set(g.get("start", [])))
    for s in scenes:
        for o in s.get("opts", []):
            for m in re.finditer(r"\b(?:pick|leave)\s+(\S+)", o):
                item_names.add(m.group(1))
    for meta in item_meta.values():
        for o in meta.get("opts", []):
            for m in re.finditer(r"\b(?:pick|leave)\s+(\S+)", o):
                item_names.add(m.group(1))
    for name, meta in item_meta.items():
        # `name:` overrides the id as the display name shown in the item list
        # and inventory band. It prints straight into the band, so it must be
        # printable text that fits one band row.
        disp = str(meta.get("name") or "").strip()
        if disp:
            if not scenefile.text_printable(disp):
                issues.append({"level": "error", "section": "item", "id": name,
                               "msg": "display name must be printable text "
                                      "(no control characters)"})
            elif len(disp) > ITEM_NAME_COLS:
                issues.append({"level": "error", "section": "item", "id": name,
                               "msg": f"display name is {len(disp)} columns; "
                                      f"the band fits {ITEM_NAME_COLS} in a row"})
        lines = [str(x).strip() for x in (meta.get("desc") or [])]
        lines = [x for x in lines if x]
        opts = [str(x).strip() for x in (meta.get("opts") or [])]
        opts = [x for x in opts if x]
        fit_entries = []
        if not lines and not disp and not opts:
            issues.append({"level": "warn", "section": "item", "id": name,
                           "msg": "empty description"})
        if len(lines) > 4:
            issues.append({"level": "error", "section": "item", "id": name,
                           "msg": f"{len(lines)} description lines; the engine "
                                  "shows at most 4"})
        # Conditions are postfix (after `->`) and are not displayed; long
        # description lines are word-wrapped by the engine.
        for ln in lines:
            rendered, conds = scenefile.split_text_line(ln)
            if len(conds) > scenefile.MAX_CONDITIONS:
                issues.append({"level": "error", "section": "item", "id": name,
                               "need": ln,
                               "msg": f"more than {scenefile.MAX_CONDITIONS} "
                                      "conditions on a description line"})
            for _kind, cname in conds:
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", cname):
                    issues.append({"level": "error", "section": "item",
                                   "id": name, "need": ln,
                                   "msg": f"condition flag '{cname}' must be "
                                          "letters, digits or _"})
                elif cname not in given:
                    issues.append({"level": "error", "section": "item",
                                   "id": name, "need": ln,
                                   "msg": f"condition '{cname}' is not a "
                                          "declared or set flag/item"})
            folded = scenefile.filter_system_conditions(conds, fit_system)
            if folded is None:
                continue
            need, clear = _cond_sets(folded)
            fit_entries.append(
                (scenefile.text_rows(rendered, TEXT_COLS), need, clear,
                 None, None))
        if len(opts) > 6:
            issues.append({"level": "error", "section": "item", "id": name,
                           "msg": f"{len(opts)} options (max 6)"})
        for o in opts:
            core, popup = scenefile.split_option_msg(o)
            om = scenefile._OPT_RE.match(core)
            if not om:
                issues.append({"level": "error", "section": "item", "id": name,
                               "need": o, "msg": f"bad option: {o}"})
                continue
            label, target, rest = om.group(1), om.group(2), om.group(3)
            if popup:
                if not scenefile.text_printable(popup):
                    issues.append({"level": "error", "section": "item",
                                   "id": name, "need": o,
                                   "msg": "popup message must be printable "
                                          "text (no control characters)"})
                if "{{" in popup:
                    issues.append({"level": "warn", "section": "item",
                                   "id": name, "need": o,
                                   "msg": "selectable words are not parsed "
                                          "in a popup message"})
            if target != "-" and target not in scene_ids:
                issues.append({"level": "error", "section": "item", "id": name,
                               "need": o,
                               "msg": f"option targets missing scene '{target}'"})
            if "{{" in label:
                issues.append({"level": "warn", "section": "item", "id": name,
                               "need": o,
                               "msg": "selectable words are only parsed in "
                                      "text: lines; {{...}} in an option label "
                                      "shows literally"})
            if len(label) > OPT_COLS:
                issues.append({"level": "warn", "section": "item", "id": name,
                               "need": o,
                               "msg": f"option label >{OPT_COLS} cols: "
                                      f"{label[:20]}..."})
            ic = re.search(r"\binscene\s+(\S+)", rest)
            if ic and ic.group(1) not in scene_ids:
                issues.append({"level": "error", "section": "item", "id": name,
                               "need": o,
                               "msg": f"inscene '{ic.group(1)}' is not a scene"})
            if re.search(r"\bifgroup\b", rest):
                issues.append({"level": "error", "section": "item", "id": name,
                               "need": o,
                               "msg": "ifgroup was removed; use repeated "
                                      "`if` tokens"})
            conds = scenefile.option_conditions(rest)
            if len(conds) > scenefile.MAX_CONDITIONS:
                issues.append({"level": "error", "section": "item", "id": name,
                               "need": o,
                               "msg": f"{len(conds)} conditions (max "
                                      f"{scenefile.MAX_CONDITIONS})"})
            for _kind, cname in conds:
                if cname not in given:
                    issues.append({"level": "error", "section": "item",
                                   "id": name, "need": o,
                                   "msg": f"condition '{cname}' is not a "
                                          "declared or set flag/item"})
            folded = scenefile.filter_system_conditions(conds, fit_system)
            if folded is None:
                continue
            need, clear = _cond_sets(folded)
            pick = re.search(r"\bpick\s+(\S+)", rest)
            pick_name = pick.group(1) if pick else None
            if pick_name:
                clear.add(pick_name)
            fit_entries.append((1, need, clear,
                                ic.group(1) if ic else None, pick_name))
        if not zx_popup:
            fixed = 1 if carry > 0 else 0
            fixed += 1
            total = _max_visible_rows(fit_entries, scene_bits,
                                      item_names=item_names, carry=carry) + fixed
            available = 21 - band_lines
            if total > available:
                issues.append({
                    "level": "warn", "section": "item", "id": name,
                    "msg": f"worst-case description + entries = {total} rows "
                           f"> {available} with art_rows={band_lines}; extra "
                           "rows are not shown. Enable Pop-up options or "
                           "shorten a line/option."})
        if name not in used and name not in g.get("items", []):
            issues.append({"level": "warn", "section": "item", "id": name,
                           "msg": f"item '{name}' has a section but is never "
                                  "picked or used"})

    # `# Game songs:` declared ids back assets/music/<id>.pt3. The `music:` default and
    # every scene override must name a declared song or the reserved on/off.
    songs = list(g.get("songs", []))
    seen_songs = set()
    for name in songs:
        if name.lower() in SONG_TOKENS:
            issues.append({"level": "error", "section": "song", "id": name,
                           "msg": f"'{name}' is reserved; pick another song id"})
        if not _valid_song_id(name):
            issues.append({"level": "error", "section": "song", "id": name,
                           "msg": "song id must be letters, digits, _ or -"})
        if name.lower() in seen_songs:
            issues.append({"level": "error", "section": "song", "id": name,
                           "msg": "duplicate song id"})
        seen_songs.add(name.lower())
        path = song_path(slug, name) if slug else None
        if path and not os.path.exists(path):
            issues.append({"level": "warn", "section": "song", "id": name,
                           "msg": f"no module yet ({os.path.basename(path)})"})

    def check_music(tok, section, sid):
        t = str(tok or "").strip()
        if not t or t.lower() in SONG_TOKENS:
            return
        if t not in songs:
            issues.append({"level": "error", "section": section, "id": sid,
                           "msg": f"music '{t}' is not a declared song"})

    if slug:
        check_music(g.get("music"), "game", "")

    # Conversion settings (dither scheme, colour match, source palette and
    # colour adjustments) accept named/range values; an unrecognised one
    # silently reverts at build time, so flag it rather than let the author
    # think it took effect. Each art may override the game's values.
    _conv_issues(g, g, "game", "", issues, False)
    for a in arts:
        _conv_issues(a, g, "art", a["id"], issues, True)

    # The ZX `art_rows:` option sets the art band height in 8px rows; a
    # NIRVANA+ tile is 16px = 2 rows, so it must be an even 8..16. An odd or
    # out-of-range value still builds (scenefile.art_lines clamps it) but
    # changes the band silently.
    raw_lines = g.get("art_lines", scenefile.ART_LINES_DEFAULT)
    try:
        raw_lines = int(raw_lines)
    except (TypeError, ValueError):
        raw_lines = None
    if raw_lines is None or raw_lines < scenefile.ART_LINES_MIN \
            or raw_lines > scenefile.ART_LINES_MAX or raw_lines % 2:
        issues.append({"level": "warn", "section": "game", "id": "art_rows",
                       "msg": f"art_rows must be an even "
                              f"{scenefile.ART_LINES_MIN}.."
                              f"{scenefile.ART_LINES_MAX}; using "
                              f"{scenefile.art_lines(g)}"})

    # `text_ink:`/`highlight_ink:` colour the body and every selection;
    # selectable words always use highlight_ink, while inventory items use
    # text_ink until selected. `text_bg:` sets the text/paper background.
    # `word_sel_ink:` is a legacy alias for highlight_ink. An unknown name
    # silently falls back to the default, so report it.
    for key, default in (
            ("text_ink", scenefile.DEFAULT_TEXT_INK),
            ("highlight_ink", scenefile.DEFAULT_HIGHLIGHT_INK),
            ("text_bg", scenefile.DEFAULT_TEXT_BG),
            ("word_sel_ink", scenefile.DEFAULT_WORD_SEL_INK)):
        val = str(g.get(key) or "").strip().lower()
        if val and val not in scenefile.WORD_INKS:
            issues.append({"level": "warn", "section": "game", "id": key,
                           "msg": f"unknown colour '{val}'; using "
                                  f"{default}"})

    # The ZX `## zx title_ink:` option takes the same colour tokens plus the
    # `text` default (inherit the body colour). An unknown token silently
    # falls back to the text colour, so report it.
    for tgt in (zx_target, next_target):
        if tgt is None or tgt.id not in selected_systems:
            continue
        raw_title = (g.get("extras") or {}).get(f"{tgt.id}_title_ink")
        val = str(raw_title or "").strip().lower()
        if val and val != scenefile.TITLE_INK_INHERIT \
                and val not in scenefile.WORD_INKS:
            issues.append({"level": "warn", "section": "game",
                           "id": "title_ink", "target": tgt.id,
                           "msg": f"unknown title colour '{val}'; using the "
                                  "text colour"})

    # `password:` drives the boot screen shown before the first scene. The
    # engine types it on the ZX keyboard and compares ASCII, so it must be a
    # short printable token; without a title the screen would be unlabelled.
    raw_pw = str(g.get("password") or "").strip()
    if raw_pw:
        if any(ord(c) < 33 or ord(c) > 126 for c in raw_pw):
            issues.append({"level": "error", "section": "game",
                           "id": "password",
                           "msg": "password must be printable ASCII with no "
                                  "spaces"})
        elif len(raw_pw) > 16:
            issues.append({"level": "error", "section": "game",
                           "id": "password",
                           "msg": "password is longer than 16 characters"})
        if not (g.get("title") or "").strip():
            issues.append({"level": "warn", "section": "game",
                           "id": "password",
                           "msg": "password set but no game title to show "
                                  "on the boot screen"})
    # `password_label:` is the boot screen's prompt line; printable text only,
    # because the engine prints it into the 64-column text band (the accent
    # mapping in scenefile.text_printable applies, as in every printed field).
    raw_pl = str(g.get("password_label") or "").strip()
    if raw_pl:
        if not scenefile.text_printable(raw_pl):
            issues.append({"level": "error", "section": "game",
                           "id": "password_label",
                           "msg": "must be printable text (no control "
                                  "characters)"})
        elif len(raw_pl) > 62:
            issues.append({"level": "error", "section": "game",
                           "id": "password_label",
                           "msg": f"{len(raw_pl)} columns; the text band is 62 "
                                  "wide"})
        if not raw_pw:
            issues.append({"level": "warn", "section": "game",
                           "id": "password_label",
                           "msg": "password label set but no password to show "
                                  "it (the boot screen is not used)"})

    # `popup_hint:` is the dismiss prompt at the bottom of an option's `msg`
    # popup. Printable text only, and it has no effect until some option uses a
    # message.
    raw_ph = str(g.get("popup_hint") or "").strip()
    if raw_ph:
        if not scenefile.text_printable(raw_ph):
            issues.append({"level": "error", "section": "game",
                           "id": "popup_hint",
                           "msg": "must be printable text (no control "
                                  "characters)"})
        elif len(raw_ph) > 62:
            issues.append({"level": "error", "section": "game",
                           "id": "popup_hint",
                           "msg": f"{len(raw_ph)} columns; the text band is 62 "
                                  "wide"})
        uses_msg = any(
            scenefile.split_option_msg(o)[1]
            for s in scenes for o in s.get("opts") or [])
        uses_msg = uses_msg or any(
            scenefile.split_option_msg(o)[1]
            for m in item_meta.values() for o in m.get("opts") or [])
        if not uses_msg:
            issues.append({"level": "warn", "section": "game",
                           "id": "popup_hint",
                           "msg": "popup hint set but no option uses msg "
                                  "(nothing shows it)"})

    # `carry:` caps the held items; a cap below the starting inventory would
    # instantly hide pickups, so warn about it.
    carry = int(g.get("carry", 0) or 0)
    if carry < 0:
        issues.append({"level": "error", "section": "game", "id": "carry",
                       "msg": "carry must be zero (unlimited) or positive"})
    elif carry and carry < len(g.get("start", [])):
        issues.append({"level": "warn", "section": "game", "id": "carry",
                       "msg": f"carry {carry} is below the "
                              f"{len(g['start'])} starting item(s)"})

    # `inventory_*` strings are the lines the per-item inventory screen prints.
    # The engine prints them into the 64-column text band, so they must be
    # printable text (the accent mapping in scenefile.text_printable applies).
    has_desc = any([str(x).strip() for x in (m.get("desc") or [])]
                   for m in item_meta.values())
    have_inv = bool(carry) or has_desc
    inv_keys = ("inventory_drop", "inventory_back")
    for key in inv_keys:
        val = str(g.get(key) or "").strip()
        if not val:
            continue
        if not scenefile.text_printable(val):
            issues.append({"level": "error", "section": "game", "id": key,
                           "msg": "must be printable text (no control "
                                  "characters)"})
        elif len(val) > 62:
            issues.append({"level": "error", "section": "game", "id": key,
                           "msg": f"{len(val)} columns; the text band is 62 "
                                  "wide"})
    if any((g.get(k) or "").strip() for k in inv_keys) and not have_inv:
        issues.append({"level": "warn", "section": "game",
                       "id": "inventory_drop",
                       "msg": "inventory strings have no effect without "
                              "carry: or item descriptions (held items are not "
                              "listed in the menu)"})

    for dup in {x for x in ref_ids if ref_ids.count(x) > 1}:
        issues.append({"level": "error", "section": "ref", "id": dup,
                       "msg": "duplicate reference id"})
    for r in refs:
        if not scenefile.valid_ref_id(r["id"]):
            issues.append({"level": "error", "section": "ref", "id": r["id"],
                           "msg": "reference id must be letters, digits, - or _ "
                                  "(it names the image folder)"})
        if not (r.get("prompt") or "").strip():
            issues.append({"level": "warn", "section": "ref", "id": r["id"],
                           "msg": "empty reference prompt"})
        img = scenefile.resolve_ref_image(ref_root, r) if ref_root else None
        if img is None:
            issues.append({"level": "warn", "section": "ref", "id": r["id"],
                           "msg": "no reference image yet"})
        elif not os.path.exists(img):
            issues.append({"level": "warn", "section": "ref", "id": r["id"],
                           "need": "image",
                           "msg": f"image '{scenefile.ref_image_name(r)}' "
                                  "not found in the reference folder"})

    for a in arts:
        if not (a.get("prompt") or "").strip():
            issues.append({"level": "warn", "section": "art", "id": a["id"],
                           "msg": "empty art prompt"})
        for name in a.get("refs") or []:
            if not scenefile.valid_ref_id(name):
                issues.append({"level": "error", "section": "art",
                               "id": a["id"], "need": "refs",
                               "msg": f"invalid reference id '{name}'"})
            elif name not in ref_ids:
                issues.append({"level": "error", "section": "art",
                               "id": a["id"], "need": "refs",
                               "msg": f"unknown reference image '{name}'"})
            else:
                r = next(x for x in refs if x["id"] == name)
                if not scenefile.resolve_ref_image(ref_root, r):
                    issues.append({"level": "warn", "section": "art",
                                   "id": a["id"], "need": "refs",
                                   "msg": f"reference '{name}' has no image "
                                          "yet"})
        if a.get("crop") is not None:
            ok = (isinstance(a["crop"], (list, tuple)) and len(a["crop"]) == 4)
            if ok:
                try:
                    cx, cy, cw, ch = (float(t) for t in a["crop"])
                    ok = (0 <= cx <= 100 and 0 <= cy <= 100
                          and cw > 0 and ch > 0
                          and cx + cw <= 100.5 and cy + ch <= 100.5)
                except (TypeError, ValueError):
                    ok = False
            if not ok:
                issues.append({"level": "error", "section": "art", "id": a["id"],
                               "need": "crop",
                               "msg": "crop must be x y w h (percent of the "
                                      "source, 0..100 and inside it)"})
        w, h = scenefile.dimensions(a, g)
        if w % 16 or h % 16 or w < 64 or h < 64:
            issues.append({"level": "warn", "section": "art", "id": a["id"],
                           "msg": f"unusual size {w}x{h}; the image model "
                                  "wants multiples of 16, at least 64"})
        img = scenefile.resolve_art_image(art_root, a, gen_dir) if art_root \
            else None
        if img is None:
            issues.append({"level": "warn", "section": "art", "id": a["id"],
                           "msg": "no generated image yet"})
        elif not os.path.exists(img):
            issues.append({"level": "warn", "section": "art", "id": a["id"],
                           "need": "image",
                           "msg": f"image '{scenefile.art_image_name(a)}' "
                                  "not found in the art folder"})

    for s in scenes:
        sid = s["id"]
        if not s.get("art"):
            issues.append({"level": "error", "section": "scene", "id": sid,
                           "msg": "missing art:"})
        elif s["art"] not in art_ids:
            issues.append({"level": "error", "section": "scene", "id": sid,
                           "msg": f"unknown art '{s['art']}'"})
        if s["id"] not in reachable:
            issues.append({"level": "warn", "section": "scene", "id": sid,
                           "msg": "unreachable from the first scene"})
        if len(s["text"]) > 8:
            issues.append({"level": "error", "section": "scene", "id": sid,
                           "msg": "more than 8 text lines"})
        nwords = 0
        fit_entries = []
        for wi, t in enumerate(s["text"]):
            rendered, conds = scenefile.split_text_line(t)
            if len(conds) > scenefile.MAX_CONDITIONS:
                issues.append({"level": "error", "section": "scene", "id": sid,
                               "need": t,
                               "msg": f"more than {scenefile.MAX_CONDITIONS} "
                                      "conditions on a text line"})
            for _kind, cname in conds:
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", cname):
                    issues.append({"level": "error", "section": "scene",
                                   "id": sid, "need": t,
                                   "msg": f"text condition '{cname}' must be "
                                          "letters, digits or _"})
                elif cname not in given:
                    issues.append({"level": "error", "section": "scene", "id": sid,
                                   "need": t,
                                   "msg": f"text condition '{cname}' is not a "
                                          "declared or set flag/item"})
            # A `{{word}}`/`{{word|flag}}` marker is not displayed; its flag
            # must be a usable name, and the whole word must stay on a wrapped
            # row to remain selectable.
            clean, words = scenefile.parse_words(rendered)
            for w in words:
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", w["flag"]):
                    issues.append({"level": "error", "section": "scene", "id": sid,
                                   "need": t,
                                   "msg": f"selectable word flag '{w['flag']}' "
                                          "must be letters, digits or _"})
            for w in _crossed_words(rendered, TEXT_COLS):
                issues.append({"level": "warn", "section": "scene", "id": sid,
                               "need": t,
                               "msg": f"selectable word '{w}' crosses a "
                                      "wrapped line and will not be fully "
                                      "selectable"})
            for w in words:
                flag = w["flag"]
                reveals = [ri for ri, raw in enumerate(s["text"])
                           if any(k == "if" and n == flag
                                  for k, n in
                                  scenefile.split_text_line(raw)[1])]
                if reveals and (wi + 1 not in reveals):
                    issues.append({"level": "warn", "section": "scene",
                                   "id": sid, "need": t,
                                   "msg": f"text revealed by selectable word "
                                          f"'{w['word']}' is not directly "
                                          f"below its line; move the "
                                          f"`-> if {flag}` line up"})
            nwords += len(words)
            folded = scenefile.filter_system_conditions(conds, fit_system)
            if folded is None:
                continue
            need, clear = _cond_sets(folded)
            fit_entries.append(
                (scenefile.text_rows(clean, TEXT_COLS), need, clear,
                 None, None))
        if nwords > 8:
            issues.append({"level": "error", "section": "scene", "id": sid,
                           "msg": f"{nwords} selectable words (max 8)"})
        if len(s.get("title", "")) > TEXT_COLS:
            issues.append({"level": "warn", "section": "scene", "id": sid,
                           "msg": f"title >{TEXT_COLS} cols; it will run off the screen"})
        if len(s["opts"]) > 6:
            issues.append({"level": "error", "section": "scene", "id": sid,
                           "msg": f"{len(s['opts'])} options (max 6)"})
        check_music(s.get("music"), "scene", sid)
        for o in s["opts"]:
            core, popup = scenefile.split_option_msg(o)
            om = scenefile._OPT_RE.match(core)
            if not om:
                issues.append({"level": "error", "section": "scene", "id": sid,
                               "need": o, "msg": f"bad option: {o}"})
                continue
            label, target = om.group(1), om.group(2)
            if popup:
                if not scenefile.text_printable(popup):
                    issues.append({"level": "error", "section": "scene",
                                   "id": sid, "need": o,
                                   "msg": "popup message must be printable "
                                          "text (no control characters)"})
                if "{{" in popup:
                    issues.append({"level": "warn", "section": "scene",
                                   "id": sid, "need": o,
                                   "msg": "selectable words are not parsed "
                                          "in a popup message"})
            if "{{" in label:
                issues.append({"level": "warn", "section": "scene", "id": sid,
                               "need": o,
                               "msg": "selectable words are only parsed in "
                                      "text: lines; {{...}} in an option label "
                                      "shows literally"})
            if len(label) > OPT_COLS:
                issues.append({"level": "warn", "section": "scene", "id": sid,
                               "need": o,
                               "msg": f"option label >{OPT_COLS} cols: {label[:20]}..."})
            if target != "-" and target not in scene_ids:
                issues.append({"level": "error", "section": "scene", "id": sid,
                               "need": o,
                               "msg": f"option targets missing scene '{target}'"})
            if re.search(r"\binscene\s+\S+", om.group(3)):
                issues.append({"level": "error", "section": "scene", "id": sid,
                               "need": o,
                               "msg": "inscene is only valid on an # Items "
                                      "option"})
            if re.search(r"\bifgroup\b", om.group(3)):
                issues.append({"level": "error", "section": "scene", "id": sid,
                               "need": o,
                               "msg": "ifgroup was removed; use repeated "
                                      "`if` tokens"})
            conds = scenefile.option_conditions(om.group(3))
            if len(conds) > scenefile.MAX_CONDITIONS:
                issues.append({"level": "error", "section": "scene", "id": sid,
                               "need": o,
                               "msg": f"{len(conds)} conditions (max "
                                      f"{scenefile.MAX_CONDITIONS})"})
            for _kind, cname in conds:
                if cname not in given:
                    issues.append({"level": "error", "section": "scene",
                                   "id": sid, "need": o,
                                   "msg": f"condition '{cname}' is not a "
                                          "declared or set flag/item"})
            folded = scenefile.filter_system_conditions(conds, fit_system)
            if folded is None:
                continue
            need, clear = _cond_sets(folded)
            pick = re.search(r"\bpick\s+(\S+)", om.group(3))
            pick_name = pick.group(1) if pick else None
            if pick_name:
                clear.add(pick_name)
            fit_entries.append((1, need, clear, None, pick_name))
        if not zx_popup:
            budget = _max_visible_rows(fit_entries, item_names=item_names,
                                       carry=carry)
            band = 22 - band_lines
            if budget > band:
                issues.append({"level": "warn", "section": "scene", "id": sid,
                               "msg": f"worst-case wrapped text + options = "
                                      f"{budget} > {band} rows with "
                                      f"art_rows={band_lines}; extra rows are "
                                      "not shown. Enable Pop-up options or "
                                      "shorten a line/option."})
    issues.extend(targets.selection_issues(doc))
    return issues



class _ValidationFailed(ValueError):
    """A game.md write rejected by validation; carries the structured issues.

    ``str()`` stays the friendly newline list, while the raw editor reads
    ``issues`` to underline the offending lines.
    """

    def __init__(self, issues):
        self.issues = issues
        errors = [i for i in issues if i.get("level") == "error"]
        detail = "\n".join(
            f"- {i['section']} {i.get('id', '')}: {i['msg']}" for i in errors)
        super().__init__("validation failed:\n" + detail)



def _annotate_lines(issues, text):
    """Attach a 1-based ``line`` to each issue so the editor can mark it.

    ``text`` is the verbatim game.md the parse ran on. A scene/art issue points
    at its offending field (e.g. the scene's ``art:`` line) or, failing that, its
    heading; a flag/item/song issue points at its declaration. The client clamps
    anything that cannot be found, so a best-effort line is fine.
    """
    lines = text.splitlines()

    def heading(section, sid):
        in_section = False
        for i, ln in enumerate(lines):
            sec = scenefile._top_heading(ln)
            if sec is not None:
                in_section = sec == section
                continue
            ident = scenefile._entry_heading(ln)
            if ident is not None:
                if in_section and ident == sid:
                    return i
                continue
            if ln.startswith("# "):
                words = ln.split(None, 3)
                if len(words) > 2 and words[1] == section \
                        and words[2].split()[0] == sid:
                    return i
        return -1

    def field_within(head, key):
        """First ``key`` line after heading ``head`` and before the next one."""
        for i in range(head + 1, len(lines)):
            if lines[i].startswith(("# ", "## ")):
                break
            if lines[i].strip().startswith(key):
                return i
        return -1

    def declared(key, sid):
        for i, ln in enumerate(lines):
            if not ln.startswith(key):
                continue
            if sid in re.split(r"[\s,]+", ln[len(key):]):
                return i
        return None

    def key_line(key):
        for i, ln in enumerate(lines):
            if ln.startswith(key + ":"):
                return i
        return -1

    def first(*candidates):
        for c in candidates:
            if c is not None and c >= 0:
                return c
        return -1

    for it in issues:
        section, sid = it.get("section"), str(it.get("id") or "")
        # An option/text issue carries the exact source text (minus the leading
        # `opt:` / indent) so it points at its own line, not the scene's art:.
        # The parser joins wrapped option continuations with a space, so match
        # on the whole normalised line rather than a substring.
        line = -1
        if it.get("need"):
            target = " ".join(it["need"].split())
            for i, ln in enumerate(lines):
                body = ln.strip()
                if body.startswith("opt:"):
                    body = body[4:].strip()
                if " ".join(body.split()) == target:
                    line = i
                    break
        if line < 0 and section in ("scene", "art", "ref") and sid:
            head = heading(section, sid)
            key = "art:" if section == "scene" else "prompt:"
            if section == "ref" and it.get("need") == "image":
                key = "image:"
            elif section == "art" and it.get("need") in ART_FIELD_NEEDS:
                key = it["need"] + ":"
            line = first(field_within(head, key) if head >= 0 else -1, head)
        elif line < 0 and section == "item" and sid:
            head = heading("item", sid)
            line = first(field_within(head, "desc:") if head >= 0 else -1, head)
        elif line < 0 and section == "game" and sid:
            line = first(declared("flags:", sid), declared("items:", sid),
                         declared("songs:", sid), key_line(sid))
        elif line < 0 and section == "song" and sid:
            head = heading("song", sid)
            line = first(field_within(head, "prompt:") if head >= 0 else -1,
                         head, declared("songs:", sid))
        elif line < 0 and section == "game" and it.get("target"):
            line = heading("system", it["target"])
        if line < 0:
            line = next((i for i, ln in enumerate(lines)
                         if ln.strip() in ("# game", "# Game")), 0)
        it["line"] = line + 1
        it.pop("need", None)     # internal locator; not part of the API



def _valid_song_id(song_id):
    return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", str(song_id or "")))



def _valid_art_id(art_id):
    """An art id is a bare token; it also names the art's image folder."""
    return bool(re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", str(art_id or "")))


# PT3 modules carry one of two canonical title headers: Vortex Tracker writes
# "Vortex Tracker II ..." and spectrumizer (ProTracker emitter) writes
# "ProTracker 3.x ...". The Z80 player ignores the text and reads the version
# char at offset 0x0D plus the tables by offset, so both are valid.
PT3_MAGIC = (b"Vortex Tracker", b"ProTracker 3.")



__all__ = [
    '_conv_issues',
    '_validate',
    '_ValidationFailed',
    '_annotate_lines',
    '_valid_song_id',
    '_valid_art_id',
]
