/* Generic story editor SPA.
 *
 * State lives in `P` (the project JSON returned by /api/project). Every render
 * rebuilds the sidebar and the selected pane; edits mutate `P` and mark the
 * buffer dirty. Save PUTs the whole project; the server re-serialises the
 * selected game's game.md canonically. The game title is a game setting, so
 * the editor is not tied to one game; the top bar selects/creates/duplicates/
 * deletes games under games/.
 */
"use strict";

let P = null;              // project
let game = null;           // active game slug (basename of its folder)
let GAMES = [];            // [{slug,title,dir}] open games, in tab order
let TARGETS = { targets: [], selected: [] };  // build-target registry
let GAME_FOLDERS = true;   // true if GAMES are opened folders (vs games/)
let sel = { kind: "game" };// current selection: game | art | scene
let selMemo = {};          // last selected id per kind: {art, scene}
let dirty = false;
let build = null;          // active build id
// Whether the server has image generation enabled (an image server is
// configured); it is hidden from the UI otherwise. Refreshed from /api/health
// and /api/project and after the editor settings modal is saved.
let AI = { image: false };
// Editor-wide image-server settings (not part of game.md), from /api/settings.
let SERVER = { stable_diffusion_url: "", image_enabled: false, settings_path: "",
               z88dk_path: "", z88dk_valid: false, z88dk_default: "",
               z88dk_effective: "", z88dk_available: false,
               z88dk_missing: [],
               cc65_path: "", cc65_valid: false, cc65_default: "",
               cc65_effective: "", cc65_available: false, cc65_missing: [] };
let jobTimers = {};
let pollingJobs = new Set();  // job ids with a live progress poller (no dupes)
let activeJob = null;      // id of the generation job the Stop button cancels
let rawDirty = false;      // Monaco buffer differs from the file on disk
let rawRevision = null;    // game.md hash the Source buffer was loaded from
let rawEditor = null;      // Monaco editor instance (Source tab), lazily created
let monacoApi = null;      // the loaded `monaco` namespace (for markers/themes)
let monacoP = null;        // promise resolving once Monaco is loaded
let suppressRawChange = false;  // ignore setValue() while seeding the editor
let rawIssues = [];        // last validation issues (with 1-based `line`s)
let rawOutline = [];       // scene/art/song/item/flag links for Ctrl+click
let rawCheckTimer = null;  // debounce handle for the live game.md checker
// active view tab: settings | systems | art | scenes | flags | items | graph | raw | build | web | emu
let view = "settings";
let systemsTab = "";        // active platform sub-tab in the Systems view
let webTransition = false;  // saving pending edits before entering the Web tab
const EDIT_MODES = ["settings", "systems", "art", "music", "scenes", "flags",
                    "items"];
const VIEWS = [...EDIT_MODES, "graph", "raw", "web", "build", "emu"];

/* Remember the last game + tab across reloads (browser localStorage). */
const SESSION_KEY = "rvn.editor.session";
const LEGACY_SESSION_KEY = "zxadv.editor.session";
function saveSession() {
  try { localStorage.setItem(SESSION_KEY, JSON.stringify({ game, view })); } catch {}
}
function loadSession() {
  try {
    let raw = localStorage.getItem(SESSION_KEY);
    if (!raw) {
      raw = localStorage.getItem(LEGACY_SESSION_KEY);
      if (raw) {
        localStorage.setItem(SESSION_KEY, raw);
        localStorage.removeItem(LEGACY_SESSION_KEY);
      }
    }
    return JSON.parse(raw || "null") || {};
  } catch { return {}; }
}

function modeSelKind(mode) {
  return mode === "art" ? "art" : mode === "music" ? "song"
    : mode === "scenes" ? "scene" : mode === "flags" ? "flag"
      : mode === "items" ? "item" : "game";
}

/* Names of every flag/item: declared in `# Game flags:`/`items:` plus every
 * name derived from usage (P.flags is the server's id-ordered legend). */
