#!/usr/bin/env python3
"""Generate adventure art and reference images with the local SD server.

The server runs Qwen-Image 2.1 (leejet/stable-diffusion.cpp) with its
A1111-compatible API. Each ``## <art-id>`` block under ``# Art`` of a game's ``game.md`` is
rendered by posting ``"<game prompt>, <art prompt>"`` to
``/sdapi/v1/txt2img``; the first returned image is written as a *new*
``assets/art/<id>/gen-<epoch>.png`` (earlier candidates are kept) and the raw
job response beside it as ``.../gen-<epoch>_result.json``. The new file becomes
the art's ``image:`` in ``game.md``. A ``prompt:`` may be written over several
4-space-indented lines; they keep their line breaks (see scenefile), just as
the editor saves them.

Each ``## <ref-id>`` under ``# References`` is generated separately from its own prompt into
``assets/refs/<id>/`` and is never packed into the game. An art's ``refs:``
line sends those reference images to the model via the SD API ``extra_images``
field (stable-diffusion.cpp's reference images), so a boat, van or character
keeps the same design across scenes.

The URL defaults to http://localhost:7860 and can be overridden with
STABLE_DIFFUSION_URL, e.g. when the container is only reachable on the docker
bridge:

    STABLE_DIFFUSION_URL=http://172.20.0.3:7860 \
        python3 tools/gen_images.py --game <slug> dock estufa

With no art ids every art in that game is regenerated. A full run renders
every ``# References`` first, then each art conditions on the fresh images; when
specific art ids are given, only the references those arts name are rendered
(a shared reference once per run). ``--refs`` renders every reference; repeat
``--ref <id>`` for specific ones. ``--refine`` (and ``--refine-refs``) instead
runs img2img from the current image at 2x, preserving the composition while
adding detail:

    python3 tools/gen_images.py --game <slug> --refs
    python3 tools/gen_images.py --game <slug> --ref boat --ref van
    python3 tools/gen_images.py --game <slug> --refine [art ids]
    python3 tools/gen_images.py --game <slug> --refine-refs

The optional ``# Game`` ``negative_prompt:``, ``hires:``, ``hires_steps:`` and
``hires_denoise:`` settings are applied to renders (and the refine strength is
``refine_denoise:``).

``--game`` accepts a slug or a game directory and defaults to the first game
under ``games/``.
"""
import base64
import json
import os
import shutil
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gamestore
import scenefile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = os.environ.get("STABLE_DIFFUSION_URL", "http://localhost:7860").rstrip("/")


def _post(payload, name, timeout):
    req = urllib.request.Request(
        f"{URL}/sdapi/v1/txt2img",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    sys.stderr.write(f"[{name}] POST {URL}/sdapi/v1/txt2img ...\n")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _candidate(dirpath):
    os.makedirs(dirpath, exist_ok=True)
    while True:                       # a fresh candidate per run; keep the rest
        fname = f"gen-{int(time.time() * 1000)}.png"
        if not os.path.exists(os.path.join(dirpath, fname)):
            return fname
        time.sleep(0.001)


def _write(dirpath, res):
    b64 = res["images"][0].split(",", 1)[-1]
    png = base64.b64decode(b64)
    fname = _candidate(dirpath)
    open(os.path.join(dirpath, fname), "wb").write(png)
    json.dump(res, open(os.path.join(dirpath, fname[:-4] + "_result.json"), "w"))
    return fname, png


def _quality_params(game):
    """Negative prompt + optional high-res pass from the # Game section."""
    out = {}
    neg = str(game.get("negative_prompt") or "").strip()
    if neg:
        out["negative_prompt"] = neg
    hires = scenefile.hires_options(game)
    if hires["scale"] > 1.0:
        out.update({"enable_hr": True, "hr_scale": hires["scale"],
                    "hr_upscaler": "Lanczos", "hr_steps": hires["steps"],
                    "denoising_strength": hires["denoise"]})
    return out


def _ref_extra_images(game_dir, names, refs_meta):
    by_id = {r["id"]: r for r in refs_meta}
    out = []
    for name in names or []:
        ref = by_id.get(name)
        if ref is None:
            raise ValueError(f"unknown reference image '{name}'")
        path = scenefile.resolve_ref_image(
            os.path.join(game_dir, scenefile.REF_ROOT), ref)
        if not path or not os.path.exists(path):
            raise ValueError(f"reference image '{name}' has no image yet")
        with open(path, "rb") as f:
            out.append("data:image/png;base64,"
                       + base64.b64encode(f.read()).decode("ascii"))
    return out


def generate(art, game, art_root, refs_meta=(), timeout=900):
    prompt = scenefile.compose_prompt(game.get("prompt", ""), art["prompt"])
    width, height = scenefile.dimensions(art, game)
    payload = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "steps": int(art.get("steps",
                              game.get("steps", scenefile.STEPS_DEFAULT))),
        "cfg_scale": float(art.get("cfg", game.get("cfg", 6.0))),
        "sample_method": "euler",
        "seed": int(art.get("seed", game.get("seed", 42))),
    }
    payload.update(_quality_params(game))
    refs = list(art.get("refs") or [])
    if refs:
        game_dir = os.path.dirname(os.path.dirname(art_root))
        payload["extra_images"] = _ref_extra_images(game_dir, refs, refs_meta)
    name = art["id"]
    res = _post(payload, name, timeout)
    fname, png = _write(os.path.join(art_root, name), res)
    sys.stderr.write(f"[{name}] wrote {os.path.relpath(os.path.join(art_root, name, fname), ROOT)}"
                     f" ({len(png)} bytes)\n")
    return fname, png


