"use strict";
// ------------------------------------------------------------------- load
async function loadGames(preferred) {
  const g = await api("GET", "/api/games");
  GAMES = g.games || [];
  GAME_FOLDERS = g.folder !== false;
  const exists = GAMES.some(x => x.slug === preferred);
  game = exists ? preferred : g.selected || (GAMES[0] && GAMES[0].slug) || null;
  saveSession();
  renderGameBar();
}

/* Fetch the image-generation flag once and hide its chrome accordingly, so
 * the UI matches the server even before a project is selected (or when none
 * exists). */
async function loadAiFlags() {
  try {
    const h = await api("GET", "/api/health");
    setAiFlags({ image: h.image_enabled });
  } catch { /* server down; leave defaults hidden */ }
}

/* Editor-wide server settings, edited in the top-bar Settings modal. */
async function loadServerSettings() {
  try { SERVER = await api("GET", "/api/settings"); }
  catch { /* server down; keep the last known values */ }
}

/* A build output from a previous session may already exist — enable Play if so. */
async function refreshRunButton() {
  if (!game) return;
  try {
    const r = await fetch(`/api/tap/${encodeURIComponent(game)}/${encodeURIComponent(game)}.tap`,
                          { cache: "no-store" });
    $("run").disabled = r.status !== 200;
    if (r.status !== 200) stopEmulator();
  } catch { /* server down; leave as is */ }
}

function renderGameBar() {
  const g = GAMES.find(x => x.slug === game) || null;
  const el = $("gamelabel");
  if (el) {
    el.innerHTML = `<span class="gp-label">${esc(g ? (g.title || g.slug) : "no folder open")}</span>`;
    el.title = g ? g.dir : "Open a game folder";
  }
  renderGameMenu();
  const reload = $("reload");
  if (reload) reload.disabled = !game;
  renderStopButton();
}

/* The switcher dropdown: one row per open game (click to switch, × to close)
 * plus the open/new actions. Rebuilt whenever GAMES or the active game change. */
function renderGameMenu() {
  const pop = $("gamepickpop");
  if (!pop) return;
  const rows = GAMES.map((x) => {
    const active = x.slug === game;
    const close = GAME_FOLDERS
      ? `<button class="gamepick-close" data-close="${esc(x.slug)}" title="Close this game">×</button>`
      : "";
    return `<div class="gamepick-row">
      <button class="gamepick-item${active ? " active" : ""}" data-slug="${esc(x.slug)}"
              role="menuitemradio" aria-checked="${active}" title="${esc(x.dir)}">
        <span class="gp-name">${esc(x.title || x.slug)}</span>
        <span class="gp-dir">${esc(x.dir)}</span>
      </button>
      ${close}
    </div>`;
  }).join("");
  pop.innerHTML = (rows || '<div class="empty">No game folders open.</div>') +
    `<div class="gamepick-sep"></div>
     <button class="gamepick-add" data-act="open" role="menuitem">Open folder…</button>
     <button class="gamepick-add" data-act="new" role="menuitem">New…</button>`;
  pop.querySelectorAll("[data-slug]").forEach((b) => {
    b.onclick = () => { closeGameMenu(); switchGame(b.dataset.slug); };
  });
  pop.querySelectorAll("[data-close]").forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); closeGameMenu(); closeGame(b.dataset.close); };
  });
  pop.querySelectorAll("[data-act]").forEach((b) => {
    b.onclick = () => {
      closeGameMenu();
      if (b.dataset.act === "open") openGameFolder(); else newGame();
    };
  });
}

function toggleGameMenu() {
  const pop = $("gamepickpop"), btn = $("gamelabel");
  if (!pop) return;
  const open = pop.hidden;
  pop.hidden = !open;
  if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
}

function closeGameMenu() {
  const pop = $("gamepickpop"), btn = $("gamelabel");
  if (pop) pop.hidden = true;
  if (btn) btn.setAttribute("aria-expanded", "false");
}

/* Switch to another open game. Unsaved edits are discarded after a confirm,
 * mirroring Open folder…. */