function entityNames(kind) {
  const out = [];
  const add = (n) => { if (n && !out.includes(n)) out.push(n); };
  if (!P) return out;
  const g = P.game || {};
  if (kind === "flag") {
    (g.flags || []).forEach(add);
    (P.flags || []).forEach(f => { if (!f.item) add(f.name); });
  } else {
    (g.items || []).forEach(add);
    (g.start || []).forEach(add);
    (P.flags || []).forEach(f => { if (f.item) add(f.name); });
    // The engine orders item ids by display name too
    // (scenefile.assign_flags), so the Items list and every item picker read
    // alphabetically by the name shown in game.
    out.sort((a, b) => itemName(a).localeCompare(itemName(b), undefined, { sensitivity: "base" }));
  }
  return out;
}

function entitiesOf(kind) {
  return entityNames(kind).map(name => ({ id: name }));
}

/* Declared AY songs (# Game songs:), each backed by assets/music/<id>.pt3. */
function songNames() {
  return (P && P.game && P.game.songs) || [];
}
function songList() {
  return songNames().map(id => ({ id }));
}
/* The song a scene plays: its own `music:` else the game default, resolving
 * `on` to the first declared song. Mirrors scenefile.resolve_song. */
function resolvedSong(scene) {
  const songs = songNames();
  const tok = (scene && scene.music) || (P.game && P.game.music) || "";
  const t = String(tok).trim().toLowerCase();
  if (!t || t === "off") return "";
  if (t === "on") return songs[0] || "";
  return tok;
}

/* Point `sel` at a valid entity for the tab being shown (or "game" when the
 * list is empty), restoring the last picked entity when possible. */
function ensureSelection(mode) {
  const kind = modeSelKind(mode);
  if (kind === "game") { sel = { kind: "game" }; return; }
  // The Art view hosts both art and its reference images; keep whichever of
  // the two is selected rather than forcing back to an art.
  if (mode === "art" && P && (sel.kind === "art" || sel.kind === "ref")) {
    const list = sel.kind === "art" ? P.arts : (P.refs || []);
    if (list.some(x => x.id === sel.id)) return;
  }
  const list = P ? (kind === "art" ? P.arts : kind === "song" ? songList()
    : kind === "scene" ? P.scenes : entitiesOf(kind)) : [];
  const wanted = selMemo[kind];
  let id = sel.kind === kind && list.some(x => x.id === sel.id) ? sel.id
    : (wanted && list.some(x => x.id === wanted) ? wanted
      : (list[0] && list[0].id));
  // Keep the tab's kind even when it has no entities, so the pane can show its
  // own empty state instead of the game settings.
  sel = { kind, id: id || null };
  if (id) selMemo[kind] = id;
}

function setView(v) {
  if (v === "web" && webTransition) return;     // auto-save already in flight
  if (v === "web" && (dirty || rawDirty)) {
    webTransition = true;
    webEnsureSaved().then((ok) => {
      webTransition = false;
      if (ok && view !== "web") setView("web");
    }).catch(() => { webTransition = false; });
    return;
  }
  if (view === "raw" && v !== "raw" && rawDirty) {
    if (!confirm("Discard unsaved game.md changes?")) return;
    clearRawDirty();
  }
  if (v === "raw" && dirty) {
    if (confirm("Save the other tabs' unsaved changes before editing game.md?")) {
      save().then((ok) => { if (ok) setView("raw"); });
      return;
    }
    if (!confirm("Discard them and edit game.md without saving?"))
      return;
    dirty = false;
    renderTop();
  }
  view = v;
  saveSession();
  if (location.hash !== "#" + v) history.replaceState(null, "", "#" + v);
  document.querySelectorAll(".viewtab").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === v));
  $("view-edit").classList.toggle("active", EDIT_MODES.includes(v));
  $("view-emu").classList.toggle("active", v === "emu");
  $("view-graph").classList.toggle("active", v === "graph");
  $("view-raw").classList.toggle("active", v === "raw");
  $("view-build").classList.toggle("active", v === "build");
  $("view-web").classList.toggle("active", v === "web");
  $("save").disabled = v === "raw";
  if (v === "web" && typeof loadWeb === "function") loadWeb();
  if (!P) {           // no game open: show the empty state
    renderNoGame();
    return;
  }
  if (EDIT_MODES.includes(v)) {
    $("view-edit").dataset.mode = v;
    ensureSelection(v);
    renderAll();
  }
  if (v === "graph") renderGraph();
  if (v === "emu" && typeof refreshEmuSystems === "function") refreshEmuSystems();
  if (v === "art") checkArt();
  if (v === "raw") loadRaw();  // lazily loads Monaco, then lays it out
}

