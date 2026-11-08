"use strict";
// ------------------------------------------------------------------- art
/* An art's crop is a source rectangle `[x, y, w, h]` in percentages of the
 * source (0..100), or null for the default centred band-aspect window. */
function artCropRect(a) {
  const c = a && a.crop;
  if (!Array.isArray(c) || c.length !== 4) return null;
  const r = c.map(Number);
  return r.every(Number.isFinite) ? r : null;
}

/* "x,y,w,h" for the preview query, or "" for the default (centred) window. */
function artCropSpec(a) {
  const r = artCropRect(a);
  return r ? r.map((v) => Math.round(v)).join(",") : "";
}

/* Art-band height in character rows (even 8..16, default 10); mirrors
 * scenefile.art_lines. A NIRVANA+ tile is 16px = 2 rows, so the value is even. */
const ART_LINE_OPTIONS = [8, 10, 12, 14, 16];
const DEFAULT_ART_LINES = 10;
function artLines() {
  const n = P && P.game ? +P.game.art_lines : NaN;
  return ART_LINE_OPTIONS.includes(n) ? n : DEFAULT_ART_LINES;
}
function artBandH() { return 8 * artLines(); }

/* Band aspect (256 x band height) and the centred band-aspect window of a
 * source, in source pixels — the largest band-aspect rectangle that fits (the
 * whole frame for a source that already matches). */
function cropAr() { return 256 / artBandH(); }
function defaultCropRect(natW, natH) {
  const ar = cropAr();
  let w, h;
  if (natW / natH > ar) { h = natH; w = natH * ar; }
  else { w = natW; h = natW / ar; }
  return { x: (natW - w) / 2, y: (natH - h) / 2, w: w, h: h };
}

/* Re-fit a source-pixel crop rectangle to the current band aspect (cropAr()),
 * keeping its centre and width and clamping it to the source. The crop box must
 * always keep the band aspect, so a stored crop whose aspect no longer matches
 * (the art band height changed) is re-fitted rather than left to stretch. */
function fitCropToBand(rect, natW, natH) {
  const ar = cropAr();
  const cx = rect.x + rect.w / 2, cy = rect.y + rect.h / 2;
  let w = Math.min(rect.w, natW), h = w / ar;
  if (h > natH) { h = natH; w = h * ar; }
  const x = Math.max(0, Math.min(cx - w / 2, natW - w));
  const y = Math.max(0, Math.min(cy - h / 2, natH - h));
  return { x: x, y: y, w: w, h: h };
}

/* Selected build systems for Art-tab previews. The Systems tab is the
 * source of truth; ZX is the backward-compatible default. */
const SYSTEM_ORDER = ["zx", "next", "cpc", "msx2", "sms", "gb", "c64", "nes"];
function previewTargets() {
  const list = typeof gameTargets === "function" ? gameTargets() : ["zx"];
  const rank = (id) => {
    const i = SYSTEM_ORDER.indexOf(id);
    return i < 0 ? SYSTEM_ORDER.length : i;
  };
  return list.slice().sort((a, b) => rank(a) - rank(b));
}
function previewTargetMeta(id) {
  return ((TARGETS && TARGETS.targets) || []).find((t) => t.id === id) || null;
}
function previewTargetLabel(id) {
  const m = previewTargetMeta(id);
  return m ? m.label : ({ zx: "ZX Spectrum 128K", next: "ZX Spectrum Next",
                          sms: "Sega Master System",
                          cpc: "Amstrad CPC 6128", msx2: "MSX2 (V9938)",
                          gb: "Nintendo Game Boy Color",
                          c64: "Commodore 64", nes: "Nintendo NES" }[id] || id);
}
function previewTargetRows(id) {
  const m = previewTargetMeta(id);
  const opt = ((m && m.options) || []).find((o) => o.suffix === "art_rows");
  let choices = ((opt && opt.choices) || [8, 10, 12, 14, 16]).map(Number);
  if (id === "cpc" && previewCpcMode() !== 2)
    choices = choices.filter((n) => n <= 12);
  const def = +(opt && opt.default != null ? opt.default : 12);
  const ex = (P && P.game && P.game.extras) || {};
  const n = +(ex[id + "_art_rows"] ?? def);
  return choices.includes(n) ? n : def;
}
/* CPC video mode (0/1/2, default 1); the mode sets both the pixel width and
 * the number of simultaneously displayable inks. */