def generate_ref(ref, game, ref_root, timeout=900):
    prompt = scenefile.compose_prompt(game.get("prompt", ""), ref["prompt"])
    width, height = scenefile.dimensions(ref, game)
    payload = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "steps": int(ref.get("steps",
                              game.get("steps", scenefile.STEPS_DEFAULT))),
        "cfg_scale": float(ref.get("cfg", game.get("cfg", 6.0))),
        "sample_method": "euler",
        "seed": int(ref.get("seed", game.get("seed", 42))),
    }
    payload.update(_quality_params(game))
    name = ref["id"]
    res = _post(payload, name, timeout)
    fname, png = _write(os.path.join(ref_root, name), res)
    sys.stderr.write(f"[{name}] wrote {os.path.relpath(os.path.join(ref_root, name, fname), ROOT)}"
                     f" ({len(png)} bytes)\n")
    return fname, png


def generate_art_refs(arts, refs, game, ref_root, done=None):
    """Render every reference the selected arts name, before the arts.

    A reference shared by several arts is generated once per run; its new
    filename is recorded on the parsed ref so ``generate`` sends the fresh
    image as ``extra_images``. ``done`` lets a full run mark references it has
    already regenerated so they are not rendered twice.
    """
    by_id = {r["id"]: r for r in refs}
    done = set() if done is None else done
    for art in arts:
        for name in art.get("refs") or []:
            if name in done:
                continue
            ref = by_id.get(name)
            if ref is None:
                raise ValueError(f"unknown reference image '{name}'")
            fname, _ = generate_ref(ref, game, ref_root)
            ref["image"] = fname
            done.add(name)


def _refine_target(game):
    w, h = scenefile.dimensions(game, game)
    scale = max(2.0, scenefile.hires_scale(game))
    return int(round(w * scale)), int(round(h * scale))


