"use strict";
// ---------------------------------------------------------------- sidebar
function renderAll() {
  if (!P) return;
  renderTitle();
  renderSidebar();
  renderPane();
  renderIssues();
  if (view === "graph") renderGraph();
  renderInventory();
  renderTop();
}

function renderTitle() {
  const g = P.game || {};
  $("title").textContent = (g.title || "Retro Visual Novel") + " — Retro Visual Novel";
}

const DEFAULT_PROMPT =
  "detailed 1980s pixel art game screen in bright saturated ZX Spectrum colours, " +
  "crisp flat shading, bold readable shapes, high contrast, clear lighting, no text, no letters";

let sidebarDrag = null;   // {kind, id} of the row being dragged

/* The lists whose rows can be reordered (drag or the up/down buttons). */
function sidebarList(kind) {
  if (!P) return null;
  return kind === "art" ? P.arts
    : kind === "scene" ? P.scenes
      : kind === "ref" ? (P.refs || []) : null;
}

function reorderSidebarItem(kind, fromId, toId, after) {
  const list = sidebarList(kind);
  if (!list) return;
  const from = list.findIndex(x => x.id === fromId);
  if (from < 0 || !list.some(x => x.id === toId) || fromId === toId) return;
  const [moved] = list.splice(from, 1);
  let to = list.findIndex(x => x.id === toId);
  if (after) to += 1;
  if (to === from) {        // already in place; restore the removed row
    list.splice(from, 0, moved);
    return;
  }
  list.splice(to, 0, moved);
  markDirty(); renderAll();
}

function stepSidebarItem(kind, id, delta) {
  const list = sidebarList(kind);
  if (!list) return;
  const from = list.findIndex(x => x.id === id);
  const to = from + delta;
  if (from < 0 || to < 0 || to >= list.length) return;
  const [moved] = list.splice(from, 1);
  list.splice(to, 0, moved);
  markDirty(); renderAll();
  // Keep keyboard focus on the moved row (the rendered buttons are new nodes).
  const row = Array.from(document.querySelectorAll(".item"))
    .find(el => el.dataset.kind === kind && el.dataset.id === id);
  if (!row) return;
  const want = delta < 0 ? ".move.up" : ".move.down";
  const fallback = delta < 0 ? ".move.down" : ".move.up";
  const btn = row.querySelector(want);
  if (btn && !btn.disabled) btn.focus();
  else {
    const other = row.querySelector(fallback);
    if (other && !other.disabled) other.focus();
  }
}

/* Active-image thumbnail for an art row. The `file:` query both selects the
 * candidate and busts the browser cache when a different one is chosen. */
function artThumbUrl(a) {
  let url = `/api/image/${encodeURIComponent(game)}/${encodeURIComponent(a.id)}`;
  if (a.image) url += `?file=${encodeURIComponent(a.image)}`;
  return url;
}

/* Active-image thumbnail for a reference row (the `image:` candidate). */
function refThumbUrl(r) {
  let url = `/api/refimage/${encodeURIComponent(game)}/${encodeURIComponent(r.id)}`;
  if (r.image) url += `?file=${encodeURIComponent(r.image)}`;
  return url;
}