function previewCpcMode() {
  const ex = (P && P.game && P.game.extras) || {};
  const mode = +(ex.cpc_mode ?? 1);
  return [0, 1, 2].includes(mode) ? mode : 1;
}
function previewTargetWidth(id) {
  const m = previewTargetMeta(id);
  const width = (m && +m.band_width) || 256;
  if (id === "cpc") return ({ 0: 160, 1: 320, 2: 640 }[previewCpcMode()] || width);
  return width;
}
function previewTargetSize(id) {
  if (id === "zx") return `256×${artBandH()}`;
  return `${previewTargetWidth(id)}×${8 * previewTargetRows(id)}`;
}
/* Palette size the target's converter quantises to; CPC follows the selected
 * video mode, otherwise the registry is the source of truth with the built-in
 * values as a fallback. */
function previewTargetColors(id) {
  if (id === "cpc") return ({ 0: 16, 1: 4, 2: 2 }[previewCpcMode()] || 4);
  const m = previewTargetMeta(id);
  const n = m ? +m.colors : NaN;
  if (n > 0) return n;
  return ({ zx: 16, next: 256, sms: 16, msx2: 16, gb: 32,
              c64: 16, nes: 16 }[id] || 0);
}
/* The display engine the target's preview emulates, shown under its name. */
function previewTargetEngine(id) {
  const m = previewTargetMeta(id);
  const e = m ? m.engine : "";
  return e || ({ zx: "NIRVANA+", next: "Layer 2",
                   c64: "VIC-II MCM", nes: "NES PPU" }[id] || "");
}
function targetPreviewQuery(id, q) {
  if (id === "zx") return q;
  return q + (q ? "&" : "?") + "target=" + encodeURIComponent(id)
           + "&rows=" + previewTargetRows(id);
}
function targetPreviewFig(id, g, aid, q, bust) {
  const src = `/api/preview/${g}/${aid}${targetPreviewQuery(id, q)}`;
  const colors = previewTargetColors(id);
  const colorText = id === "cpc" && previewCpcMode() === 1
    ? ", mono"
    : colors ? `, ${colors} colour${colors === 1 ? "" : "s"}` : "";
  const engine = previewTargetEngine(id);
  const engineText = engine ? `<br><span class="targetnote">${esc(engine)}</span>` : "";
  return `<figure class="band target-${esc(id)}" data-tg="${esc(id)}">
      <img src="${src}${src.includes("?") ? "&" : "?"}t=${bust}"
           alt="${esc(previewTargetLabel(id))}" onerror="this.style.opacity=.15">
      <figcaption>${esc(previewTargetLabel(id))} (${esc(previewTargetSize(id))}${colorText})${engineText}
      </figcaption></figure>`;
}

/* Art pane puts the source image and every selected system preview in one
 * responsive grid; the Original carries a resizable crop box (see
 * initCropBox) that keeps the band aspect (32/art_lines); the preview always
 * uses the art's own (possibly unsaved) crop, so it agrees with the box. */
