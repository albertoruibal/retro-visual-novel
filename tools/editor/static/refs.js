"use strict";
// ------------------------------------------------------------- references
// A `## <ref-id>` under `# References` is a generation-only image with its own prompt. It is stored
// in assets/refs/<id>/ and selected by an art's `refs:` line so the model can
// keep the same boat/van/character design across scenes.

function refById(id) {
  return ((P && P.refs) || []).find(r => r.id === id);
}

function refImageHtml(r) {
  if (!r) return '<span class="empty">No reference selected.</span>';
  const src = refImageUrl(r);
  if (!src) {
    return '<span class="empty">No image yet — Regenerate or Upload to add one.</span>';
  }
  return `<figure class="src"><img class="refimg" src="${esc(src)}"
    alt="${esc(r.id)}" loading="lazy" onerror="this.style.opacity=.15"></figure>`;
}

function refImageUrl(r, file) {
  if (!r) return "";
  const name = file || r.image;
  const q = name ? `?file=${encodeURIComponent(name)}&t=${Date.now()}` : "";
  return `/api/refimage/${encodeURIComponent(game)}/${encodeURIComponent(r.id)}${q}`;
}

function drawRefView(id) {
  const el = $("refview");
  if (!el) return;
  el.innerHTML = refImageHtml(refById(id));
}

async function regenerateRef(ref) {
  if (!AI.image || !ref) return;
  const id = ref.id;
  if ((dirty || rawDirty) && !(await save())) return;
  const r = refById(id);
  if (!r) { $("genstatus").textContent = "reference no longer exists"; return; }
  $("refgen").disabled = true;
  $("genstatus").textContent = "queuing…";
  $("genbar").innerHTML = '<div class="bar"><i></i></div>';
  api("POST", "/api/generate_ref", { ref: id, overrides: { prompt: r.prompt } })
    .then((res) => { pollJob(res.job); })
    .catch((e) => {
      $("genstatus").textContent = "error: " + e.message;
      $("refgen").disabled = false;
      $("genbar").innerHTML = "";
    });
}

async function uploadRef(file, ref) {
  const id = ref && ref.id;
  if (!id) return;
  if (!file.type.startsWith("image/")) {
    $("genstatus").textContent = "not an image file";
    return;
  }
  if ((dirty || rawDirty) && !(await save())) return;
  $("refupload").disabled = true;
  $("genstatus").textContent = "reading " + file.name + "…";
  try {
    const data = await new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(new Error("could not read file"));
      r.readAsDataURL(file);
    });
    $("genstatus").textContent = "uploading…";
    const res = await api("POST", "/api/upload_ref", { ref: id, data });
    const r = refById(id);
    if (r) r.image = res.image;
    $("genstatus").textContent = `uploaded ${file.name} (${res.bytes} bytes)`;
    drawRefView(id);
    drawRefPicker(id);
    renderSidebar();
  } catch (e) {
    $("genstatus").textContent = "error: " + e.message;
  } finally {
    $("refupload").disabled = false;
  }
}

async function drawRefPicker(id) {
  const el = $("refpicker");
  if (!el) return;
  const r = refById(id);
  let data;
  try {
    data = await api("GET",
      `/api/refimages/${encodeURIComponent(game)}/${encodeURIComponent(id)}`);
  } catch (e) {
    el.innerHTML = `<span class="empty">could not list images: ${esc(e.message)}</span>`;
    return;
  }
  const files = data.files || [];
  const count = $("refpickcount");
  if (count) count.textContent = files.length + (files.length === 1 ? " file" : " files");
  if (!files.length) {
    el.innerHTML = '<span class="empty">No images yet — Regenerate or Upload to add one.</span>';
    return;
  }
  const active = r && r.image ? r.image : data.image;
  const g = encodeURIComponent(game);
  const rid = encodeURIComponent(id);
  el.innerHTML = files.map((f) => {
    const on = f.file === active;
    return `<div class="artpickwrap">
      <button class="artpick${on ? " active" : ""}" data-file="${esc(f.file)}"
          title="Use ${esc(f.file)}">
        <img src="/api/refimage/${g}/${rid}?file=${encodeURIComponent(f.file)}&t=${f.mtime}"
          alt="${esc(f.file)}" loading="lazy" onerror="this.style.opacity=.15">
        <span class="tag">${esc(f.file)}</span>
      </button>
      <button class="artpickdel" data-file="${esc(f.file)}"
          title="Delete image" aria-label="Delete image ${esc(f.file)}">×</button>
    </div>`;
  }).join("");
  el.querySelectorAll(".artpick").forEach((b) => {
    b.onclick = () => selectRefImage(id, b.dataset.file);
  });
  el.querySelectorAll(".artpickdel").forEach((b) => {
    b.onclick = (e) => {
      e.stopPropagation();
      deleteImageCandidate("ref", id, b.dataset.file);
    };
  });
}