function sidebarItem(kind, id, label, badge, onRemove, opts = {}) {
  const d = document.createElement("div");
  d.className = "item" + (sel.kind === kind && sel.id === id ? " active" : "");
  d.dataset.kind = kind;
  d.dataset.id = id;
  const name = document.createElement("span");
  name.className = "name";
  name.innerHTML = `${esc(label)}<span class="id">${esc(badge)}</span>` +
    (opts.start ? '<span class="id start">start</span>' : "");
  name.onclick = () => {
    sel = { kind, id };
    if (kind !== "game") selMemo[kind] = id;
    renderAll();
  };
  const del = document.createElement("button");
  del.className = "del";
  del.textContent = "×";
  del.title = "Delete";
  del.onclick = (e) => { e.stopPropagation(); onRemove(); };
  if (opts.thumb) {
    const img = document.createElement("img");
    img.className = "thumb";
    img.src = opts.thumb;
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    img.title = label;
    img.onclick = () => name.onclick();
    img.onerror = () => {
      img.onerror = null;
      img.remove();
      d.classList.remove("has-thumb");
    };
    d.classList.add("has-thumb");
    d.appendChild(img);
  }
  d.appendChild(name);
  if (opts.reorder) {
    const moves = document.createElement("span");
    moves.className = "moves";
    [["up", "▲", -1, "Move up"], ["down", "▼", 1, "Move down"]].forEach(
      ([cls, glyph, delta, title]) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "move " + cls;
        b.textContent = glyph;
        b.title = title;
        b.setAttribute("aria-label", title);
        b.disabled = delta < 0 ? !!opts.first : !!opts.last;
        b.onclick = (e) => {
          e.stopPropagation();
          stepSidebarItem(kind, id, delta);
        };
        moves.appendChild(b);
      });
    d.appendChild(moves);
  }
  d.appendChild(del);
  if (opts.reorder) {
    d.draggable = true;
    d.title = opts.start ? "Starting scene — drag to reorder"
      : "Drag to reorder";
    const clearMarks = () => {
      if (!d.parentElement) return;
      d.parentElement.querySelectorAll(".drop-before, .drop-after")
        .forEach(el => el.classList.remove("drop-before", "drop-after"));
    };
    const beforeRow = (e) => {
      const r = d.getBoundingClientRect();
      return e.clientY < r.top + r.height / 2;
    };
    d.addEventListener("dragstart", (e) => {
      sidebarDrag = { kind, id };
      d.classList.add("dragging");
      if (e.dataTransfer) {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", id);
      }
    });
    d.addEventListener("dragover", (e) => {
      if (!sidebarDrag || sidebarDrag.kind !== kind) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
      clearMarks();
      d.classList.add(beforeRow(e) ? "drop-before" : "drop-after");
    });
    d.addEventListener("dragleave", (e) => {
      if (!d.contains(e.relatedTarget)) {
        d.classList.remove("drop-before", "drop-after");
      }
    });
    d.addEventListener("drop", (e) => {
      if (!sidebarDrag || sidebarDrag.kind !== kind) return;
      e.preventDefault();
      const fromId = sidebarDrag.id;
      sidebarDrag = null;
      clearMarks();
      reorderSidebarItem(kind, fromId, id, !beforeRow(e));
    });
    d.addEventListener("dragend", () => {
      sidebarDrag = null;
      d.classList.remove("dragging");
      clearMarks();
    });
  }
  return d;
}

function renderSidebar() {
  const gameItem = document.querySelector('.item[data-tab="game"]');
  if (gameItem) gameItem.classList.toggle("active", sel.kind === "game");
  const al = $("artlist"); al.innerHTML = "";
  P.arts.forEach((a, i) => {
    al.appendChild(sidebarItem("art", a.id, a.id,
      `${P.scenes.filter(s => s.art === a.id).length} sc`,
      () => removeArt(a.id),
      { reorder: true, first: i === 0, last: i === P.arts.length - 1,
        thumb: artThumbUrl(a) }));
  });
  if (!P.arts.length) al.innerHTML = "<div class='empty'>no art</div>";
  const rl = $("reflist");
  if (rl) {
    rl.innerHTML = "";
    (P.refs || []).forEach((r, i) => {
      const uses = P.arts.filter(a => (a.refs || []).includes(r.id)).length;
      rl.appendChild(sidebarItem("ref", r.id, r.id, `${uses} art`,
        () => removeRef(r.id),
        { reorder: true, first: i === 0, last: i === P.refs.length - 1,
          thumb: refThumbUrl(r) }));
    });
    if (!(P.refs || []).length) rl.innerHTML = "<div class='empty'>no references</div>";
  }
  const ml = $("songlist");
  if (ml) {
    ml.innerHTML = "";
    songList().forEach((s) => {
      ml.appendChild(sidebarItem("song", s.id, s.id, ".pt3",
        () => removeSong(s.id)));
    });
    if (!songList().length) ml.innerHTML = "<div class='empty'>no songs</div>";
  }
  const sl = $("scenelist"); sl.innerHTML = "";
  P.scenes.forEach((s, i) => {
    sl.appendChild(sidebarItem("scene", s.id, s.title || s.id, s.id,
      () => removeScene(s.id),
      { reorder: true, start: i === 0,
        first: i === 0, last: i === P.scenes.length - 1 }));
  });
  if (!P.scenes.length) sl.innerHTML = "<div class='empty'>no scenes</div>";
  renderEntityList("flag", "flaglist", "no flags");
  renderEntityList("item", "itemlist", "no items");
  renderMobSel();
}

/* Sidebar list for the declared/derived flags or items, with a delete button
 * per row (mirrors the art/scene lists). */
function renderEntityList(kind, listId, emptyText) {
  const el = $(listId);
  if (!el) return;
  el.innerHTML = "";
  const names = entityNames(kind);
  names.forEach((name) => {
    el.appendChild(sidebarItem(kind, name,
      kind === "item" ? itemName(name) : name,
      kind === "item" ? name : "flag",
      () => removeEntity(kind, name)));
  });
  if (!names.length) el.innerHTML = `<div class='empty'>${emptyText}</div>`;
}