function drawArtView(id, mode, viewId = "artview") {
  const v = $(viewId);
  if (!v) return;
  const bust = Date.now();
  const g = encodeURIComponent(game || "");
  const aid = encodeURIComponent(id);
  const art = P.arts.find(x => x.id === id);
  const spec = artCropSpec(art);
  const params = [];
  if (spec) params.push(`crop=${spec}`);
  if (art && art.image) params.push(`file=${encodeURIComponent(art.image)}`);
  const cq = convQuery(art);
  if (cq) params.push(cq);
  const q = params.length ? `?${params.join("&")}` : "";
  const fq = art && art.image ? `file=${encodeURIComponent(art.image)}&` : "";
  let html;
  const systems = previewTargets();
  if (mode === "all") {
    html = `<div class="artgrid">`
         + `<figure class="src"><div class="cropstage" id="cropstage-${viewId}">
        <img src="/api/image/${g}/${aid}?${fq}t=${bust}" alt="Original" onerror="this.style.opacity=.15">
        <div class="cropbox" id="cropbox-${viewId}">
          <span class="handle nw" data-corner="nw"></span>
          <span class="handle ne" data-corner="ne"></span>
          <span class="handle sw" data-corner="sw"></span>
          <span class="handle se" data-corner="se"></span>
        </div>
      </div><figcaption id="cropcap-${viewId}">Original</figcaption></figure>`
         + systems.map((id) => targetPreviewFig(id, g, aid, q, bust)).join("")
         + `</div>`;
  } else {
    const id = systems[0] || "zx";
    html = targetPreviewFig(id, g, aid, q, bust);
  }
  v.innerHTML = html;
  v.querySelectorAll("img").forEach((img) => {
    if (img.closest(".artgrid")) return;
    img.onload = () => fitArtImg(img);
    if (img.complete) fitArtImg(img);
  });
  if (mode === "all") initCropBox(id, viewId);
}

/* Make the crop box on the Original figure movable (drag inside) and
 * resizable (drag a corner; the band aspect is kept so nothing distorts).
 * Only the box moves during the drag; the Spectrum previews are refreshed and
 * the crop persisted on pointer release, never during. */
