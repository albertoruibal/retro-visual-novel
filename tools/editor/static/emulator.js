"use strict";
// ------------------------------------------------------------- web emulators
/* The Emulator tab previews the exported combined web player: the mobile-first
 * novel plus a browser emulator for every selected system. The tab has no
 * toolbar of its own; opening it saves pending edits, exports <game>/web/ and
 * mounts the player. The top-bar Export player button refreshes it. */
let emu = null;              // { exit() } for the running player
let emuFitObserver = null;   // refits the player when the tab resizes
let playerStarting = false;  // guards the save/export/mount cycle
let emuNeedsRefresh = false; // a build finished while the preview was hidden

function emuFitSize() {
  const box = $("emuhost");
  if (!box) return null;
  const cs = getComputedStyle(box);
  const availW = box.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const availH = box.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
  if (availW <= 0 || availH <= 0) return null;
  return { width: availW, height: availH };
}

function fitEmulatorHost() {
  const host = $("emu");
  if (!host) return null;
  const size = emuFitSize();
  if (!size) return null;
  host.style.width = Math.max(1, Math.floor(size.width)) + "px";
  host.style.height = Math.max(1, Math.floor(size.height)) + "px";
  return size;
}

function refitEmulator() {
  if (emu) fitEmulatorHost();
}

function watchEmuFit() {
  if (emuFitObserver || typeof ResizeObserver !== "function") return;
  const box = $("emuhost");
  if (!box) return;
  emuFitObserver = new ResizeObserver(refitEmulator);
  emuFitObserver.observe(box);
}

function stopEmulator() {
  if (emu) { try { emu.exit(); } catch {} }
  emu = null;
  const host = $("emu");
  if (host) {
    host.innerHTML = "";
    host.className = "";
    host.style.width = "";
    host.style.height = "";
  }
}

function iframeEmu(host, src) {
  host.classList.add("iframe-host");
  const frame = document.createElement("iframe");
  frame.src = src;
  frame.title = "Game player";
  frame.setAttribute("allow", "autoplay; gamepad; fullscreen");
  frame.onload = () => { try { frame.contentWindow.focus(); } catch {} };
  host.append(frame);
  return {
    exit() { frame.remove(); host.classList.remove("iframe-host"); },
  };
}

function mountPlayerPreview() {
  const host = $("emu");
  if (!host || !game) return;
  if (emu) stopEmulator();
  host.innerHTML = "";
  host.className = "";
  watchEmuFit();
  fitEmulatorHost();
  emu = iframeEmu(host, playerUrl(true));
}

function showPlayerNotice(text) {
  const host = $("emu");
  if (!host) return;
  if (emu) stopEmulator();
  host.innerHTML = "";
  host.className = "";
  host.textContent = text || "";
}

async function ensurePlayerPreview(force) {
  if (view !== "emu" || playerStarting) return;
  if (!game) { emuNeedsRefresh = false; showPlayerNotice(""); return; }
  if (!force && emu && playerLoadedGame === game) return;
  playerStarting = true;
  try {
    if (!(await playerEnsureSaved())) return;
    showPlayerNotice("Exporting player…");
    const result = await playerExportNow();
    if (!result) { showPlayerNotice("Could not export the player."); return; }
    if (view !== "emu" || !game) return;
    mountPlayerPreview();
    emuNeedsRefresh = false;
  } finally {
    playerStarting = false;
  }
}

/* Called when the tab opens, after a save and after a build. A plain call only
 * starts a missing preview; `force` rebuilds it from a fresh export (a build
 * while another tab is open defers that refresh until the tab is shown). */
async function refreshEmuSystems(force) {
  if (force) emuNeedsRefresh = true;
  return ensurePlayerPreview(emuNeedsRefresh);
}

function reloadPlayerPreview() {
  if (view !== "emu" || !game) return;
  emuNeedsRefresh = false;
  mountPlayerPreview();
}