/* Compact entity picker shown only on narrow screens, mirroring the active
 * tab's list. Hidden by CSS on desktop. */
function renderMobSel() {
  const wrap = $("mobselwrap"), el = $("mobsel");
  if (!wrap || !el) return;
  if (sel.kind === "game" || !EDIT_MODES.includes(view)) {
    wrap.style.display = "none"; return;
  }
  if (view === "art") {           // the Art view hosts art and references
    const arts = P.arts, refs = P.refs || [];
    if (!arts.length && !refs.length) { wrap.style.display = "none"; return; }
    wrap.style.display = "";
    const group = (label, kind, list) => list.length ? `<optgroup label="${label}">`
      + list.map(x => `<option value="${kind}:${esc(x.id)}"${
        sel.kind === kind && x.id === sel.id ? " selected" : ""}>${esc(x.id)}</option>`).join("")
      + "</optgroup>" : "";
    el.innerHTML = group("References", "ref", refs) + group("Art", "art", arts);
    return;
  }
  const list = sel.kind === "art" ? P.arts
    : sel.kind === "ref" ? (P.refs || [])
      : sel.kind === "song" ? songList()
        : sel.kind === "scene" ? P.scenes
          : entitiesOf(sel.kind);
  if (!list.length) { wrap.style.display = "none"; return; }
  wrap.style.display = "";
  el.innerHTML = list.map(x => {
    const label = sel.kind === "scene" ? (x.title || x.id)
      : sel.kind === "item" ? itemName(x.id)
        : x.id;
    return `<option value="${esc(x.id)}"${x.id === sel.id ? " selected" : ""}>${esc(label)}</option>`;
  }).join("");
}

function removeScene(id) {
  const s = P.scenes.find(x => x.id === id);
  if (!s) return;
  if (!confirm(`Delete scene "${s.title || s.id}"?`)) return;
  P.scenes = P.scenes.filter(x => x.id !== id);
  if (sel.kind === "scene" && sel.id === id)
    sel = { kind: "scene", id: P.scenes.length ? P.scenes[0].id : null };
  if (selMemo.scene === id) selMemo.scene = sel.id || null;
  markDirty(); renderAll();
}

function addRef() {
  const id = uniqueId("reference", (P.refs || []).map(r => r.id));
  if (!P.refs) P.refs = [];
  P.refs.push({ kind: "ref", id, prompt: "", image: null });
  sel = { kind: "ref", id };
  selMemo.ref = id;
  markDirty(); renderAll();
}

function removeRef(id) {
  const n = P.arts.filter(a => (a.refs || []).includes(id)).length;
  if (!confirm(`Delete reference "${id}"${n ? ` (used by ${n} art)` : ""}?`))
    return;
  P.refs = (P.refs || []).filter(r => r.id !== id);
  P.arts.forEach(a => { a.refs = (a.refs || []).filter(x => x !== id); });
  if (sel.kind === "ref" && sel.id === id)
    sel = { kind: "ref", id: P.refs.length ? P.refs[0].id : null };
  if (selMemo.ref === id) selMemo.ref = sel.id || null;
  markDirty(); renderAll();
}

/* Rename a reference id and repoint every art that uses it. Named fields are
 * edited on each keystroke, so `old` is the current id. */
function renameRef(old, next) {
  next = next.trim();
  if (!next || next === old) return;
  if ((P.refs || []).some(r => r.id === next)) return;
  (P.refs || []).forEach(r => { if (r.id === old) r.id = next; });
  P.arts.forEach(a => {
    a.refs = (a.refs || []).map(x => x === old ? next : x);
  });
  if (sel.kind === "ref" && sel.id === old) sel.id = next;
  if (selMemo.ref === old) selMemo.ref = next;
  markDirty(); renderSidebar();
  const h = document.querySelector("#main h2");
  if (h) h.firstChild.textContent = `Reference: ${next} `;
}

function removeArt(id) {
  const n = P.scenes.filter(s => s.art === id).length;
  if (n && !confirm(`Art "${id}" is used by ${n} scene(s). Delete anyway?`))
    return;
  if (!n && !confirm(`Delete art "${id}"?`)) return;
  P.arts = P.arts.filter(x => x.id !== id);
  P.scenes.forEach(s => { if (s.art === id) s.art = P.arts[0] ? P.arts[0].id : ""; });
  if (sel.kind === "art" && sel.id === id)
    sel = { kind: "art", id: P.arts.length ? P.arts[0].id : null };
  if (selMemo.art === id) selMemo.art = sel.id || null;
  markDirty(); renderAll();
}