function initCropBox(id, viewId) {
  const stage = $("cropstage-" + viewId);
  const box = $("cropbox-" + viewId);
  const cap = $("cropcap-" + viewId);
  if (!stage || !box) return;
  const img = stage.querySelector("img");
  if (!img) return;

  const start = () => {
    const natW = img.naturalWidth, natH = img.naturalHeight;
    if (!natW || !natH) {
      if (cap) cap.textContent = "Original — no image yet";
      box.style.display = "none";
      return;
    }
    const art = P.arts.find(x => x.id === id);
    const pct = artCropRect(art);
    const clamp = (r) => {
      r.w = Math.max(1, Math.min(r.w, natW));
      r.h = Math.max(1, Math.min(r.h, natH));
      r.x = Math.max(0, Math.min(r.x, natW - r.w));
      r.y = Math.max(0, Math.min(r.y, natH - r.h));
      return r;
    };
    let refit = false;
    let rect;
    if (pct) {
      rect = fitCropToBand(clamp({ x: pct[0] / 100 * natW,
                                    y: pct[1] / 100 * natH,
                                    w: pct[2] / 100 * natW,
                                    h: pct[3] / 100 * natH }), natW, natH);
      const np = [rect.x / natW * 100, rect.y / natH * 100,
                  rect.w / natW * 100, rect.h / natH * 100]
                  .map((v) => Math.round(v));
      if (np.some((v, i) => v !== pct[i])) refit = true;
    } else {
      rect = defaultCropRect(natW, natH);
    }

    const setBox = () => {
      box.style.left = (rect.x / natW * 100) + "%";
      box.style.top = (rect.y / natH * 100) + "%";
      box.style.width = (rect.w / natW * 100) + "%";
      box.style.height = (rect.h / natH * 100) + "%";
    };
    const toPct = () => [rect.x / natW * 100, rect.y / natH * 100,
                         rect.w / natW * 100, rect.h / natH * 100]
                        .map((v) => Math.round(v));
    const caption = () => {
      if (!cap) return;
      const p = toPct();
      cap.textContent = `Original — drag to move, corners to resize `
                      + `(${p[2]}%×${p[3]}% at ${p[0]},${p[1]})`;
    };
    setBox();
    caption();
    /* The art band height changed, so the stored crop no longer keeps the band
     * aspect; persist the re-fitted rectangle and refresh the previews so the
     * box and the two Spectrum bands agree (and the build stays undistorted). */
    if (refit && art) {
      art.crop = toPct();
      markDirty();
      refreshArtPreviews(id, art.crop.join(","), viewId);
    }

    const toSource = (e) => {
      const r = stage.getBoundingClientRect();
      return {
        x: (e.clientX - r.left) * natW / r.width,
        y: (e.clientY - r.top) * natH / r.height,
      };
    };

    const release = () => {
      box.classList.remove("dragging");
      box.onpointermove = box.onpointerup = box.onpointercancel = null;
      let p = toPct();
      const d = defaultCropRect(natW, natH);
      const dp = [d.x / natW * 100, d.y / natH * 100,
                  d.w / natW * 100, d.h / natH * 100].map((v) => Math.round(v));
      if (p.every((v, i) => Math.abs(v - dp[i]) <= 1)) p = null;
      const art = P.arts.find(x => x.id === id);
      if (art) art.crop = p;
      rect = clamp(p
        ? { x: p[0] / 100 * natW, y: p[1] / 100 * natH,
            w: p[2] / 100 * natW, h: p[3] / 100 * natH }
        : d);
      setBox();
      caption();
      markDirty();
      refreshArtPreviews(id, p ? p.join(",") : "", viewId);
    };

    box.onpointerdown = (e) => {
      e.preventDefault();
      try { box.setPointerCapture(e.pointerId); } catch (_) { /* no capture */ }
      box.classList.add("dragging");
      const p0 = toSource(e);
      const corner = e.target && e.target.dataset
        ? e.target.dataset.corner : null;

      if (!corner) {                                    // move
        const grab = { x: p0.x - rect.x, y: p0.y - rect.y };
        box.onpointermove = (ev) => {
          const p = toSource(ev);
          rect.x = Math.max(0, Math.min(natW - rect.w, p.x - grab.x));
          rect.y = Math.max(0, Math.min(natH - rect.h, p.y - grab.y));
          setBox();
          caption();
        };
        box.onpointerup = box.onpointercancel = release;
        return;
      }

      // Resize: one corner follows the pointer, the opposite stays fixed, and
      // the width tracks the height at the band aspect.
      const sx = (corner === "nw" || corner === "sw") ? -1 : 1;
      const sy = (corner === "nw" || corner === "ne") ? -1 : 1;
      const ax = sx > 0 ? rect.x : rect.x + rect.w;     // fixed corner
      const ay = sy > 0 ? rect.y : rect.y + rect.h;
      box.onpointermove = (ev) => {
        const p = toSource(ev);
        const dx = (p.x - ax) * sx, dy = (p.y - ay) * sy;
        const maxW = sx > 0 ? natW - ax : ax;
        const maxH = sy > 0 ? natH - ay : ay;
        let h = Math.max(dy, dx / cropAr());
        h = Math.min(h, maxH, maxW / cropAr());
        h = Math.max(h, Math.min(8, maxH, maxW / cropAr()));
        const w = cropAr() * h;
        rect = { x: sx > 0 ? ax : ax - w, y: sy > 0 ? ay : ay - h, w: w, h: h };
        setBox();
        caption();
      };
      box.onpointerup = box.onpointercancel = release;
    };

    box.style.display = "block";
  };

  if (img.complete && img.naturalWidth) start();
  else img.addEventListener("load", start, { once: true });
}

/* Refresh the Spectrum preview in place (keep the Original and its box, so
 * dragging the crop does not reload the source image). ``spec`` is
 * "x,y,w,h" or "" for the default window. */