function slug(s, fallback) {
  const t = String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return t || fallback;
}
function uniqueId(base, taken) {
  let id = base, n = 2;
  while (taken.includes(id)) id = `${base}_${n++}`;
  return id;
}

const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function optRe() { return /(.+?)\s*->\s*(\S+)(.*)$/; }
function token(rest, key) {
  const m = new RegExp("\\b" + key + "\\s+(\\S+)").exec(rest || "");
  return m ? m[1] : "";
}
const MSG_EFFECT_WORDS = new Set(
  ["if", "unless", "inscene", "set", "unset", "pick", "leave"]);
function splitOptMsg(raw) {
  const s = String(raw || "");
  const arrow = s.indexOf("->");
  let start = 0;
  if (arrow >= 0) {
    start = arrow + 2;
    const mt = /^\s*\S+/.exec(s.slice(start));
    if (mt) start += mt[0].length;
  }
  const re = /(?:^|\s)msg\s+([\s\S]*)$/gi;
  re.lastIndex = start;
  for (let m = re.exec(s); m; m = re.exec(s)) {
    const before = s.slice(0, m.index).trimEnd();
    const wm = /\S+$/.exec(before);
    if (!wm || !MSG_EFFECT_WORDS.has(wm[0].toLowerCase()))
      return { rest: s.slice(0, m.index).trimEnd(), popup: m[1].trim() };
    re.lastIndex = m.index + 1;
  }
  return { rest: s, popup: "" };
}
function parseOpt(o) {
  const split = splitOptMsg(o);
  const m = optRe().exec(split.rest);
  if (!m) return { label: split.rest, target: "", conds: [], inscene: "",
                   set: "", unset: "", pick: "", leave: "", clear: false,
                   popup: split.popup };
  const conds = [];
  for (const cm of (m[3] || "").matchAll(/\b(if|unless)\s+(\S+)/g))
    conds.push({ kind: cm[1], name: cm[2] });
  return { label: m[1], target: m[2], conds,
           inscene: token(m[3], "inscene"),
           set: token(m[3], "set"), unset: token(m[3], "unset"),
           pick: token(m[3], "pick"), leave: token(m[3], "leave"),
           clear: /\bclear\b/.test(m[3]), popup: split.popup };
}
function fmtOpt(o) {
  let s = `${o.label.trim()} -> ${o.target}`;
  for (const c of (o.conds || []))
    if (c.name) s += ` ${c.kind} ${c.name}`;
  if (o.inscene) s += ` inscene ${o.inscene}`;
  if (o.set) s += ` set ${o.set}`;
  if (o.unset) s += ` unset ${o.unset}`;
  if (o.pick) s += ` pick ${o.pick}`;
  if (o.leave) s += ` leave ${o.leave}`;
  if (o.clear) s += ` clear`;
  if (o.popup) s += ` msg ${String(o.popup).trim()}`;
  return s;
}

/* A scene text / item description line carries its conditions after ` -> `,
 * mirroring scenefile.split_text_line:
 *   The van is here. -> if seen_van unless has_diesel
 * Unconditional lines have no arrow. */
const COND_LINE_RE = /^(.*?)\s*->\s*((?:(?:if|unless)\s+\S+\s*)+)$/;
function parseCondLine(line) {
  const s = String(line || "").trim();
  const m = COND_LINE_RE.exec(s);
  if (!m) return { text: s, conds: [] };
  const conds = [];
  for (const cm of m[2].matchAll(/\b(if|unless)\s+(\S+)/g))
    conds.push({ kind: cm[1], name: cm[2] });
  return { text: m[1].trim(), conds };
}
function fmtCondLine(p) {
  const text = String((p && p.text) || "").trim();
  const conds = ((p && p.conds) || []).filter(c => c.name);
  if (!conds.length) return text;
  const tokens = conds.map(c => `${c.kind} ${c.name}`).join(" ");
  return text ? `${text} -> ${tokens}` : `-> ${tokens}`;
}