function selectRefImage(id, name) {
  const r = refById(id);
  if (!r || r.image === name) return;
  r.image = name;
  markDirty();
  drawRefView(id);
  drawRefPicker(id);
  renderSidebar();
}

async function refreshRefImages(onlyId) {
  if (!P) return;
  let fresh;
  try { fresh = await api("GET", "/api/project"); }
  catch (_) { return; }
  if (!fresh || fresh.game_slug !== P.game_slug) return;
  (fresh.refs || []).forEach((f) => {
    const r = refById(f.id);
    if (r) r.image = f.image;
  });
  if (sel.kind === "ref" && (!onlyId || onlyId === sel.id)) {
    drawRefView(sel.id);
    drawRefPicker(sel.id);
  }
  renderSidebar();
}

/* Pick which references condition an art's generation (its `refs:` line). */
function drawArtRefs(a) {
  const el = $("artrefs");
  if (!el) return;
  const refs = P.refs || [];
  if (!refs.length) {
    el.innerHTML = '<span class="empty">No references yet — add one under Art in the sidebar.</span>';
    return;
  }
  const g = encodeURIComponent(game);
  el.innerHTML = refs.map((r) => {
    const on = (a.refs || []).includes(r.id);
    const name = r.image || "";
    const q = name ? `?file=${encodeURIComponent(name)}&t=${Date.now()}` : "";
    const src = `/api/refimage/${g}/${encodeURIComponent(r.id)}${q}`;
    return `<button class="artpick${on ? " active" : ""}" data-ref="${esc(r.id)}"
        title="${esc(r.id)}">
      <img src="${src}" alt="${esc(r.id)}" loading="lazy" onerror="this.style.opacity=.15">
      <span class="tag">${esc(r.id)}</span></button>`;
  }).join("");
  el.querySelectorAll(".artpick").forEach((b) => {
    b.onclick = () => toggleArtRef(a, b.dataset.ref);
  });
}

function toggleArtRef(a, id) {
  const set = new Set(a.refs || []);
  if (set.has(id)) set.delete(id); else set.add(id);
  a.refs = [...set];
  markDirty();
  drawArtRefs(a);
}

/* Refine the selected image at 2x with img2img: keeps the composition and
 * adds detail, unlike Regenerate (which starts a fresh scene). */
async function refineEntry(kind, entry) {
  if (!AI.image || !entry) return;
  if ((dirty || rawDirty) && !(await save())) return;
  const path = kind === "ref" ? "/api/refine_ref" : "/api/refine_art";
  const body = kind === "ref" ? { ref: entry.id } : { art: entry.id };
  const btn = $("refine");
  if (btn) btn.disabled = true;
  if ($("genstatus")) $("genstatus").textContent = "queuing refine…";
  if ($("genbar")) $("genbar").innerHTML = '<div class="bar"><i></i></div>';
  api("POST", path, body)
    .then((r) => { pollJob(r.job); })
    .catch((e) => {
      if ($("genstatus")) $("genstatus").textContent = "error: " + e.message;
      if (btn) btn.disabled = false;
      if ($("genbar")) $("genbar").innerHTML = "";
    });
}
