"use strict";
// -------------------------------------------------------------- web runtime
/* The Web tab previews the exported static runtime.  The runtime itself is
 * frontend-only: the server only writes <game>/web/ (a build step) and serves
 * those files.  Pending edits are saved before entering the tab; the preview
 * re-exports and reloads only when the exported revision actually changes. */

let webLoadedGame = null;   // game currently in the iframe (progress kept on tab switches)
let webLoadedRev = null;    // revision of the export currently in the iframe
let webLoadingGame = null;  // game whose export is in flight

function webRuntimeUrl() {
  if (!game) return "";
  return `/play/${encodeURIComponent(game)}/?t=${Date.now()}`;
}

function webSetStatus(message, bad) {
  const el = $("webstatus");
  if (!el) return;
  el.textContent = message || "";
  el.className = "status " + (bad ? "bad" : "");
}

function showWebFrame(slug, rev) {
  const frame = $("webframe");
  const empty = $("webempty");
  if (!frame || !empty) return;
  empty.hidden = true;
  frame.hidden = false;
  webLoadedGame = slug;
  webLoadedRev = rev || null;
  frame.src = `/play/${encodeURIComponent(slug)}/?t=${Date.now()}`;
  const zip = $("webzip");
  if (zip) zip.disabled = false;
}

async function webExportNow() {
  if (!game) return null;
  try {
    const result = await api("POST", "/api/web_export", {});
    const zip = $("webzip");
    if (zip) zip.disabled = false;
    return result;
  } catch (e) {
    webSetStatus("export failed: " + e.message, true);
    return null;
  }
}

async function prepareWeb(slug, force) {
  webSetStatus("preparing…");
  const result = await webExportNow();
  if (!result) {
    if (game === slug) {
      const empty = $("webempty");
      if (empty && webLoadedGame !== slug) {
        empty.textContent = "Could not prepare the web runtime.";
        empty.hidden = false;
      }
    }
    return;
  }
  if (game !== slug) return;
  if (!force && webLoadedGame === slug && webLoadedRev === result.rev) {
    webSetStatus(dirty || rawDirty ? "unsaved changes — Reload to apply" : "");
    return;
  }
  showWebFrame(slug, result.rev);
  webSetStatus(dirty || rawDirty ? "unsaved changes — Reload to apply" : "");
}

function loadWeb(force) {
  const frame = $("webframe");
  const empty = $("webempty");
  if (!frame || !empty) return;
  const exportBtn = $("webexport");
  if (exportBtn) exportBtn.disabled = !game;
  if (!game) {
    webLoadedGame = null;
    webLoadedRev = null;
    webLoadingGame = null;
    frame.hidden = true;
    frame.removeAttribute("src");
    empty.textContent = "Open a game to play it in the browser.";
    empty.hidden = false;
    webSetStatus("");
    return;
  }
  if (!force && webLoadingGame === game) return;
  const slug = game;
  if (webLoadedGame !== slug) {
    webLoadedGame = null;
    webLoadedRev = null;
    frame.hidden = true;
    empty.textContent = "Preparing the web runtime…";
    empty.hidden = false;
  }
  webLoadingGame = slug;
  prepareWeb(slug, force).finally(() => {
    if (webLoadingGame === slug) webLoadingGame = null;
  });
}

function reloadWeb() {
  loadWeb(true);
}

async function webEnsureSaved() {
  if (view === "raw" && rawDirty) {
    await saveRaw();
    if (rawDirty) return false;
  } else if (dirty && !(await save())) {
    return false;
  }
  return true;
}

async function openWebTab() {
  if (!game) return;
  if (!(await webEnsureSaved())) return;
  const result = await webExportNow();
  if (!result) return;
  showWebFrame(game, result.rev);
  window.open(webRuntimeUrl(), "_blank", "noopener");
}

async function exportWeb() {
  if (!game) return;
  if (!(await webEnsureSaved())) return;
  const result = await webExportNow();
  if (!result) return;
  showWebFrame(game, result.rev);
  webSetStatus(`exported to ${result.path}`);
}

async function downloadWebZip() {
  if (!game) return;
  if (!(await webEnsureSaved())) return;
  const link = document.createElement("a");
  link.href = `/api/webzip/${encodeURIComponent(game)}?t=${Date.now()}`;
  link.download = `${game}-web.zip`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  webSetStatus("downloading zip…");
}

if ($("webreload"))
  $("webreload").onclick = () => { webEnsureSaved().then((ok) => { if (ok) reloadWeb(); }); };
if ($("webnewtab")) $("webnewtab").onclick = openWebTab;
if ($("webexport")) $("webexport").onclick = exportWeb;
if ($("webzip")) $("webzip").onclick = downloadWebZip;