/* Selectable-word markup in a text line: `{{word}}` / `{{word|flag}}`. Mirrors
 * scenefile.parse_words, so the effective flag of `{{word}}` is the word
 * slugified. Returns [{word, flag}] in order. */
const WORD_RE = /\{\{(.+?)\}\}/g;
function wordSlug(word) {
  return word.toLowerCase().replace(/[^0-9a-z]+/g, "_").replace(/^_+|_+$/g, "");
}
function wordsIn(t) {
  const out = [];
  for (const m of String(t || "").matchAll(WORD_RE)) {
    const bar = m[1].indexOf("|");
    const word = (bar >= 0 ? m[1].slice(0, bar) : m[1]).trim();
    const flag = (bar >= 0 ? m[1].slice(bar + 1).trim() : "") || wordSlug(word);
    out.push({ word, flag });
  }
  return out;
}
/* Rewrite every selectable word whose effective flag is `old` to `|next`
 * (used when a flag is renamed). */
function remapWords(t, old, next) {
  return String(t || "").replace(WORD_RE, (m, body) => {
    const bar = body.indexOf("|");
    const word = (bar >= 0 ? body.slice(0, bar) : body).trim();
    const flag = bar >= 0 ? body.slice(bar + 1).trim() : "";
    const eff = flag || wordSlug(word);
    return eff === old ? `{{${word}|${next}}}` : m;
  });
}
/* Drop the markup for a word whose flag is `name`, keeping the word as plain
 * text (used when a flag is deleted). */
function dropWordFlag(t, name) {
  return String(t || "").replace(WORD_RE, (m, body) => {
    const bar = body.indexOf("|");
    const word = (bar >= 0 ? body.slice(0, bar) : body).trim();
    const flag = bar >= 0 ? body.slice(bar + 1).trim() : "";
    const eff = flag || wordSlug(word);
    return eff === name ? word : m;
  });
}

function withGame(path) {
  if (!game || !path.startsWith("/api/")) return path;
  if (path === "/api/games" || path.startsWith("/api/games/")) return path;
  if (path === "/api/health") return path;
  if (path === "/api/settings") return path;
  if (path === "/api/open" || path === "/api/new" || path === "/api/close") return path;
  return path + (path.includes("?") ? "&" : "?") + "game=" + encodeURIComponent(game);
}

async function api(method, path, body) {
  const r = await fetch(withGame(path), {
    method, headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const t = await r.text();
  let j; try { j = JSON.parse(t); } catch { j = { error: t }; }
  if (!r.ok) {
    const err = new Error(j.error || r.statusText);
    err.status = r.status;    // callers may distinguish a 409 save conflict
    err.body = j;              // callers may want structured fields (e.g. issues)
    throw err;
  }
  return j;
}

/* Show/hide the image-generation chrome to match the server's enabled flag:
 * the generation bar and the Regenerate images buttons. Art upload and MIDI
 * conversion are not AI and stay. */
function renderAiChrome() {
  const artbar = $("artbar");
  if (artbar) artbar.style.display = AI.image ? "" : "none";
  const regenall = $("regenall");
  if (regenall) regenall.style.display = AI.image ? "" : "none";
  const regenmissing = $("regenmissing");
  if (regenmissing) regenmissing.style.display = AI.image ? "" : "none";
  const stopgen = $("stopgen");
  if (stopgen) stopgen.style.display = AI.image ? "" : "none";
}

function setAiFlags({ image }) {
  if (typeof image === "boolean") AI.image = image;
  renderAiChrome();
}

function markDirty(v = true) { dirty = v; renderTop(); }

/* The Build log lives in its own tab (before the Emulator). Starting a build
 * switches to it so progress is never hidden; image regeneration keeps writing
 * to it without stealing focus from the Art tab. */
function showBuildLog() {
  setView("build");
}

function setBuildStatus(msg, cls) {
  const el = $("buildstatus");
  if (!el) return;
  el.textContent = msg || "";
  el.className = "status " + (cls || "");
}

function renderTop() {
  $("dirty").textContent = dirty ? "● unsaved" : "";
  $("dirty").className = "status " + (dirty ? "bad" : "");
}