function refreshArtPreviews(id, spec, viewId) {
  const v = $(viewId);
  if (!v) return;
  const g = encodeURIComponent(game || "");
  const aid = encodeURIComponent(id);
  const art = P.arts.find(x => x.id === id);
  const params = [];
  if (spec) params.push(`crop=${spec}`);
  if (art && art.image) params.push(`file=${encodeURIComponent(art.image)}`);
  const cq = convQuery(art);
  if (cq) params.push(cq);
  const q = params.length ? `?${params.join("&")}` : "";
  const bust = Date.now();
  v.querySelectorAll(".band[data-tg] img").forEach((img) => {
    const tid = img.closest(".band").dataset.tg;
    const src = `/api/preview/${g}/${aid}${targetPreviewQuery(tid, q)}`;
    img.src = src + (src.includes("?") ? "&" : "?") + "t=" + bust;
  });
}

/* Art is shown at 2x zoom of the 256px Spectrum band. Source images may be
 * taller/wider (512x256 by default), so the on-screen width is capped at the
 * pane width and the height follows the source's aspect ratio rather than being
 * compressed into the band's box. */
const ART_ZOOM = 2;
const ART_BASE_W = 256;

function fitArtImg(img) {
  if (!img.naturalWidth || !img.naturalHeight) return;
  const host = img.closest(".artview");
  const avail = host ? host.clientWidth : 0;
  const base = ART_BASE_W * ART_ZOOM;
  const w = avail ? Math.min(base, avail) : base;
  img.style.width = w + "px";
  img.style.height = Math.round(w * img.naturalHeight / img.naturalWidth) + "px";
}

/* Generation reads the art from the game's game.md on the server, so flush
 * any pending edits (a brand-new or just-renamed art only exists client-side)
 * before asking for a render. Otherwise the server rejects the id as unknown. */
async function regenerate(art) {
  if (!AI.image) return;
  const id = art.id;
  if (dirty && !(await save())) return;
  const a = P.arts.find(x => x.id === id);
  if (!a) { $("genstatus").textContent = "art no longer exists"; return; }
  const overrides = { prompt: a.prompt };
  $("gen").disabled = true;
  $("genstatus").textContent = "queuing…";
  $("genbar").innerHTML = '<div class="bar"><i></i></div>';
  api("POST", "/api/generate", { art: id, overrides })
    .then((r) => { activeJob = r.job; renderStopButton(); pollJob(r.job); })
    .catch((e) => {
      $("genstatus").textContent = "error: " + e.message;
      $("gen").disabled = false;
      $("genbar").innerHTML = "";
    });
}

/* Replace an art's source image with one the user picks. The file is read as a
 * data URL, the active art pane is flushed first so a brand-new/renamed art
 * exists server-side, then the image is stored (scaled to the art's
 * width/height) and the previews (generated / Spectrum) are redrawn from it. */
async function uploadArt(file, art) {
  const id = art.id;
  if (!file.type.startsWith("image/")) {
    $("genstatus").textContent = "not an image file";
    return;
  }
  if (dirty && !(await save())) return;
  $("upload").disabled = true;
  $("genstatus").textContent = "reading " + file.name + "…";
  try {
    const data = await new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(new Error("could not read file"));
      r.readAsDataURL(file);
    });
    $("genstatus").textContent = "uploading…";
    const r = await api("POST", "/api/upload_art", { art: id, data });
    art.image = r.image;
    $("genstatus").textContent = `uploaded ${file.name} (${r.bytes} bytes)`;
    drawArtView(id, "all");
    drawArtPicker(id);
  } catch (e) {
    $("genstatus").textContent = "error: " + e.message;
  } finally {
    $("upload").disabled = false;
  }
}

/* Delete one image candidate after confirmation. The server repoints the
 * entry's `image:` to the newest remaining file (or clears it when none
 * remain), so P is updated from the response and the open pane redrawn. */