async function switchGame(slug) {
  if (!slug || slug === game) return;
  if (!GAMES.some(x => x.slug === slug)) return;
  if ((dirty || rawDirty) && !confirm("Discard unsaved changes?")) return;
  game = slug;
  sel = { kind: "game" };
  selMemo = {};
  stopEmulator();
  saveSession();
  rememberGames();
  await load();
}

/* Close an open game folder (its files are untouched). Closing the active game
 * falls back to another open one, or to the empty state; closing another one
 * leaves the current game (and its unsaved edits) alone. */
async function closeGame(slug) {
  if (slug === game && (dirty || rawDirty) &&
      !confirm("Discard unsaved changes?")) return;
  try {
    const r = await api("POST", "/api/close", { game: slug });
    GAMES = r.games || [];
    if (slug !== game) {
      saveSession();
      rememberGames();
      renderGameBar();
      return;
    }
    game = GAMES.length ? GAMES[0].slug : null;
    sel = { kind: "game" };
    selMemo = {};
    stopEmulator();
    await load();
    rememberGames();
  } catch (e) { alert("close failed: " + e.message); }
}

async function load() {
  await loadGames(game);
  await loadAiFlags();
  await loadServerSettings();
  if (!game) {
    P = null; dirty = false;
    view = "settings";
    $("title").textContent = "Retro Visual Novel";
    setView(view);
    renderIssuesEmpty();
    return;
  }
  P = await api("GET", "/api/project");
  try { TARGETS = await api("GET", "/api/targets"); }
  catch { TARGETS = { targets: [], selected: [] }; }
  if (P.ai) setAiFlags(P.ai);
  dirty = false;
  rawDirty = false;
  renderTitle();
  setView(view);
  reattachJob(P.active_job);
  checkArt();
  refreshEmuSystems();
}

function renderIssuesEmpty() {
  $("issues").innerHTML = "<em>no issues</em>";
  $("invlist").innerHTML = "<em>no items</em>";
  const svg = $("scenegraph");
  if (svg) { svg.innerHTML = ""; svg.setAttribute("width", 0); svg.setAttribute("height", 0); }
}

/* No game open: show the empty state. The editor-wide settings live in the
 * top-bar Settings modal, so they are reachable without a folder. */
function renderNoGame() {
  const msg = "<p>No folder open. Use <b>Open folder…</b> to load a game, " +
    "or <b>New…</b> to create one.</p>";
  $("main").innerHTML = msg;
}

/* The editor-wide settings panes (one per tab) shown in the top-bar Settings
 * modal. Global: not stored in game.md. */
function paneEditor() {
  return `<div class="card" id="cardz88dk" data-pane="z88dk">
    <label>z88dk path</label>
    <div style="display:flex;gap:8px">
      <input id="msz88dk" value="${esc(SERVER.z88dk_path || "")}"
             placeholder="${esc(SERVER.z88dk_default || "/tmp/z88dk")}"
             style="flex:1">
      <button id="msz88dkbrowse" type="button">Browse…</button>
    </div>
    <div class="hint">Point this at the root of a complete z88dk toolchain
      (it needs <code>bin/zcc</code>, <code>bin/z88dk-z80asm</code>,
      <code>bin/z88dk-appmake</code> and <code>bin/z88dk-zx0</code>). Picking a
      folder saves it. Leave this blank to use <code>$Z88DK</code>, or on Linux
      a Snap install (<code>/snap/z88dk/current</code>), which is detected
      automatically. Nightly tarballs from
      <code>http://nightly.z88dk.org</code> are source-only: their
      <code>bin/</code> stays empty until you run <code>./build.sh</code> —
      only the Windows/macOS zips ship prebuilt binaries. On Linux, build the
      tarball with <code>./build.sh</code>, install the Snap (Ubuntu:
      <code>snap install z88dk --beta</code>, tree at
      <code>/snap/z88dk/current</code>) or use the Docker image; the Docker
      image's binaries are musl-linked and only run inside that container, so
      this card needs a folder built for your host.</div>
    <div class="hint" id="msz88dkstate"></div>
    <div style="margin-top:10px;display:flex;gap:8px;align-items:center">
      <button id="mszsavetool" class="primary">Save toolchain</button>
      <span id="mszstatus" class="status"></span>
    </div>
  </div>
  <div class="card" data-pane="servers" hidden>
    <label>Stable Diffusion server</label>
    <input id="mssdurl" value="${esc(SERVER.stable_diffusion_url || "")}"
           placeholder="http://127.0.0.1:7860">
    <div class="hint">The stable-diffusion.cpp endpoint used by the Art tab and
      the Regenerate buttons. It applies immediately and is shared by every
      game, not stored in <code>game.md</code>. Leave it blank to disable image
      generation and hide its controls.</div>
    <div style="margin-top:10px;display:flex;gap:8px;align-items:center">
      <button id="mssave" class="primary">Save server</button>
      <span id="msstatus" class="status"></span>
    </div>
  </div>`;
}