/* Rename an art id in place and repoint every scene that references it.
 * Called on each keystroke, so `old` must match the art's current id. */
function renameArt(old, next) {
  next = next.trim();
  if (!next || next === old) return;
  if (P.arts.some(a => a.id === next)) return;
  P.arts.forEach(a => { if (a.id === old) a.id = next; });
  P.scenes.forEach(s => { if (s.art === old) s.art = next; });
  if (sel.kind === "art" && sel.id === old) sel.id = next;
  if (selMemo.art === old) selMemo.art = next;
  markDirty(); renderSidebar();
  const h = document.querySelector("#main h2");
  if (h) h.firstChild.textContent = `Art: ${next} `;
}

/* Rename a song id: repoint the game default and every scene `music:` that
 * names it. Called on each keystroke, so `old` must match the current id. */
function renameSong(old, next) {
  next = next.trim();
  if (!next || next === old) return;
  if (songNames().includes(next)) return;
  P.game.songs = songNames().map(s => s === old ? next : s);
  if ((P.game.music || "") === old) P.game.music = next;
  P.scenes.forEach(s => { if ((s.music || "") === old) s.music = next; });
  if (sel.kind === "song" && sel.id === old) sel.id = next;
  if (selMemo.song === old) selMemo.song = next;
  markDirty(); renderSidebar();
  const h = document.querySelector("#main h2");
  if (h) h.firstChild.textContent = `Song: ${next} `;
}

function removeSong(id) {
  const n = P.scenes.filter(s => (s.music || "") === id).length;
  if (!confirm(`Delete song "${id}"${n ? ` (played by ${n} scene(s))` : ""}?`))
    return;
  P.game.songs = songNames().filter(s => s !== id);
  if ((P.game.music || "") === id) P.game.music = null;
  P.scenes.forEach(s => { if ((s.music || "") === id) s.music = null; });
  if (sel.kind === "song" && sel.id === id)
    sel = { kind: "song", id: P.game.songs.length ? P.game.songs[0] : null };
  if (selMemo.song === id) selMemo.song = sel.id || null;
  markDirty(); renderAll();
}

function addSong() {
  const id = uniqueId("song", songNames());
  if (!P.game.songs) P.game.songs = [];
  P.game.songs.push(id);
  sel = { kind: "song", id };
  selMemo.song = id;
  markDirty(); renderAll();
}

async function uploadSong(file, song) {
  const read = () => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
  if (dirty && !(await save())) return;
  const status = $("songstatus");
  try {
    if (status) { status.textContent = "uploading…"; status.className = "status"; }
    const data = await read();
    const r = await api("POST", "/api/upload_song", { song: song.id, data });
    if (status) {
      status.textContent = `${r.bytes} bytes`;
      status.className = "status ok";
    }
    refreshSongAudio(song.id);
  } catch (e) {
    if (status) { status.textContent = e.message; status.className = "status bad"; }
  }
}

/* Force the inline player to reload its stream after the module changed (the
 * rendered WAV is re-made server-side; cache-bust so the browser refetches). */
function refreshSongAudio(id) {
  const a = $("songaudio");
  if (!a) return;
  const base = `/api/songpreview/${encodeURIComponent(game)}/${encodeURIComponent(id)}`;
  a.src = `${base}?t=${Date.now()}`;
  a.load();
}

/* Conversion options shared by Convert and Re-convert, read from the pane's
 * controls. The cut window is transient (seconds; blank = start/end). */
function convertOpts() {
  const num = (id) => ($(id) ? parseFloat($(id).value) || 0 : 0);
  const ival = (id, dflt) => ($(id) ? parseInt($(id).value, 10) || dflt : dflt);
  return {
    style: $("cstyle") ? $("cstyle").value : "faithful",
    bass: $("cbass") ? $("cbass").value : "normal",
    transpose: ival("ctranspose", 0),
    rows_per_beat: ival("crows", 4),
    speed: ival("cspeed", 0),
    author: $("cauthor") ? $("cauthor").value.trim() : "",
    loop_pos: ival("cloop", 0),
    channel_c: $("cvoice") ? $("cvoice").value : "",
    arp_speed: ival("carpspeed", 1),
    auto_transpose: !!($("cautotranspose") && $("cautotranspose").checked),
    vibrato: !!($("cvibrato") && $("cvibrato").checked),
    no_dynamics: !!($("cnodynamics") && $("cnodynamics").checked),
    trim_start: num("ctrimstart"),
    trim_end: num("ctrimend"),
  };
}

