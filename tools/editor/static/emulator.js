"use strict";
// ------------------------------------------------------------- web emulators
/* Target-aware Emulator tab. ZX uses the vendored JSSpeccy inline; SMS, MSX2,
 * CPC and Game Boy Color load pinned offline emulator pages in a same-origin iframe. The
 * target registry (GET /api/targets) supplies the adapter id and artifact
 * extensions, so adding a target does not hard-code anything here. */
let emu = null;             // { exit() } for the running emulator
let jsspeccy = null;        // the JSSpeccy instance (ZX only)
let emuFitObserver = null;  // refits an iframe emulator when the tab resizes

const EMU_KINDS = ["jsspeccy", "emulatorjs", "webmsx", "cpcjs", "gambatte"];
const EMU_EXT = {
  jsspeccy: ".tap",
  emulatorjs: ".sms",
  webmsx: ".rom",
  cpcjs: ".dsk",
  gambatte: ".gbc",
};
/* Native display aspect per target, so an iframe is sized to its picture
 * instead of filling the tab height and leaving black bands inside it. */
const EMU_ASPECT = {
  zx: 4 / 3,
  sms: 4 / 3,
  gb: 160 / 144,
  cpc: 768 / 540,
  msx2: (544 * 1.14) / 456,
};

function emuTargetMeta(id) {
  const list = (TARGETS && TARGETS.targets) || [];
  return list.find((t) => t.id === id) || null;
}
function emuTargets() {
  const selected = (typeof gameTargets === "function") ? gameTargets() : ["zx"];
  const rank = (id) => {
    const i = SYSTEM_ORDER.indexOf(id);
    return i < 0 ? SYSTEM_ORDER.length : i;
  };
  return selected.map(emuTargetMeta).filter(
    (t) => t && EMU_KINDS.includes(t.emulator))
    .sort((a, b) => rank(a.id) - rank(b.id));
}
function emuArtifact(meta) {
  const ext = EMU_EXT[meta.emulator] ||
    (meta.outputs || []).find((e) => [".tap", ".sna", ".sms", ".rom", ".dsk", ".gb", ".gbc", ".nex"].includes(e));
  if (!ext) return null;
  return `/api/artifact/${encodeURIComponent(game)}/${encodeURIComponent(game)}${ext}`;
}
function emuSelectedMeta() {
  const sel = $("emusystem");
  return sel ? emuTargetMeta(sel.value) : null;
}
function emuStorageKey() { return "rvn-emu-system-" + (game || ""); }
function legacyEmuStorageKey() { return "zxad-emu-system-" + (game || ""); }
function storedEmuSystem() {
  let value = localStorage.getItem(emuStorageKey());
  if (!value) {
    value = localStorage.getItem(legacyEmuStorageKey());
    if (value) {
      localStorage.setItem(emuStorageKey(), value);
      localStorage.removeItem(legacyEmuStorageKey());
    }
  }
  return value;
}
function emuRunName(meta) {
  if (meta && meta.emulator === "cpcjs") return "GAME";
  return String(game || "").toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
}

function emuFitSize(aspect) {
  const box = $("emuhost");
  if (!box) return null;
  const cs = getComputedStyle(box);
  const availW = box.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const availH = box.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
  if (availW <= 0 || availH <= 0) return null;
  let width = availW, height = width / aspect;
  if (height > availH) { height = availH; width = height * aspect; }
  return { width, height };
}

function fitEmulatorHost(meta) {
  const host = $("emu");
  if (!host || !meta) return null;
  const size = emuFitSize(EMU_ASPECT[meta.id] || 4 / 3);
  if (!size) return null;
  host.style.width = Math.max(1, Math.floor(size.width)) + "px";
  host.style.height = Math.max(1, Math.floor(size.height)) + "px";
  return size;
}

function speccyZoom() {
  const size = emuFitSize(EMU_ASPECT.zx);
  if (!size) return null;
  return Math.min(size.width / 256, size.height / 192);
}

function applySpeccyCrop(zoom) {
  const host = $("emu");
  const canvas = host && host.querySelector("canvas");
  const app = canvas && canvas.parentElement;
  if (!host || !canvas || !app) return;
  const fullW = 320 * zoom, fullH = 240 * zoom;
  const boxW = 256 * zoom, boxH = 192 * zoom;
  host.style.width = boxW + "px";
  host.style.height = boxH + "px";
  app.style.width = boxW + "px";
  app.style.height = boxH + "px";
  app.style.overflow = "hidden";
  canvas.style.width = fullW + "px";
  canvas.style.height = fullH + "px";
  canvas.style.maxWidth = "none";
  canvas.style.position = "absolute";
  canvas.style.left = ((boxW - fullW) / 2) + "px";
  canvas.style.top = ((boxH - fullH) / 2) + "px";
}

function refitEmulator() {
  const meta = emuSelectedMeta();
  if (!emu || !meta) return;
  if (meta.emulator === "jsspeccy") {
    const zoom = speccyZoom();
    if (jsspeccy && zoom) {
      jsspeccy.setZoom(zoom);
      applySpeccyCrop(zoom);
    }
  } else {
    fitEmulatorHost(meta);
  }
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
  jsspeccy = null;
  const host = $("emu");
  if (host) {
    host.innerHTML = "";
    host.className = "";
    host.style.width = "";
    host.style.height = "";
  }
  const run = $("run");
  if (run) run.textContent = "▶ Play";
  refreshRunButton();
}

async function artifactReady(meta) {
  if (!meta) return false;
  const url = emuArtifact(meta);
  if (!url) return false;
  try {
    const r = await fetch(url, { cache: "no-store" });
    return r.status === 200;
  } catch { return false; }
}