function renderZ88dkState() {
  const el = $("msz88dkstate");
  if (!el) return;
  const typed = $("msz88dk") ? $("msz88dk").value.trim() : "";
  const saved = SERVER.z88dk_path || "";
  const missing = Array.isArray(SERVER.z88dk_missing) ? SERVER.z88dk_missing : [];
  const absent = missing.length ? missing.join(", ") : "bin/zcc";
  const eff = SERVER.z88dk_effective || typed || SERVER.z88dk_default || "/tmp/z88dk";
  if (!typed) {
    if (SERVER.z88dk_available) {
      el.textContent = `Using the default: ${eff} (toolchain complete).`;
      el.className = "hint ok";
    } else {
      el.textContent = `Using the default: ${eff}, but ${absent} is not there` +
        " — set the toolchain folder before building.";
      el.className = "hint bad";
    }
  } else if (typed !== saved) {
    el.textContent = "Save this path to check it.";
    el.className = "hint";
  } else if (SERVER.z88dk_available) {
    el.textContent = "Looks like a valid z88dk toolchain (all build tools found).";
    el.className = "hint ok";
  } else {
    el.textContent = `This z88dk folder is incomplete — missing ${absent}. ` +
      "Pick a complete z88dk install (it ships z88dk-zx0).";
    el.className = "hint bad";
  }
}

/* The Settings modal splits its editor-wide blocks into tabs. Only the active
 * pane is shown; openServerSettings("z88dk") switches to the toolchain tab. */