/* Remember the last cut window per game/song so a re-convert does not need it
 * re-typed. This is transient UI state (localStorage), not game.md state. */
function cutKey(id) { return `rvn.cut.${game}.${id}`; }
function legacyCutKey(id) { return `zxadv.cut.${game}.${id}`; }
function restoreCutValues(id) {
  let cut = null;
  try {
    let raw = localStorage.getItem(cutKey(id));
    if (!raw) {
      raw = localStorage.getItem(legacyCutKey(id));
      if (raw) {
        localStorage.setItem(cutKey(id), raw);
        localStorage.removeItem(legacyCutKey(id));
      }
    }
    cut = JSON.parse(raw || "null");
  } catch {}
  if ($("ctrimstart")) $("ctrimstart").value = cut && cut.start ? cut.start : "";
  if ($("ctrimend")) $("ctrimend").value = cut && cut.end ? cut.end : "";
}
function saveCutValues(id) {
  try {
    localStorage.setItem(cutKey(id),
      JSON.stringify({ start: convertOpts().trim_start, end: convertOpts().trim_end }));
  } catch {}
}

/* Show the stored source .mid's length so a cut range can be chosen. */
async function loadSongSource(id) {
  const el = $("songsource");
  if (!el) return;
  el.textContent = "source: checking…";
  try {
    const r = await api("GET",
      `/api/songsource/${encodeURIComponent(game)}/${encodeURIComponent(id)}`);
    el.textContent = r.exists
      ? `source: ${r.seconds != null ? r.seconds.toFixed(1) + " s" : "?"}` +
        ` (${r.bytes} bytes .mid)`
      : "source: no stored .mid yet";
  } catch (e) {
    el.textContent = "source: —";
  }
}

/* Convert an uploaded MIDI to this song's .pt3 with spectrumizer (server-side).
 * The active song pane is flushed first so a brand-new/renamed song exists
 * server-side; the conversion options come from the pane's controls. */
async function convertSong(file, song) {
  if (!/\.(mid|midi)$/i.test(file.name) && !file.type.startsWith("audio/midi") &&
      !/midi/i.test(file.type)) {
    const st = $("songstatus");
    if (st) { st.textContent = "not a .mid/.midi file"; st.className = "status bad"; }
    return;
  }
  const opts = convertOpts();
  if (dirty && !(await save())) return;
  saveCutValues(song.id);
  const status = $("songstatus");
  $("songconvert").disabled = true;
  try {
    if (status) { status.textContent = "reading " + file.name + "…"; status.className = "status"; }
    const data = await new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(new Error("could not read file"));
      r.readAsDataURL(file);
    });
    if (status) { status.textContent = "converting…"; status.className = "status"; }
    const r = await api("POST", "/api/convert_song",
      { song: song.id, name: P.game.title || song.id, data, opts });
    if (status) {
      status.textContent = `converted ${file.name} → ${r.bytes} bytes`;
      status.className = "status ok";
    }
    refreshSongAudio(song.id);
    loadSongSource(song.id);
  } catch (e) {
    if (status) { status.textContent = e.message; status.className = "status bad"; }
  } finally {
    $("songconvert").disabled = false;
  }
}

/* Rebuild the .pt3 from the stored original .mid with the current options
 * (including the cut), without re-uploading the MIDI. */
async function reconvertSong(song) {
  if (dirty && !(await save())) return;
  saveCutValues(song.id);
  const status = $("songstatus");
  const btn = $("songreconvert");
  if (btn) btn.disabled = true;
  try {
    if (status) { status.textContent = "re-converting stored source…"; status.className = "status"; }
    const r = await api("POST", "/api/reconvert_song",
      { song: song.id, name: P.game.title || song.id, opts: convertOpts() });
    if (status) {
      status.textContent = `re-converted → ${r.bytes} bytes`;
      status.className = "status ok";
    }
    refreshSongAudio(song.id);
  } catch (e) {
    if (status) { status.textContent = e.message; status.className = "status bad"; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

function addScene() {
  const id = uniqueId("scene", P.scenes.map(s => s.id));
  P.scenes.push({ id, title: "New scene", art: P.arts[0] ? P.arts[0].id : "",
                  ending: null, music: null, text: [], opts: [] });
  sel = { kind: "scene", id };
  selMemo.scene = id;
  markDirty(); renderAll();
}

function addArt() {
  const id = uniqueId("art", P.arts.map(a => a.id));
  P.arts.push({ id, prompt: "" });
  sel = { kind: "art", id };
  selMemo.art = id;
  markDirty(); renderAll();
}