async function deleteImageCandidate(kind, id, name) {
  const what = kind === "ref" ? "reference image" : "image";
  if (!confirm(`Delete ${what} "${name}"? This cannot be undone.`)) return;
  if ((dirty || rawDirty) && !(await save())) return;
  $("genstatus").textContent = `deleting ${name}…`;
  try {
    const r = await api("DELETE",
      `/api/${kind}images/${encodeURIComponent(game)}/${encodeURIComponent(id)}` +
      `?file=${encodeURIComponent(name)}`);
    if (kind === "ref") {
      const ref = refById(id);
      if (ref) ref.image = r.image || null;
      $("genstatus").textContent = `deleted ${name}`;
      drawRefView(id);
      drawRefPicker(id);
    } else {
      const a = P.arts.find(x => x.id === id);
      if (a) a.image = r.image || null;
      $("genstatus").textContent = `deleted ${name}`;
      drawArtView(id, "all");
      drawArtPicker(id);
    }
  } catch (e) {
    $("genstatus").textContent = "error: " + e.message;
  }
}

/* Visual picker for an art's candidate images. Lists assets/art/<id>/ newest
 * first and highlights the active one (the art's `image:`); clicking a
 * thumbnail selects it and marks the project dirty so a normal save persists
 * the choice. */
async function drawArtPicker(id) {
  const el = $("artpicker");
  if (!el) return;
  const a = P.arts.find(x => x.id === id);
  let data;
  try {
    data = await api("GET",
      `/api/artimages/${encodeURIComponent(game)}/${encodeURIComponent(id)}`);
  } catch (e) {
    el.innerHTML = `<span class="empty">could not list images: ${esc(e.message)}</span>`;
    return;
  }
  const files = data.files || [];
  const count = $("artpickcount");
  if (count) count.textContent = files.length + (files.length === 1 ? " file" : " files");
  if (!files.length) {
    el.innerHTML = '<span class="empty">No images yet — Regenerate or Upload to add one.</span>';
    return;
  }
  const active = a && a.image ? a.image : data.image;
  const g = encodeURIComponent(game);
  const aid = encodeURIComponent(id);
  el.innerHTML = files.map((f) => {
    const on = f.file === active;
    return `<div class="artpickwrap">
      <button class="artpick${on ? " active" : ""}" data-file="${esc(f.file)}"
          title="Use ${esc(f.file)}">
        <img src="/api/image/${g}/${aid}?file=${encodeURIComponent(f.file)}&t=${f.mtime}"
          alt="${esc(f.file)}" loading="lazy" onerror="this.style.opacity=.15">
        <span class="tag">${esc(f.file)}</span>
      </button>
      <button class="artpickdel" data-file="${esc(f.file)}"
          title="Delete image" aria-label="Delete image ${esc(f.file)}">×</button>
    </div>`;
  }).join("");
  el.querySelectorAll(".artpick").forEach((b) => {
    b.onclick = () => selectArtImage(id, b.dataset.file);
  });
  el.querySelectorAll(".artpickdel").forEach((b) => {
    b.onclick = (e) => {
      e.stopPropagation();
      deleteImageCandidate("art", id, b.dataset.file);
    };
  });
}

/* Choose a candidate as the art's active image (client state; the next save
 * writes `image:` to game.md). */
function selectArtImage(id, name) {
  const a = P.arts.find(x => x.id === id);
  if (!a || a.image === name) return;
  a.image = name;
  markDirty();
  drawArtView(id, "all");
  drawArtPicker(id);
}

/* Re-read the arts' `image:` pointers from the server after a generate job
 * wrote new candidates into game.md, and redraw the active art. `onlyId`
 * limits the redraw (a single-art job); null refreshes every art. The SPA is
 * clean before a job, so re-reading cannot drop edits. */
async function refreshArtImages(onlyId) {
  if (!P) return;
  let fresh;
  try { fresh = await api("GET", "/api/project"); }
  catch (_) { return; }
  if (!fresh || fresh.game_slug !== P.game_slug) return;
  (fresh.arts || []).forEach((f) => {
    const a = P.arts.find((x) => x.id === f.id);
    if (a) a.image = f.image;
  });
  if (sel.kind === "art" && (!onlyId || onlyId === sel.id)) {
    drawArtView(sel.id, "all");
    drawArtPicker(sel.id);
  } else {
    redrawSelection();
  }
}

