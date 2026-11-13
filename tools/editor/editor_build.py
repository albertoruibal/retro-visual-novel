"""Build jobs for the selected systems."""

from __future__ import annotations

from server import *  # noqa: F401,F403 - shared state and helpers

from editor_games import *

def _build_env_for(slug):
    env = dict(os.environ)
    game = gamestore.resolve(slug)
    if game:
        # The server may have inherited the desktop app's startup tab list.
        # It is stale once a folder is opened at runtime, and gamestore gives
        # RVN_GAMES precedence over RVN_GAME, so drop it: the child build
        # only needs the game being built.
        env["RVN_GAME"] = game["dir"]
        env.pop("RVN_GAMES", None)
        env.pop("ZXAD_GAMES", None)
        env.pop("ZXAD_GAME", None)
    env["Z88DK"] = z88dk_effective_path()
    env["CC65"] = cc65_effective_path()
    return env



def _selected_build_ids(doc, requested=None):
    """Selected targets plus the always-built web emulator player.

    An explicit ``requested`` list builds exactly those targets (the editor's
    "Build selected" action); only the full build appends the web export.
    """
    req = [str(t).strip().lower() for t in (requested or [])
           if str(t).strip()]
    if req:
        return targets.ordered_targets(req)
    ids = targets.ordered_targets(targets.selected_targets(doc))
    if ids and "web" not in ids:
        ids = targets.ordered_targets(ids + ["web"])
    return ids


def _run_build(build_id, slug, requested=None):
    """Build every target selected in game.md (or an explicit override).

    Each target runs as its own tools/build.py child so one platform failing
    does not stop the others; the combined log keeps the ``[target]`` prefixes
    emitted by the dispatcher, and ``targets`` holds per-platform status. The
    web player is always built last: ticking Web adds the novel, otherwise the
    export refreshes only the native emulator entries.
    """
    _builds[build_id]["status"] = "running"
    log = []
    results = {}
    try:
        env = _build_env_for(slug)
        # Each child is one target; the orchestrator appends the web step, so
        # a child must not auto-export the player after its own build.
        env["RVN_WEB_AUTO"] = "0"
        game = _game_or_error(slug)
        doc = scenefile.parse(os.path.join(game["dir"], "game.md"))
        ids = _selected_build_ids(doc, requested)
        _builds[build_id]["targets"] = {t: {"status": "queued", "log": []}
                                        for t in ids}
        if not ids:
            raise ValueError("no build targets selected")
        for target_id in ids:
            target = targets.get_target(target_id)
            banner = targets.build_separator(
                target_id, target.label if target else "")
            if log:
                log.append("")
            log.append(banner)
            if target is None:
                msg = f"unknown build target {target_id!r}"
                results[target_id] = {"status": "error", "error": msg,
                                      "returncode": 1, "log": [banner, msg]}
                _builds[build_id]["targets"][target_id] = results[target_id]
                log.append(f"[{target_id}] {msg}")
                continue
            started = time.monotonic()
            proc = subprocess.Popen(
                [sys.executable, "-u", os.path.join(ROOT, "tools", "build.py"),
                 "build", slug, target_id], cwd=ROOT, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            tlog = [banner]
            for line in proc.stdout:
                text = line.rstrip("\n")
                tlog.append(text)
                log.append(text)
                _builds[build_id]["log"] = log[-400:]
                _builds[build_id]["targets"][target_id] = {
                    "status": "running", "log": tlog[-160:]}
            proc.wait()
            seconds = round(time.monotonic() - started, 1)
            st = "done" if proc.returncode == 0 else "error"
            results[target_id] = {"status": st, "returncode": proc.returncode,
                                  "log": tlog[-160:], "seconds": seconds}
            _builds[build_id]["targets"][target_id] = results[target_id]
        statuses = [r["status"] for r in results.values()]
        if statuses and all(x == "done" for x in statuses):
            overall = "done"
        elif any(x == "done" for x in statuses):
            overall = "partial"
        else:
            overall = "error"
        _builds[build_id].update(status=overall,
                                 returncode=0 if overall == "done" else 1,
                                 targets=results)
    except Exception as e:      # noqa: BLE001
        _builds[build_id].update(status="error", error=str(e))
    finally:
        _builds[build_id]["finished"] = time.time()



def start_build(slug, requested=None):
    game = _game_or_error(slug)
    doc = scenefile.parse(os.path.join(game["dir"], "game.md"))
    ids = _selected_build_ids(doc, requested)
    cc65_targets = ("c64", "nes", "oric")
    if any(t not in cc65_targets and t != "web" for t in ids):
        missing = z88dk_missing_tools()
        if missing:
            raise ValueError(
                "z88dk is incomplete — missing %s in %s. Set the toolchain "
                "folder in Settings (Build toolchain)." % (
                    ", ".join(missing),
                    os.path.join(z88dk_effective_path(), "bin")))
    if any(t in cc65_targets for t in ids):
        missing = cc65_missing_tools()
        if missing:
            raise ValueError(
                "cc65 is incomplete — missing %s. Install cc65 or set its "
                "folder in Settings (Build toolchain)." % ", ".join(missing))
    build_id = f"build-{slug}-{int(time.time()*1000)}"
    _builds[build_id] = {"id": build_id, "game": slug, "status": "queued",
                         "log": [], "targets": {}}
    threading.Thread(target=_run_build, args=(build_id, slug, requested),
                     daemon=True).start()
    return build_id


# ------------------------------------------------------------------- preview

__all__ = [
    '_build_env_for',
    '_run_build',
    'start_build',
]