async function refreshEmuSystems() {
  const sel = $("emusystem");
  if (!sel) return;
  const list = emuTargets();
  const wanted = storedEmuSystem();
  const current = sel.value || wanted;
  sel.innerHTML = "";
  if (!list.length) {
    const o = document.createElement("option");
    o.value = "";
    o.textContent = "No web emulator selected";
    sel.append(o);
    sel.disabled = true;
    const hint = $("emuhint");
    if (hint) hint.innerHTML = gameTargets().includes("next")
      ? "ZX Next builds a <code>.nex</code>; run it with ZEsarUX via " +
        "<code>python3 tools/build.py run &lt;game&gt; next</code> (no bundled web emulator)."
      : "Select a system in the Systems tab.";
    const run = $("run");
    if (run) run.disabled = true;
    return;
  }
  sel.disabled = false;
  for (const meta of list) {
    const o = document.createElement("option");
    o.value = meta.id;
    o.textContent = meta.label;
    sel.append(o);
  }
  const pick = list.some((t) => t.id === current) ? current : list[0].id;
  sel.value = pick;
  localStorage.setItem(emuStorageKey(), pick);
  updateEmuHint();
  refreshRunButton();
}

function updateEmuHint() {
  const meta = emuSelectedMeta();
  const hint = $("emuhint");
  if (!hint) return;
  if (!meta) { hint.textContent = ""; return; }
  const url = emuArtifact(meta);
  const ext = url ? url.slice(url.lastIndexOf(".")) : "";
  hint.innerHTML =
    `Plays the built <code>${esc(game || "")}${esc(ext)}</code> in ${esc(meta.label)} — ` +
    "run <b>Build</b> first.";
  if (gameTargets().includes("next"))
    hint.innerHTML += "<br>ZX Next builds a <code>.nex</code>; run it with ZEsarUX " +
      "(<code>python3 tools/build.py run &lt;game&gt; next</code>).";
}

async function refreshRunButton() {
  const run = $("run");
  if (!run) return;
  if (emu) { run.disabled = false; run.textContent = "■ Stop"; return; }
  const meta = emuSelectedMeta();
  if (!game || !meta) { run.disabled = true; return; }
  const ok = await artifactReady(meta);
  run.disabled = !ok;
  const status = $("runstatus");
  if (!ok && status) status.textContent = "not built yet — run Build first";
  else if (status) status.textContent = "";
}

function iframeEmu(host, src) {
  host.classList.add("iframe-host");
  const frame = document.createElement("iframe");
  frame.src = src;
  frame.title = "Game emulator";
  frame.setAttribute("allow", "autoplay; gamepad; fullscreen");
  frame.onload = () => { try { frame.contentWindow.focus(); } catch {} };
  host.append(frame);
  return {
    exit() { frame.remove(); host.classList.remove("iframe-host"); },
  };
}

async function runEmulator() {
  if (emu) return stopEmulator();
  const meta = emuSelectedMeta();
  if (!game || !meta) {
    const status = $("runstatus");
    if (status) status.textContent = "select a system with a web emulator first";
    return;
  }
  const url = emuArtifact(meta);
  const status = $("runstatus");
  if (status) status.textContent = "loading…";
  if (!url || !(await artifactReady(meta))) {
    if (status) status.textContent = "not built yet — run Build first";
    return;
  }

  $("run").textContent = "■ Stop";
  const host = $("emu");
  host.innerHTML = "";
  host.className = "";
  const name = encodeURIComponent(game || "game");
  /* Bust caches in the embedded emulators (WebMSX keeps cartridges keyed by
   * their URL), while leaving the ZX tape URL extension intact for JSSpeccy. */
  const fresh = meta.emulator === "jsspeccy" ? url
    : url + (url.includes("?") ? "&" : "?") + "v=" + Date.now();
  const encoded = encodeURIComponent(fresh);

  watchEmuFit();

  if (meta.emulator === "jsspeccy") {
    host.classList.add("jsspeccy-host");
    const zoom = speccyZoom() || 1;
    jsspeccy = JSSpeccy(host, {
      machine: 128,
      zoom,
      openUrl: url,
      autoLoadTapes: true,
      autoStart: true,
      uiEnabled: false,
    });
    applySpeccyCrop(zoom);
    emu = { exit() { try { jsspeccy.exit(); } catch {} } };
  } else if (meta.emulator === "emulatorjs") {
    fitEmulatorHost(meta);
    emu = iframeEmu(host,
      `/emulator/sms/index.html?rom=${encoded}&name=${name}`);
  } else if (meta.emulator === "webmsx") {
    /* Large ROMs auto-detect as Konami before ASCII16; force our mapper. */
    fitEmulatorHost(meta);
    emu = iframeEmu(host,
      `/emulator/msx/index.html?ROM=${encoded}` +
      `&MACHINE=${encodeURIComponent(meta.machine || "MSX2")}` +
      `&CARTRIDGE1_FORMAT=ASCII16` +
      `&FAST_BOOT=1&SCREEN_CONTROL_BAR=0&AUTO_START=1` +
      `&SCREEN_FULLSCREEN_MODE=2`);
  } else if (meta.emulator === "cpcjs") {
    fitEmulatorHost(meta);
    emu = iframeEmu(host,
      `/emulator/cpc/index.html?rom=${encoded}&name=${name}` +
      `&run=${encodeURIComponent(emuRunName(meta))}`);
  } else if (meta.emulator === "gambatte") {
    fitEmulatorHost(meta);
    emu = iframeEmu(host,
      `/emulator/gb/index.html?rom=${encoded}&name=${name}`);
  }
  if (status) status.textContent = "";
}
