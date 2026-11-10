"""Game folders, project JSON, art/reference candidates and saves."""

from __future__ import annotations

import hashlib

from server import *  # noqa: F401,F403 - shared state and helpers

from editor_validation import *


class _SaveConflict(ValueError):
    """Raised when game.md changed on disk since the editor loaded it."""

    def __init__(self, message, revision=""):
        super().__init__(message)
        self.revision = revision


def _game_md_revision(path):
    """Content hash of game.md, used to spot an out-of-band edit on save."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return ""


def _check_revision(path, expected):
    """Refuse to save when ``path`` no longer matches the loaded revision.

    ``expected=None`` skips the check (internal writers that re-read the file
    themselves). An empty string means the file did not exist when loaded.
    """
    current = _game_md_revision(path)
    if expected is not None and current != expected:
        raise _SaveConflict(
            "game.md was modified on disk since you loaded it", current)
    return current


def _game_or_error(slug):
    """Resolve a slug to an existing game, raising KeyError otherwise."""
    game = gamestore.resolve(slug)
    if game is None:
        raise KeyError(f"no such game: {slug!r}")
    return game



def _game_md_path(slug):
    game = _game_or_error(slug)
    return os.path.join(game["dir"], "game.md")



def _art_root(game_dir):
    return os.path.join(game_dir, scenefile.ART_ROOT)



def _art_legacy_dir(game_dir):
    return os.path.join(game_dir, scenefile.ART_LEGACY_ROOT)



def _art_image_path(game, art):
    """Resolved source PNG for an art (assets/art/<id>/ with legacy fallback)."""
    return scenefile.resolve_art_image(_art_root(game["dir"]), art,
                                       _art_legacy_dir(game["dir"]))



def _ref_root(game_dir):
    return os.path.join(game_dir, scenefile.REF_ROOT)



def _ref_image_path(game, ref):
    """Resolved source PNG for a reference image."""
    return scenefile.resolve_ref_image(_ref_root(game["dir"]), ref)



def _new_art_filename(prefix):
    """A fresh candidate basename, e.g. ``gen-1730000000000.png``.

    The epoch-millisecond suffix keeps every generation/upload a separate file
    (nothing is overwritten), and sorting the folder by mtime picks the newest.
    """
    return f"{prefix}-{int(time.time() * 1000)}.png"



def _set_art_image(slug, art_id, filename):
    """Persist ``image: <filename>`` for one art, atomically, keeping a .bak.

    Called after a generate/upload writes a new candidate, so a headless run
    (or an immediate build) picks the fresh image. The editor flushes pending
    edits before it asks for a render, so this cannot clobber unsaved state.
    """
    game = _game_or_error(slug)
    md = os.path.join(game["dir"], "game.md")
    if not os.path.exists(md):
        return
    doc = scenefile.parse(md)
    art = _find_art(doc, art_id)
    if art is None:
        return
    art["image"] = filename
    text = scenefile.serialize(doc)
    tmp = md + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    shutil.copyfile(md, md + ".bak")
    with _lock:
        os.replace(tmp, md)



def _set_ref_image(slug, ref_id, filename):
    """Persist ``image: <filename>`` for one reference, atomically."""
    if not scenefile.valid_ref_id(ref_id):
        return
    game = _game_or_error(slug)
    md = os.path.join(game["dir"], "game.md")
    if not os.path.exists(md):
        return
    doc = scenefile.parse(md)
    ref = _find_ref(doc, ref_id)
    if ref is None:
        return
    ref["image"] = filename
    text = scenefile.serialize(doc)
    tmp = md + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    shutil.copyfile(md, md + ".bak")
    with _lock:
        os.replace(tmp, md)



def _write_game_doc(slug, doc):
    """Write a parsed project atomically, keeping the previous game.md as .bak."""
    game = _game_or_error(slug)
    md = os.path.join(game["dir"], "game.md")
    text = scenefile.serialize(doc)
    tmp = md + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    if os.path.exists(md):
        shutil.copyfile(md, md + ".bak")
    with _lock:
        os.replace(tmp, md)



def _delete_candidate_image(root, ident, filename):
    """Delete one candidate PNG and its generation sidecar from a folder."""
    if not scenefile.valid_art_image(filename):
        raise ValueError(f"invalid image name {filename!r}")
    folder = os.path.join(root, ident)
    path = os.path.join(folder, filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"image '{filename}' not found")
    with _lock:
        os.remove(path)
        sidecar = os.path.join(folder,
                               os.path.splitext(filename)[0] + "_result.json")
        if os.path.isfile(sidecar):
            try:
                os.remove(sidecar)
            except OSError:
                pass



def delete_art_image(slug, art_id, filename):
    """Delete one art candidate, repointing ``image:`` if it was active."""
    if not _valid_art_id(art_id):
        raise ValueError(f"invalid art id {art_id!r}")
    game = _game_or_error(slug)
    md = os.path.join(game["dir"], "game.md")
    doc = scenefile.parse(md) if os.path.exists(md) else None
    art = _find_art(doc, art_id) if doc else None
    explicit = scenefile.art_image_name(art) if art else None
    resolved = _art_image_path(game, art) if art else None
    active = explicit or (os.path.basename(resolved) if resolved else None)
    root = _art_root(game["dir"])
    _delete_candidate_image(root, art_id, filename)
    remaining = scenefile.list_art_images(root, art_id)
    newest = os.path.basename(remaining[0]) if remaining else None
    if art is not None and active == filename:
        if newest is None:
            art.pop("image", None)
        else:
            art["image"] = newest
        _write_game_doc(slug, doc)
        image = newest
    else:
        image = explicit or newest
    return {"art": art_id, "deleted": filename, "image": image,
            "revision": _game_md_revision(md)}



def delete_ref_image(slug, ref_id, filename):
    """Delete one reference candidate, repointing ``image:`` if it was active."""
    if not scenefile.valid_ref_id(ref_id):
        raise ValueError(f"invalid reference id {ref_id!r}")
    game = _game_or_error(slug)
    md = os.path.join(game["dir"], "game.md")
    doc = scenefile.parse(md) if os.path.exists(md) else None
    ref = _find_ref(doc, ref_id) if doc else None
    explicit = scenefile.ref_image_name(ref) if ref else None
    resolved = _ref_image_path(game, ref) if ref else None
    active = explicit or (os.path.basename(resolved) if resolved else None)
    root = _ref_root(game["dir"])
    _delete_candidate_image(root, ref_id, filename)
    remaining = scenefile.list_ref_images(root, ref_id)
    newest = os.path.basename(remaining[0]) if remaining else None
    if ref is not None and active == filename:
        if newest is None:
            ref.pop("image", None)
        else:
            ref["image"] = newest
        _write_game_doc(slug, doc)
        image = newest
    else:
        image = explicit or newest
    return {"ref": ref_id, "deleted": filename, "image": image,
            "revision": _game_md_revision(md)}


# Fields an art issue can be annotated onto: the art's `refs:`/`image:`/`crop:`
# or one of its own conversion-override lines.
ART_FIELD_NEEDS = ("refs", "image", "crop") + tuple(scenefile.CONV_KEYS)



def active_generation(slug=None):
    """The newest generation job still queued or running, or None.

    The editor keeps the Stop button and progress poller alive only while it
    holds a client-side job id, which a page reload loses. Re-deriving the
    in-flight job server-side lets a reloaded page reattach to it. ``slug``
    restricts this to the selected game's jobs so another game's art progress
    is never shown.
    """
    with _lock:
        running = [j for j in _jobs.values()
                   if j.get("status") in ("queued", "running")
                   and (slug is None or j.get("game") == slug)]
    if not running:
        return None
    return max(running, key=lambda j: j.get("started", 0))



def project_json(slug):
    game = _game_or_error(slug)
    md = os.path.join(game["dir"], "game.md")
    doc = scenefile.parse(md)
    doc["system_flags"] = sorted(scenefile.SYSTEM_FLAGS)
    try:
        flag_map, item_list, order = scenefile.assign_flags(
            doc["scenes"], doc["game"].get("start", []),
            doc["game"].get("flags", []),
            scenefile.declared_items(doc["game"], doc.get("item_meta")),
            item_names=scenefile.item_display_names(doc["game"],
                                                    doc.get("item_meta")),
            item_meta=doc.get("item_meta"))
    except ValueError as e:
        flag_map, item_list, order = {}, [], []
        doc["flag_error"] = str(e)
    doc["flags"] = [{"id": flag_map[n], "name": n,
                     "item": n in item_list} for n in order]
    doc["issues"] = _validate(doc, game["slug"])
    doc["game_slug"] = game["slug"]
    doc["revision"] = _game_md_revision(md)
    try:
        rel_md = os.path.relpath(md, ROOT)
    except ValueError:          # different drive (Windows): use the absolute path
        rel_md = md
    doc["paths"] = {"game_md": rel_md,
                    "game_dir": game["dir"],
                    "stable_diffusion_url": STABLE_DIFFUSION_URL}
    doc["ai"] = {"image": IMAGE_ENABLED}
    doc["active_job"] = active_generation(game["slug"])
    return doc



def _migrate_art_files(old_doc, doc, art_root, gen_dir):
    """Carry an art's image folder over when an art id is renamed in the editor.

    The editor keeps art order, so pairing removed ids with added ids in order
    maps a rename (optionally with deletes/reorders) onto the existing
    assets/art/<id>/ folder without losing the images, and copies the old
    ``image:`` pointer to the renamed art. Flat legacy files under assets/gen
    are moved too.
    """
    old_ids = [a["id"] for a in old_doc["arts"]]
    new_ids = [a["id"] for a in doc["arts"]]
    old_set, new_set = set(old_ids), set(new_ids)
    removed = [i for i in old_ids if i not in new_set]
    added = [i for i in new_ids if i not in old_set]
    for old_id, new_id in zip(removed, added):
        src = os.path.join(art_root, old_id)
        dst = os.path.join(art_root, new_id)
        if os.path.isdir(src) and not os.path.exists(dst):
            try:
                shutil.move(src, dst)
            except OSError:
                pass
        old_art = next((a for a in old_doc["arts"] if a["id"] == old_id), None)
        new_art = next((a for a in doc["arts"] if a["id"] == new_id), None)
        if old_art and new_art and not new_art.get("image"):
            new_art["image"] = old_art.get("image")
        for suffix in (".png", "_result.json"):
            src = os.path.join(gen_dir, f"art_{old_id}{suffix}")
            dst = os.path.join(gen_dir, f"art_{new_id}{suffix}")
            if os.path.exists(src) and not os.path.exists(dst):
                os.replace(src, dst)



def _migrate_ref_files(old_doc, doc, ref_root):
    """Carry a reference's image folder over when its id is renamed.

    Renames are paired by position, exactly like art ids; every art whose
    ``refs:`` names the old id is repointed to the new one.
    """
    old_refs = old_doc.get("refs") or []
    new_refs = doc.get("refs") or []
    old_ids = [r["id"] for r in old_refs]
    new_ids = [r["id"] for r in new_refs]
    old_set, new_set = set(old_ids), set(new_ids)
    removed = [i for i in old_ids if i not in new_set]
    added = [i for i in new_ids if i not in old_set]
    renames = dict(zip(removed, added))
    for old_id, new_id in renames.items():
        src = os.path.join(ref_root, old_id)
        dst = os.path.join(ref_root, new_id)
        if os.path.isdir(src) and not os.path.exists(dst):
            try:
                shutil.move(src, dst)
            except OSError:
                pass
        old_ref = next((r for r in old_refs if r["id"] == old_id), None)
        new_ref = next((r for r in new_refs if r["id"] == new_id), None)
        if old_ref and new_ref and not new_ref.get("image"):
            new_ref["image"] = old_ref.get("image")
    if renames:
        for a in doc.get("arts") or []:
            a["refs"] = [renames.get(n, n) for n in (a.get("refs") or [])]



def _migrate_song_files(old_doc, doc, mdir):
    """Carry modules over when a song id is renamed (mirrors art migration)."""
    old_ids = [s for s in old_doc["game"].get("songs", [])]
    new_ids = [s for s in doc["game"].get("songs", [])]
    old_set, new_set = set(old_ids), set(new_ids)
    removed = [i for i in old_ids if i not in new_set]
    added = [i for i in new_ids if i not in old_set]
    for old_id, new_id in zip(removed, added):
        for ext in (".pt3", ".mid"):
            src = os.path.join(mdir, f"{old_id}{ext}")
            dst = os.path.join(mdir, f"{new_id}{ext}")
            if os.path.exists(src) and not os.path.exists(dst):
                os.replace(src, dst)



def _write_game_md(slug, content, expected_revision=None):
    """Validate and atomically write game.md (kept as .bak). Returns warn count.

    On an error the write is refused and ``_ValidationFailed`` (a ValueError)
    is raised carrying the issues with their source lines, so the editor can
    mark them. ``str(exc)`` remains the friendly newline list.

    ``expected_revision`` (the hash the editor loaded) refuses the write with
    ``_SaveConflict`` when another user/process changed game.md in the meantime;
    internal callers leave it ``None`` because they re-read the file first.
    """
    doc = scenefile.parse(content)
    issues = _validate(doc, slug)
    _annotate_lines(issues, content)
    errors = [i for i in issues if i.get("level") == "error"]
    if errors:
        raise _ValidationFailed(issues)
    path = _game_md_path(slug)
    with _lock:
        _check_revision(path, expected_revision)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        if os.path.exists(path):
            old_doc = scenefile.parse(path)
            mdir = os.path.join(gamestore.resolve(slug)["dir"], "assets", "music")
            _migrate_song_files(old_doc, doc, mdir)
            shutil.copyfile(path, path + ".bak")
        os.replace(tmp, path)
    return len([i for i in issues if i.get("level") == "warn"])



def lint_game_md(slug, content):
    """Validate game.md text without writing; returns issues with line numbers.

    Used by the Source tab's live checker so an error is underlined as soon as
    it is typed, before a Save is attempted. An unparseable file yields a single
    file-level issue rather than raising.
    """
    _game_or_error(slug)
    try:
        doc = scenefile.parse(content)
    except Exception as e:      # noqa: BLE001 - a bad line can break the parse
        return [{"level": "error", "section": "file", "id": "", "line": 1,
                 "msg": f"could not parse game.md: {e}"}]
    issues = _validate(doc, slug)
    _annotate_lines(issues, content)
    return issues



def save_project(doc, slug, expected_revision=None):
    from editor_images import _drop_art_overrides
    """Write <game>/game.md atomically, keeping a .bak of the previous file.

    ``expected_revision`` refuses the save with ``_SaveConflict`` when another
    user/process edited game.md after the editor loaded it.
    """
    game = _game_or_error(slug)
    md = os.path.join(game["dir"], "game.md")
    gen_dir = os.path.join(game["dir"], "assets", "gen")
    mdir = os.path.join(game["dir"], "assets", "music")
    ref_root = _ref_root(game["dir"])
    _drop_art_overrides(doc)
    with _lock:
        _check_revision(md, expected_revision)
        if os.path.exists(md):
            # Migrate renamed-art/reference folders (and copy the old `image:`
            # pointers) before serialising, so they are written in this save.
            old_doc = scenefile.parse(md)
            _migrate_art_files(old_doc, doc, _art_root(game["dir"]), gen_dir)
            _migrate_ref_files(old_doc, doc, ref_root)
            _migrate_song_files(old_doc, doc, mdir)
            shutil.copyfile(md, md + ".bak")
        text = scenefile.serialize(doc)
        tmp = md + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, md)
    return text


# --------------------------------------------------------------- generation

def _find_art(doc, art_id):
    for a in doc["arts"]:
        if a["id"] == art_id:
            return a
    return None



def _find_ref(doc, ref_id):
    for r in doc.get("refs") or []:
        if r["id"] == ref_id:
            return r
    return None


# ---------------------------------------------------------------- music
# Each game's songs live in games/<slug>/assets/music/<id>.pt3 and are packed
# as paged data by the build. A module must fit the resident player buffer
# (SONG_WS; the ZX buffer lives in lower RAM) or the engine would be overwritten.
SONG_WS = 4158
SONG_MAX_BYTES = 4 * 1024 * 1024
SONG_MIDI_MAX_BYTES = 4 * 1024 * 1024
SONG_TOKENS = ("on", "off")
SONG_RENDER_TIMEOUT = 300
CONVERT_TIMEOUT = 120
CONVERT_STYLES = ("faithful", "chiptune")
CONVERT_BASSES = ("normal", "envelope", "envelope-tone")
CONVERT_FLAGS = ("auto_transpose", "vibrato")



__all__ = [
    '_game_or_error',
    '_game_md_path',
    '_write_game_md',
    '_game_md_revision',
    '_SaveConflict',
    'lint_game_md',
    '_art_root',
    '_art_legacy_dir',
    '_art_image_path',
    '_ref_root',
    '_ref_image_path',
    '_new_art_filename',
    '_set_art_image',
    '_set_ref_image',
    '_write_game_doc',
    '_delete_candidate_image',
    'delete_art_image',
    'delete_ref_image',
    'active_generation',
    'project_json',
    '_migrate_art_files',
    '_migrate_ref_files',
    '_migrate_song_files',
    'save_project',
    '_find_art',
    '_find_ref',
]
