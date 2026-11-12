"""Image generation, refinement, uploads, previews and jobs."""

from __future__ import annotations

from server import *  # noqa: F401,F403 - shared state and helpers

from editor_games import *
from editor_validation import *
import pngmeta

def _drop_art_overrides(doc):
    """Remove every per-art generation parameter.

    Seed/steps/cfg/size/width/height are game-wide (the # Game section) by
    design, so the editor never persists or honours a per-art override. The
    per-art ``crop:`` (scenefile.DEFAULT_CROP) is *not* in PARAM_KEYS and is
    kept, since it is meant to be set per image.
    """
    for a in doc["arts"]:
        for k in scenefile.PARAM_KEYS:
            a.pop(k, None)
    return doc



def _sd_txt2img(prompt, params, timeout=2400):
    payload = dict(params)
    payload["prompt"] = prompt
    req = urllib.request.Request(
        f"{STABLE_DIFFUSION_URL}/sdapi/v1/txt2img",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)



def _sd_img2img(prompt, params, timeout=2400):
    payload = dict(params)
    payload["prompt"] = prompt
    req = urllib.request.Request(
        f"{STABLE_DIFFUSION_URL}/sdapi/v1/img2img",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)



def _quality_params(game):
    """Optional negative prompt + high-res second pass from the # Game section."""
    out = {}
    neg = str((game or {}).get("negative_prompt") or "").strip()
    if neg:
        out["negative_prompt"] = neg
    hires = scenefile.hires_options(game)
    if hires["scale"] > 1.0:
        out.update({
            "enable_hr": True,
            "hr_scale": hires["scale"],
            "hr_upscaler": "Lanczos",
            "hr_steps": hires["steps"],
            "denoising_strength": hires["denoise"],
        })
    return out



class _JobCancelled(Exception):
    """Raised inside a generation worker after the job was asked to stop."""



def _is_cancelled(job_id):
    with _lock:
        return job_id in _interrupts