def refine(entry, game, src, out_dir, timeout=2400):
    """Refine an existing art/reference at 2x with img2img (keeps the scene)."""
    from PIL import Image
    import io
    if not src or not os.path.exists(src):
        raise ValueError(f"{entry['id']}: no image to refine")
    tw, th = _refine_target(game)
    im = Image.open(src).convert("RGB").resize((tw, th), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    init = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    prompt = scenefile.compose_prompt(game.get("prompt", ""),
                                      entry.get("prompt", ""))
    payload = {
        "steps": int(game.get("steps", scenefile.STEPS_DEFAULT)),
        "cfg_scale": float(game.get("cfg", 6.0)),
        "sample_method": "euler",
        "seed": int(game.get("seed", 42)),
        "denoising_strength": scenefile.refine_denoise(game),
        "init_images": [init],
    }
    neg = str(game.get("negative_prompt") or "").strip()
    if neg:
        payload["negative_prompt"] = neg
    req = urllib.request.Request(
        f"{URL}/sdapi/v1/img2img", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    sys.stderr.write(f"[{entry['id']}] POST {URL}/sdapi/v1/img2img ...\n")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        res = json.load(r)
    fname, png = _write(out_dir, res)
    sys.stderr.write(f"[{entry['id']}] refined {fname} ({len(png)} bytes)\n")
    return fname, png


def main():
    args = sys.argv[1:]
    slug = None
    if "--game" in args:
        i = args.index("--game")
        if i + 1 >= len(args):
            sys.exit("--game needs a slug or directory")
        slug = args[i + 1]
        del args[i:i + 2]
    refine_arts = "--refine" in args
    if refine_arts:
        args.remove("--refine")
    refine_refs = "--refine-refs" in args
    if refine_refs:
        args.remove("--refine-refs")
    want_refs = False
    if "--refs" in args:
        want_refs = True
        args.remove("--refs")
    ref_ids = []
    while "--ref" in args:
        i = args.index("--ref")
        if i + 1 >= len(args):
            sys.exit("--ref needs a reference id")
        ref_ids.append(args[i + 1])
        del args[i:i + 2]
    game = gamestore.resolve(slug)
    if game is None:
        sys.exit(f"no such game: {slug!r} (see 'games/')")
    md = os.path.join(game["dir"], "game.md")
    art_root = os.path.join(game["dir"], scenefile.ART_ROOT)
    ref_root = os.path.join(game["dir"], scenefile.REF_ROOT)

    doc = scenefile.parse(md)
    names = args
    if (refine_arts or refine_refs) and (ref_ids or want_refs):
        sys.exit("--refine/--refine-refs cannot be combined with --ref/--refs")
    if refine_arts or refine_refs:
        arts = doc["arts"]
        if names:
            arts = [a for a in arts if a["id"] in names]
            missing = set(names) - {a["id"] for a in arts}
            if missing:
                sys.exit(f"unknown art id(s): {', '.join(sorted(missing))}")
        elif not refine_arts:
            arts = []
        refs = list(doc.get("refs") or []) if refine_refs else []
        legacy = os.path.join(game["dir"], scenefile.ART_LEGACY_ROOT)
        for ref in refs:
            src = scenefile.resolve_ref_image(ref_root, ref)
            fname, _ = refine(ref, doc["game"], src,
                              os.path.join(ref_root, ref["id"]))
            ref["image"] = fname
        for art in arts:
            src = scenefile.resolve_art_image(art_root, art, legacy)
            fname, _ = refine(art, doc["game"], src,
                              os.path.join(art_root, art["id"]))
            art["image"] = fname
        if not refs and not arts:
            sys.exit(f"no art or reference sections selected in {md}")
        tmp = md + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(scenefile.serialize(doc))
        if os.path.exists(md):
            shutil.copyfile(md, md + ".bak")
        os.replace(tmp, md)
        return
    refs_mode = bool(ref_ids or want_refs)
    if names:
        arts = [a for a in doc["arts"] if a["id"] in names]
        missing = set(names) - {a["id"] for a in arts}
        if missing:
            sys.exit(f"unknown art id(s): {', '.join(sorted(missing))}")
    elif refs_mode:
        arts = []                 # `--ref`/`--refs` selects references only
    else:
        arts = doc["arts"]
    refs = doc.get("refs") or []
    if ref_ids:
        refs = [r for r in refs if r["id"] in ref_ids]
        missing = set(ref_ids) - {r["id"] for r in refs}
        if missing:
            sys.exit(f"unknown reference id(s): {', '.join(sorted(missing))}")
    elif want_refs:
        refs = list(refs)
    else:
        refs = []
    if not arts and not refs:
        sys.exit(f"no art or reference sections selected in {md}")
    for ref in refs:
        fname, _ = generate_ref(ref, doc["game"], ref_root)
        ref["image"] = fname
    if arts:
        done = set()
        if not names and not refs_mode:
            for ref in doc.get("refs") or []:
                fname, _ = generate_ref(ref, doc["game"], ref_root)
                ref["image"] = fname
                done.add(ref["id"])
        generate_art_refs(arts, doc.get("refs") or [], doc["game"], ref_root,
                          done)
    for art in arts:
        fname, _ = generate(art, doc["game"], art_root, doc.get("refs") or [])
        art["image"] = fname
    tmp = md + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(scenefile.serialize(doc))
    if os.path.exists(md):
        shutil.copyfile(md, md + ".bak")
    os.replace(tmp, md)


if __name__ == "__main__":
    main()