function showSettingsPane(pane) {
  document.querySelectorAll("#settingstabs .subtab").forEach((b) => {
    const on = b.dataset.pane === pane;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll("#settingsbody [data-pane]").forEach((c) => {
    c.hidden = c.dataset.pane !== pane;
  });
}

function wireEditor() {
  document.querySelectorAll("#settingstabs .subtab").forEach((b) => {
    b.onclick = () => showSettingsPane(b.dataset.pane);
  });
  const save = $("mssave");
  if (save) save.onclick = () => saveServers($("msstatus"));
  const saveTool = $("mszsavetool");
  if (saveTool) saveTool.onclick = () => saveToolchain($("mszstatus"));
  const browse = $("msz88dkbrowse");
  if (browse) browse.onclick = async () => {
    const b = window.rvn;
    const picked = async (p) => {
      if (!p) return;
      $("msz88dk").value = p;
      await saveToolchain($("mszstatus"));
    };
    if (!b || typeof b.pickDir !== "function") {
      await picked(prompt("Path to the z88dk toolchain folder:", $("msz88dk").value));
      return;
    }
    await picked(await b.pickDir());
  };
  renderZ88dkState();
}

/* Saving the toolchain alone (the Browse picker calls this) leaves the model
 * server fields untouched. */
async function saveToolchain(el) {
  if (el) { el.textContent = "saving…"; el.className = "status"; }
  try {
    const r = await api("POST", "/api/settings", {
      z88dk_path: $("msz88dk") ? $("msz88dk").value.trim() : "",
    });
    SERVER = r;
    if (el) { el.textContent = "saved"; el.className = "status ok"; }
    renderZ88dkState();
    return true;
  } catch (e) {
    if (el) { el.textContent = e.message; el.className = "status bad"; }
    return false;
  }
}

async function saveServers(el) {
  if (el) { el.textContent = "saving…"; el.className = "status"; }
  try {
    const r = await api("POST", "/api/settings", {
      stable_diffusion_url: $("mssdurl").value.trim(),
      z88dk_path: $("msz88dk") ? $("msz88dk").value.trim() : "",
    });
    SERVER = r;
    setAiFlags({ image: r.image_enabled });
    if (el) { el.textContent = "saved"; el.className = "status ok"; }
    renderZ88dkState();
    checkArt();
  } catch (e) {
    if (el) { el.textContent = e.message; el.className = "status bad"; }
  }
}

/* Top-bar Settings modal: the editor-wide build toolchain and model servers,
 * available on any tab and with no game open. ``focus="z88dk"`` highlights the
 * toolchain card for a build that has no compiler. */
function openServerSettings(focus) {
  const modal = $("settingsmodal");
  if (!modal) return;
  $("settingsbody").innerHTML = paneEditor();
  wireEditor();
  showSettingsPane(focus === "servers" ? "servers" : "z88dk");
  modal.hidden = false;
  if (focus === "z88dk") {
    const input = $("msz88dk");
    const card = $("cardz88dk");
    if (card) {
      card.classList.add("attention");
      setTimeout(() => card.classList.remove("attention"), 1800);
    }
    if (input) input.focus();
  }
}
function closeServerSettings() {
  const modal = $("settingsmodal");
  if (modal) modal.hidden = true;
}


/* Folder-open model: pick a folder containing game.md and activate it. In the
 * desktop app window.rvn shows native dialogs; in a browser we fall back to a
 * path prompt. `kind` is "open" or "new". */
async function pickFolder(kind) {
  const b = window.rvn;
  if (b) {
    if (kind === "new" && typeof b.newFolder === "function") return await b.newFolder();
    if (typeof b.openFolder === "function") return await b.openFolder();
  }
  return prompt("Path to a game folder (the one containing game.md):", "");
}

/* Persist the open game folders and the active one (desktop app); a no-op in a
 * plain browser, where nothing survives a reload anyway. */
function rememberGames() {
  const b = window.rvn;
  if (!b) return;
  const dirs = GAMES.map(g => g.dir).filter(Boolean);
  const active = (GAMES.find(g => g.slug === game) || {}).dir || "";
  if (typeof b.rememberGames === "function") b.rememberGames(dirs, active);
  else if (typeof b.rememberFolder === "function" && active) b.rememberFolder(active);
}

async function openGameFolder() {
  if ((dirty || rawDirty) &&
      !confirm("Discard unsaved changes?")) return;
  let path;
  try { path = await pickFolder("open"); } catch { return; }
  if (path === null || path === undefined) return;
  path = String(path).trim();
  if (!path) return;
  try {
    const r = await api("POST", "/api/open", { path });
    GAMES = r.games || [];
    game = r.game ? r.game.slug : null;
    sel = { kind: "game" };
    selMemo = {};
    stopEmulator();
    await load();
    rememberGames();
  } catch (e) { alert("open failed: " + e.message); }
}

async function newGame() {
  let parent;
  try { parent = await pickFolder("new"); } catch { return; }
  if (!parent) return;
  const name = prompt("New game name (letters, digits, dashes):", "new-game");
  if (!name) return;
  const title = prompt("Game title:", name) || name;
  if ((dirty || rawDirty) && !confirm("Discard unsaved changes?")) return;
  try {
    const r = await api("POST", "/api/new", { parent, name, title });
    game = r.game.slug;
    sel = { kind: "game" };
    selMemo = {};
    stopEmulator();
    await load();
    rememberGames();
  } catch (e) { alert("create failed: " + e.message); }
}

async function checkArt() {
  const el = $("sdstatus");
  if (!el) return;
  if (!AI.image) return;
  try {
    const h = await api("GET", "/api/health");
    if (h.reachable) {
      el.textContent = `Stable Diffusion: ${h.model || "up"} @ ${h.stable_diffusion_url}`;
      el.className = "status ok";
    } else {
      el.textContent = `Stable Diffusion offline @ ${h.stable_diffusion_url}`;
      el.className = "status bad";
    }
  } catch (e) {
    el.textContent = "server error";
    el.className = "status bad";
  }
}