def _sd_interrupt():
    """Best-effort abort of the SD server's in-flight txt2img pass."""
    try:
        req = urllib.request.Request(
            f"{STABLE_DIFFUSION_URL}/sdapi/v1/interrupt", data=b"",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception:      # noqa: BLE001 - cancellation is best effort
        pass



def cancel_generate(job_id):
    """Ask a generation job to stop and abort the SD server's current pass.

    The image server is single-GPU, so stopping means interrupting whatever
    txt2img call is in flight and preventing a *-all worker from starting the
    next art. Jobs already finished are returned unchanged.
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise KeyError(f"unknown job '{job_id}'")
        if job.get("status") in ("done", "error", "cancelled"):
            return job
        _interrupts.add(job_id)
    _sd_interrupt()
    return job



def _reference_extra_images(game_dir, names, refs_meta):
    """Base64 data URLs for an art's ``refs:``, in author order.

    The SD API maps ``extra_images`` to stable-diffusion.cpp's reference images
    (``ref_images``), so Qwen conditions on the same boat/van/character design.
    A missing reference is a clear error rather than a silent text-only render.
    """
    by_id = {r["id"]: r for r in (refs_meta or [])}
    out = []
    for name in names or []:
        ref = by_id.get(name)
        if ref is None:
            raise ValueError(f"unknown reference image '{name}'")
        path = scenefile.resolve_ref_image(_ref_root(game_dir), ref)
        if not path or not os.path.exists(path):
            raise ValueError(f"reference image '{name}' has no image yet")
        with open(path, "rb") as f:
            out.append("data:image/png;base64,"
                       + base64.b64encode(f.read()).decode("ascii"))
    return out



def _render_art(slug, art_id, art, game, overrides, job_id=None,
                refs_meta=None, refs_done=None):
    """Render one art and write a *new* candidate PNG + sanitised result JSON.

    Each run drops ``gen-<epoch>.png`` (with embedded PNG metadata stripped, and
    a ``_result.json`` without the image payload or model details) into the art's
    folder, leaving earlier candidates in place, then records it as the art's
    ``image:``. Returns (prompt, params, png_len, filename, refs). Shared by the
    single-art and regenerate-all jobs so both build the request and write files
    identically. The art's ``refs:`` are re-rendered first so it conditions on
    fresh reference images; ``refs_done`` lets a regenerate-all run render each
    shared reference once. When ``job_id`` has been cancelled, raises
    ``_JobCancelled`` instead of writing a partial image.
    """
    if job_id is not None and _is_cancelled(job_id):
        raise _JobCancelled()
    merged = dict(art)
    merged.update(overrides or {})
    refs = list(merged.get("refs") or [])
    prompt = scenefile.compose_prompt(game.get("prompt", ""),
                                      merged.get("prompt", ""), refs)
    width, height = scenefile.dimensions(game, game)
    params = {
        "width": width, "height": height,
        "steps": int(game.get("steps", scenefile.STEPS_DEFAULT)),
        "cfg_scale": float(game.get("cfg", 6.0)),
        "sample_method": "euler",
        "seed": int(game.get("seed", 42)),
    }
    params.update(_quality_params(game))
    if refs:
        by_id = {r["id"]: r for r in (refs_meta or [])}
        done = set() if refs_done is None else refs_done
        for name in refs:
            if name in done:
                continue
            ref = by_id.get(name)
            if ref is None:
                raise ValueError(f"unknown reference image '{name}'")
            _, _, _, img = _render_ref(slug, name, ref, game, None, job_id)
            ref["image"] = img
            done.add(name)
        rec = _game_or_error(slug)
        request = dict(params)
        request["extra_images"] = _reference_extra_images(rec["dir"], refs,
                                                          refs_meta)
    else:
        request = params
    try:
        res = _sd_txt2img(prompt, request)
    except Exception:
        # An interrupt can drop the in-flight connection; report it as a
        # cancellation rather than a hard generation error.
        if job_id is not None and _is_cancelled(job_id):
            raise _JobCancelled()
        raise
    if job_id is not None and _is_cancelled(job_id):
        raise _JobCancelled()
    b64 = res["images"][0].split(",", 1)[-1]
    png = pngmeta.strip_png_metadata(base64.b64decode(b64))
    rec = _game_or_error(slug)
    name = _new_art_filename("gen")
    adir = os.path.join(_art_root(rec["dir"]), art_id)
    os.makedirs(adir, exist_ok=True)
    with _lock:
        open(os.path.join(adir, name), "wb").write(png)
        json.dump(pngmeta.sanitize_result(res),
                  open(os.path.join(adir, name[:-4] + "_result.json"), "w"))
    _set_art_image(slug, art_id, name)
    return prompt, params, len(png), name, refs



def _render_ref(slug, ref_id, ref, game, overrides, job_id=None):
    """Render one ``# References`` image from its own prompt (no art references).

    References are generated separately from their own ``# References`` section and
    stored in ``assets/refs/<id>/``; they are never packed into the game.
    """
    if job_id is not None and _is_cancelled(job_id):
        raise _JobCancelled()
    merged = dict(ref)
    merged.update(overrides or {})
    prompt = scenefile.compose_prompt(game.get("prompt", ""),
                                      merged.get("prompt", ""))
    width, height = scenefile.dimensions(merged, game)
    params = {
        "width": width, "height": height,
        "steps": int(merged.get("steps") or
                     game.get("steps", scenefile.STEPS_DEFAULT)),
        "cfg_scale": float(merged.get("cfg") or game.get("cfg", 6.0)),
        "sample_method": "euler",
        "seed": int(merged.get("seed") if merged.get("seed") is not None
                    else game.get("seed", 42)),
    }
    params.update(_quality_params(game))
    try:
        res = _sd_txt2img(prompt, params)
    except Exception:
        if job_id is not None and _is_cancelled(job_id):
            raise _JobCancelled()
        raise
    if job_id is not None and _is_cancelled(job_id):
        raise _JobCancelled()
    b64 = res["images"][0].split(",", 1)[-1]
    png = pngmeta.strip_png_metadata(base64.b64decode(b64))
    rec = _game_or_error(slug)
    name = _new_art_filename("gen")
    rdir = os.path.join(_ref_root(rec["dir"]), ref_id)
    os.makedirs(rdir, exist_ok=True)
    with _lock:
        open(os.path.join(rdir, name), "wb").write(png)
        json.dump(pngmeta.sanitize_result(res),
                  open(os.path.join(rdir, name[:-4] + "_result.json"), "w"))
    _set_ref_image(slug, ref_id, name)
    return prompt, params, len(png), name



def _run_generate(job_id, slug, art_id, art, game, overrides, refs_meta=None):
    _jobs[job_id]["status"] = "running"
    try:
        prompt, params, n, name, refs = _render_art(
            slug, art_id, art, game, overrides, job_id, refs_meta)
        _jobs[job_id].update(prompt=prompt, params=params, image=name,
                             refs=refs)
        _jobs[job_id].update(status="done", bytes=n, finished=time.time())
    except _JobCancelled:
        _jobs[job_id].update(status="cancelled", finished=time.time())
    except Exception as e:      # noqa: BLE001 - surfaced to the UI
        _jobs[job_id].update(status="error", error=str(e),
                             finished=time.time())
    finally:
        with _lock:
            _interrupts.discard(job_id)



def start_generate(slug, art_id, overrides):
    if not IMAGE_ENABLED:
        raise ValueError("image generation is disabled (set STABLE_DIFFUSION_URL)")
    game = _game_or_error(slug)
    doc = project_json(slug)
    art = _find_art(doc, art_id)
    if art is None:
        raise KeyError(f"unknown art '{art_id}'")
    job_id = f"{game['slug']}-{art_id}-{int(time.time()*1000)}"
    _jobs[job_id] = {"id": job_id, "game": game["slug"], "kind": "art",
                     "art": art_id, "status": "queued",
                     "started": time.time()}
    t = threading.Thread(target=_run_generate,
                         args=(job_id, game["slug"], art_id, art, doc["game"],
                               overrides, doc.get("refs") or []),
                         daemon=True)
    t.start()
    return job_id



def start_generate_ref(slug, ref_id, overrides):
    """Queue a reference-image render (its own prompt, no art references)."""
    if not IMAGE_ENABLED:
        raise ValueError("image generation is disabled (set STABLE_DIFFUSION_URL)")
    game = _game_or_error(slug)
    if not scenefile.valid_ref_id(ref_id):
        raise ValueError(f"invalid reference id {ref_id!r}")
    doc = project_json(slug)
    ref = _find_ref(doc, ref_id)
    if ref is None:
        raise KeyError(f"unknown reference '{ref_id}'")
    job_id = f"{game['slug']}-ref-{ref_id}-{int(time.time()*1000)}"
    _jobs[job_id] = {"id": job_id, "game": game["slug"], "kind": "ref",
                     "ref": ref_id, "status": "queued",
                     "started": time.time()}
    t = threading.Thread(target=_run_generate_ref,
                         args=(job_id, game["slug"], ref_id, ref,
                               doc["game"], overrides),
                         daemon=True)
    t.start()
    return job_id



def _run_generate_ref(job_id, slug, ref_id, ref, game, overrides):
    _jobs[job_id]["status"] = "running"
    try:
        prompt, params, n, name = _render_ref(slug, ref_id, ref, game,
                                              overrides, job_id)
        _jobs[job_id].update(prompt=prompt, params=params, image=name)
        _jobs[job_id].update(status="done", bytes=n, finished=time.time())
    except _JobCancelled:
        _jobs[job_id].update(status="cancelled", finished=time.time())
    except Exception as e:      # noqa: BLE001 - surfaced to the UI
        _jobs[job_id].update(status="error", error=str(e),
                             finished=time.time())
    finally:
        with _lock:
            _interrupts.discard(job_id)



def _refine_target(game):
    """The output size of the 2x refine pass (at least 2x the base size)."""
    w, h = scenefile.dimensions(game, game)
    scale = max(2.0, scenefile.hires_scale(game))
    return int(round(w * scale)), int(round(h * scale))



def _refine_image(slug, kind, ident, entry, game, overrides=None, job_id=None):
    """Refine an existing art/reference at 2x with img2img.

    The selected image is enlarged with Lanczos and re-rendered with the same
    prompt at a modest denoise, which adds detail while keeping the composition
    and the objects the author already chose. A *new* ``ref-<epoch>.png`` is
    written and becomes the entry's ``image:``.
    """
    if job_id is not None and _is_cancelled(job_id):
        raise _JobCancelled()
    rec = _game_or_error(slug)
    src = _art_image_path(rec, entry) if kind == "art" \
        else _ref_image_path(rec, entry)
    if not src or not os.path.exists(src):
        raise ValueError(f"{kind} '{ident}' has no image to refine")
    from PIL import Image
    import io
    tw, th = _refine_target(game)
    im = Image.open(src).convert("RGB").resize((tw, th), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    init = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    merged = dict(entry)
    merged.update(overrides or {})
    prompt = scenefile.compose_prompt(game.get("prompt", ""),
                                      merged.get("prompt", ""))
    params = {
        "steps": int(game.get("steps", scenefile.STEPS_DEFAULT)),
        "cfg_scale": float(game.get("cfg", 6.0)),
        "sample_method": "euler",
        "seed": int(game.get("seed", 42)),
        "denoising_strength": scenefile.refine_denoise(game),
        "init_images": [init],
    }
    neg = str(game.get("negative_prompt") or "").strip()
    if neg:
        params["negative_prompt"] = neg
    if job_id is not None and _is_cancelled(job_id):
        raise _JobCancelled()
    try:
        res = _sd_img2img(prompt, params)
    except Exception:
        if job_id is not None and _is_cancelled(job_id):
            raise _JobCancelled()
        raise
    if job_id is not None and _is_cancelled(job_id):
        raise _JobCancelled()
    png = pngmeta.strip_png_metadata(
        base64.b64decode(res["images"][0].split(",", 1)[-1]))
    name = _new_art_filename("ref")
    out_dir = (os.path.join(_art_root(rec["dir"]), ident) if kind == "art"
               else os.path.join(_ref_root(rec["dir"]), ident))
    os.makedirs(out_dir, exist_ok=True)
    with _lock:
        open(os.path.join(out_dir, name), "wb").write(png)
        json.dump(pngmeta.sanitize_result(res),
                  open(os.path.join(out_dir, name[:-4] + "_result.json"), "w"))
    if kind == "art":
        _set_art_image(slug, ident, name)
    else:
        _set_ref_image(slug, ident, name)
    summary = dict(params)
    summary.pop("init_images", None)
    return prompt, summary, len(png), name



def start_refine_art(slug, art_id, overrides=None):
    if not IMAGE_ENABLED:
        raise ValueError("image generation is disabled (set STABLE_DIFFUSION_URL)")
    game = _game_or_error(slug)
    doc = project_json(slug)
    art = _find_art(doc, art_id)
    if art is None:
        raise KeyError(f"unknown art '{art_id}'")
    job_id = f"{game['slug']}-refine-{art_id}-{int(time.time()*1000)}"
    _jobs[job_id] = {"id": job_id, "game": game["slug"], "kind": "refine",
                     "art": art_id, "status": "queued", "started": time.time()}
    threading.Thread(target=_run_refine,
                     args=(job_id, game["slug"], "art", art_id, art,
                           doc["game"], overrides), daemon=True).start()
    return job_id



def start_refine_ref(slug, ref_id, overrides=None):
    if not IMAGE_ENABLED:
        raise ValueError("image generation is disabled (set STABLE_DIFFUSION_URL)")
    game = _game_or_error(slug)
    doc = project_json(slug)
    ref = _find_ref(doc, ref_id)
    if ref is None:
        raise KeyError(f"unknown reference '{ref_id}'")
    job_id = f"{game['slug']}-refine-ref-{ref_id}-{int(time.time()*1000)}"
    _jobs[job_id] = {"id": job_id, "game": game["slug"], "kind": "refine",
                     "ref": ref_id, "status": "queued", "started": time.time()}
    threading.Thread(target=_run_refine,
                     args=(job_id, game["slug"], "ref", ref_id, ref,
                           doc["game"], overrides), daemon=True).start()
    return job_id



def _run_refine(job_id, slug, kind, ident, entry, game, overrides):
    _jobs[job_id]["status"] = "running"
    try:
        prompt, params, n, name = _refine_image(slug, kind, ident, entry,
                                                game, overrides, job_id)
        _jobs[job_id].update(prompt=prompt, params=params, image=name)
        _jobs[job_id].update(status="done", bytes=n, finished=time.time())
    except _JobCancelled:
        _jobs[job_id].update(status="cancelled", finished=time.time())
    except Exception as e:      # noqa: BLE001 - surfaced to the UI
        _jobs[job_id].update(status="error", error=str(e),
                             finished=time.time())
    finally:
        with _lock:
            _interrupts.discard(job_id)



def _run_generate_all(job_id, slug, missing=False):
    """Render every reference, then every (or every missing) art, in order.

    Both a full and a ``missing`` run re-render every declared ``# References``
    first, so the arts condition on fresh reference images; with ``missing``
    set, arts that already have an image are then skipped. The SD server is
    single-GPU, so requests are serial. A failure on one entry is recorded in
    ``errors`` and the run continues; the job ends "done" once at least one art
    rendered (or, with no arts, one reference), else "error". A stop request
    ends it "cancelled" before the next entry starts.
    """
    _jobs[job_id]["status"] = "running"
    try:
        doc = project_json(slug)
        game_rec = _game_or_error(slug)
        arts = doc["arts"]
        if missing:
            arts = [a for a in arts
                    if _art_image_path(game_rec, a) is None]
        game = doc["game"]
        refs = list(doc.get("refs") or [])
        total = len(refs) + len(arts)
        refs_done = set()
        done = 0
        art_ok = 0
        _jobs[job_id].update(total=total, done=0, errors=[])
        for ref in refs:
            if _is_cancelled(job_id):
                _jobs[job_id].update(status="cancelled", current=None,
                                     finished=time.time())
                return
            ref_id = ref["id"]
            _jobs[job_id].update(current=ref_id, index=done + 1)
            try:
                _, _, n, img = _render_ref(slug, ref_id, ref, game, None,
                                           job_id)
                ref["image"] = img
                refs_done.add(ref_id)
                _jobs[job_id]["bytes"] = n
                _jobs[job_id]["image"] = img
            except _JobCancelled:
                _jobs[job_id].update(status="cancelled", current=None,
                                     finished=time.time())
                return
            except Exception as e:      # noqa: BLE001 - keep going
                _jobs[job_id]["errors"].append({"ref": ref_id,
                                                "error": str(e)})
            done += 1
            _jobs[job_id]["done"] = done
        for art in arts:
            if _is_cancelled(job_id):
                _jobs[job_id].update(status="cancelled", current=None,
                                     finished=time.time())
                return
            art_id = art["id"]
            _jobs[job_id].update(current=art_id, index=done + 1)
            try:
                _, _, n, name, _refs = _render_art(
                    slug, art_id, art, game, None, job_id, refs, refs_done)
                _jobs[job_id]["bytes"] = n
                _jobs[job_id]["image"] = name
                art_ok += 1
            except _JobCancelled:
                _jobs[job_id].update(status="cancelled", current=None,
                                     finished=time.time())
                return
            except Exception as e:      # noqa: BLE001 - keep going
                _jobs[job_id]["errors"].append({"art": art_id, "error": str(e)})
            done += 1
            _jobs[job_id]["done"] = done
        failed = (art_ok == 0) if arts else (not refs_done)
        _jobs[job_id].update(status="error" if failed else "done",
                             current=None, finished=time.time())
    except Exception as e:      # noqa: BLE001 - surfaced to the UI
        _jobs[job_id].update(status="error", error=str(e), finished=time.time())
    finally:
        with _lock:
            _interrupts.discard(job_id)


MAX_UPLOAD_BYTES = 16 * 1024 * 1024



def upload_art(slug, art_id, data):
    """Store a user-supplied image as a new candidate for an art.

    ``data`` is a base64 string or a ``data:image/...;base64,`` URL (what the
    browser's FileReader produces). The upload is normalised to RGB and scaled
    to the game's ``width``/``height`` (512x256 by default) so it drives the
    same bicolor/classic pipeline the generated art does. It is written as a
    fresh ``up-<epoch>.png`` and becomes the art's ``image:``; earlier
    candidates are kept.
    """
    game = _game_or_error(slug)
    doc = project_json(slug)
    art = _find_art(doc, art_id)
    if art is None:
        raise KeyError(f"unknown art '{art_id}'")
    raw = data.split(",", 1)[-1] if data.startswith("data:") else data
    try:
        png = base64.b64decode(raw, validate=True)
    except Exception:
        raise ValueError("upload is not valid base64 image data")
    if not png:
        raise ValueError("empty upload")
    if len(png) > MAX_UPLOAD_BYTES:
        raise ValueError("image too large (max 16 MB)")
    from PIL import Image
    import io
    try:
        im = Image.open(io.BytesIO(png)).convert("RGB")
    except Exception:
        raise ValueError("upload is not a readable image")
    width, height = scenefile.output_dimensions(doc["game"], doc["game"])
    if im.size != (width, height):
        im = im.resize((width, height), Image.LANCZOS)
    name = _new_art_filename("up")
    adir = os.path.join(_art_root(game["dir"]), art_id)
    os.makedirs(adir, exist_ok=True)
    out = os.path.join(adir, name)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    with _lock:
        open(out, "wb").write(pngmeta.strip_png_metadata(buf.getvalue()))
    _set_art_image(slug, art_id, name)
    return {"art": art_id, "image": name, "width": width, "height": height,
            "size": width if width == height else None,
            "bytes": os.path.getsize(out),
            "revision": _game_md_revision(os.path.join(game["dir"], "game.md"))}


REF_MAX_SIDE = 1024



def upload_ref(slug, ref_id, data, kind="up"):
    """Store a user-supplied image as a new candidate for a reference.

    Reference images are not cropped to the art band; they keep their own
    aspect and are only capped to ``REF_MAX_SIDE`` so a huge upload cannot
    bloat the model request. The new file becomes the reference's ``image:``.
    """
    game = _game_or_error(slug)
    if not scenefile.valid_ref_id(ref_id):
        raise ValueError(f"invalid reference id {ref_id!r}")
    doc = project_json(slug)
    ref = _find_ref(doc, ref_id)
    if ref is None:
        raise KeyError(f"unknown reference '{ref_id}'")
    raw = data.split(",", 1)[-1] if data.startswith("data:") else data
    try:
        png = base64.b64decode(raw, validate=True)
    except Exception:
        raise ValueError("upload is not valid base64 image data")
    if not png:
        raise ValueError("empty upload")
    if len(png) > MAX_UPLOAD_BYTES:
        raise ValueError("image too large (max 16 MB)")
    from PIL import Image
    import io
    try:
        im = Image.open(io.BytesIO(png))
        im.load()
    except Exception:
        raise ValueError("upload is not a readable image")
    if max(im.size) > REF_MAX_SIDE:
        scale = REF_MAX_SIDE / max(im.size)
        im = im.resize((max(1, round(im.width * scale)),
                        max(1, round(im.height * scale))), Image.LANCZOS)
    if "A" in im.getbands():
        im = im.convert("RGBA")
    else:
        im = im.convert("RGB")
    width, height = im.size
    name = _new_art_filename(kind if kind in ("up", "gen") else "up")
    rdir = os.path.join(_ref_root(game["dir"]), ref_id)
    os.makedirs(rdir, exist_ok=True)
    out = os.path.join(rdir, name)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    with _lock:
        open(out, "wb").write(pngmeta.strip_png_metadata(buf.getvalue()))
    _set_ref_image(slug, ref_id, name)
    return {"ref": ref_id, "image": name, "width": width, "height": height,
            "bytes": os.path.getsize(out),
            "revision": _game_md_revision(os.path.join(game["dir"], "game.md"))}



def start_generate_all(slug, missing=False):
    """Queue a run over every art, or only the arts lacking any image.

    ``missing`` lets the editor fill in only the not-yet-rendered art without
    redoing work; the worker re-checks existence so an image written between the
    queue and the run is not regenerated.
    """
    if not IMAGE_ENABLED:
        raise ValueError("image generation is disabled (set STABLE_DIFFUSION_URL)")
    game = _game_or_error(slug)
    doc = project_json(slug)
    if missing:
        pending = [a for a in doc["arts"] if _art_image_path(game, a) is None]
        if not pending:
            raise ValueError("no missing art to generate")
    elif not doc["arts"]:
        raise ValueError("no art sections to regenerate")
    job_id = f"{game['slug']}-all-{int(time.time()*1000)}"
    _jobs[job_id] = {"id": job_id, "game": game["slug"], "kind": "all",
                     "status": "queued", "started": time.time()}
    threading.Thread(target=_run_generate_all,
                     args=(job_id, game["slug"], missing),
                     daemon=True).start()
    return job_id


# --------------------------------------------------------------------- build

def _png_bytes(img):
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()



def _preview_overrides(qs):
    """Pull live conversion values from the preview query string.

    Recognises the ``match``/``palette``/``palette_colors`` names, the four
    colour adjustments and a preview-only ``dither``. The Art tab passes the
    art's unsaved control values and the Systems tab's live dither so the
    previews track them before a save; the crop keeps its own ``?crop=``
    parameter. The dither value is still a system setting, never an art one.
    """
    out = {}
    for key in ("dither", "margin", "match", "palette", "palette_colors") \
            + scenefile.ADJUST_KEYS:
        v = qs.get(key, [None])[0]
        if v is not None and v != "":
            out[key] = v
    return out



def _preview_context(slug, art_id, crop, file, lines, overrides,
                     target_id=None):
    """Resolve (src, conv, doc, art) for an Art-tab preview query."""
    game = _game_or_error(slug)
    doc = scenefile.parse(os.path.join(game["dir"], "game.md"))
    art = _find_art(doc, art_id)
    if file is not None and scenefile.valid_art_image(file):
        src = os.path.join(_art_root(game["dir"]), art_id, file)
    else:
        src = _art_image_path(game, art) if art else None
    if not src or not os.path.exists(src):
        return None, None, doc, art, None
    conv = scenefile.conversion_options(art or {}, doc["game"],
                                        target_id or "zx128")
    if lines is not None:
        try:
            lines = scenefile.art_lines({"art_lines": int(lines)})
        except (TypeError, ValueError):
            lines = None
    if lines is None:
        target = targets.get_target(target_id or "zx128")
        target_rows = (targets.target_options(doc, target).get("art_rows")
                       if target is not None else None)
        if target_rows is not None:
            lines = scenefile.art_lines({"art_lines": int(target_rows)})
        else:
            lines = scenefile.art_lines(doc["game"])
    if isinstance(crop, str):
        crop = [t for t in crop.replace(",", " ").split()] or None
    if crop is not None:
        try:
            crop = [float(t) for t in crop]
        except (TypeError, ValueError):
            crop = None
        if crop is not None and len(crop) != 4:
            crop = None
    if crop is not None:
        conv["crop"] = crop
    for key, val in (overrides or {}).items():
        if key in ("palette_colors", "margin"):
            try:
                conv[key] = max(0, int(val))
            except (TypeError, ValueError):
                pass
        elif key in scenefile.ADJUST_KEYS:
            try:
                conv["adjust"][key] = float(val)
            except (TypeError, ValueError):
                pass
        elif key in ("dither", "match", "palette"):
            conv[key] = str(val).strip().lower()
    return src, conv, doc, art, max(1, lines // 2)



def target_art_preview_bytes(slug, art_id, target_id, crop=None, file=None,
                             lines=None, overrides=None, target_rows=None):
    """Return a PNG preview using a target plugin's converter."""
    target = targets.get_target(target_id)
    if target is None or target.preview is None:
        return None
    src, conv, doc, _art, _rows = _preview_context(
        slug, art_id, crop, file, lines, overrides, target.id)
    if not src:
        return None
    options = targets.target_options(doc, target)
    if target_rows is not None:
        option = next((o for o in target.options if o.key == "art_rows"), None)
        if option is not None:
            options["art_rows"] = targets.coerce_option(option, target_rows)
    try:
        return target.preview(src, conv, options, doc.get("game"))
    except Exception:                       # noqa: BLE001 - bad image/settings
        return None



def art_preview_bytes(slug, art_id, mode="nirvana", crop=None, overrides=None,
                      file=None, lines=None):
    """Return a band PNG preview of the art as the Spectrum will show it.

    The band is the source cropped to ``crop`` and scaled to 256 x (8*art_rows)
    (the selected ZX target's band; 256x80 for the default 10). ``lines``
    overrides that height with the Art tab's current (possibly unsaved) value,
    so the previews track the control before a save; it is clamped to the valid
    even 8..16 range. ``crop``
    is ``[x, y, w, h]`` percentages of the source (or a "x,y,w,h" string from
    the ``?crop=`` query); None uses the art's own ``crop:`` setting (itself
    None = the centred band-aspect window). ``file`` names a specific candidate
    in the art's folder to preview (an Art-tab picker thumbnail); None uses the
    art's active ``image:``. ``mode``
    selects the attribute model: ``"nirvana"`` quantises through the NIRVANA+
    bicolor tiles (per-2-line attributes, exactly what the engine draws),
    ``"classic"`` uses standard 8x8 attributes (the blockier non-NIRVANA clash
    look) and ``"bifrost"`` uses Bifrost*'s per-scanline 8x1 attributes (an
    approximation -- Bifrost drives only 20 of the band's 32 columns). It is
    returned at its native size; the UI shows it next to the source
    without distorting either (see ``art.js``).

    The art's conversion settings (colour match, palette and colour
    adjustments) are resolved with ``scenefile.conversion_options`` so the
    preview matches the build, and the dither comes from the ``zx128`` system
    block; ``overrides`` layers the Art tab's unsaved control values (from
    ``_preview_overrides``) on top.
    """
    src, conv, doc, _art, rows = _preview_context(
        slug, art_id, crop, file, lines, overrides, "zx128")
    if not src:
        return None
    from PIL import Image
    im = Image.open(src).convert("RGB")
    margin = conv.get("margin", 0)
    fill = zxart.background_rgb(doc["game"])
    if mode == "classic":
        img = zxart.grid_to_rgb_image(zxart.classic_band(
            im, crop=conv["crop"], rows=rows, adjust=conv["adjust"],
            palette=conv["palette"], palette_colors=conv["palette_colors"],
            margin=margin, fill=fill))
        return _png_bytes(zxart.preview_margin_crop(
            img, margin, zxart.BAND_W, zxart.band_h(rows)))
    if mode == "bifrost":
        img = zxart.grid_to_rgb_image(zxart.bifrost_band(
            im, crop=conv["crop"], rows=rows, adjust=conv["adjust"],
            palette=conv["palette"], palette_colors=conv["palette_colors"],
            margin=margin, fill=fill))
        return _png_bytes(zxart.preview_margin_crop(
            img, margin, zxart.BAND_W, zxart.band_h(rows)))
    grid = zxart.nirvana_band(im, crop=conv["crop"], dither=conv["dither"],
                              rows=rows, match=conv["match"],
                              adjust=conv["adjust"], palette=conv["palette"],
                              palette_colors=conv["palette_colors"],
                              margin=margin, fill=fill)
    _, _, blob = zxart.band_to_art(grid, rows=rows)
    m = list(blob[:zxart.map_len(rows)])
    tiles = [blob[zxart.map_len(rows) + i * 48:zxart.map_len(rows) + (i + 1) * 48]
             for i in range((len(blob) - zxart.map_len(rows)) // 48)]
    img = Image.new("RGB", (zxart.BAND_W, zxart.band_h(rows)))
    px = img.load()
    for cy in range(rows):
        for cx in range(zxart.COLS):
            grid2 = [[0] * 16 for _ in range(16)]
            zxart.tile_to_rgb(tiles[m[cy * zxart.COLS + cx]], grid2)
            for y in range(16):
                for x in range(16):
                    px[cx * 16 + x, cy * 16 + y] = zxart.rgb(grid2[y][x])
    return _png_bytes(zxart.preview_margin_crop(
        img, margin, zxart.BAND_W, zxart.band_h(rows)))


# ------------------------------------------------------------------- emulator

__all__ = [
    '_drop_art_overrides',
    '_sd_txt2img',
    '_sd_img2img',
    '_quality_params',
    '_JobCancelled',
    '_is_cancelled',
    '_sd_interrupt',
    'cancel_generate',
    '_reference_extra_images',
    '_render_art',
    '_render_ref',
    '_run_generate',
    'start_generate',
    'start_generate_ref',
    '_run_generate_ref',
    '_refine_target',
    '_refine_image',
    'start_refine_art',
    'start_refine_ref',
    '_run_refine',
    '_run_generate_all',
    'upload_art',
    'upload_ref',
    'start_generate_all',
    '_png_bytes',
    '_preview_overrides',
    '_preview_context',
    'target_art_preview_bytes',
    'art_preview_bytes',
]
