"use strict";
// -------------------------------------------------------------- web player
/* The Emulator tab's Web player previews the exported combined player.  The
 * export itself (story runtime, selected emulators, downloadable files and
 * rendered music) is a build step in tools/webgame.py; the server only writes
 * <game>/web/ and serves those files.  Pending edits are saved before an
 * export or preview. */

let playerLoadedGame = null;
let playerLoadedRev = null;

function playerSetStatus(message, bad) {
  const el = $("emustatus");
  if (!el) return;
  el.textContent = message || "";
  el.className = "status " + (bad ? "bad" : "");
}

async function playerEnsureSaved() {
  if (view === "raw" && rawDirty) {
    await saveRaw();
    if (rawDirty) return false;
  } else if (dirty && !(await save())) {
    return false;
  }
  return true;
}

function playerUrl(embed) {
  if (!game) return "";
  const suffix = embed ? "?embed=1&t=" : "?t=";
  return `/play/${encodeURIComponent(game)}/${suffix}${Date.now()}`;
}

async function playerExportNow() {
  if (!game) return null;
  try {
    const result = await api("POST", "/api/web_export", {});
    playerLoadedGame = game;
    playerLoadedRev = result.rev || null;
    const warnings = result.warnings || [];
    const systems = (result.systems || []).length;
    playerSetStatus(
      `exported ${systems} system${systems === 1 ? "" : "s"}` +
      (warnings.length ? ` · ${warnings.length} warning${warnings.length === 1 ? "" : "s"}` : ""),
      false);
    if (warnings.length) console.warn("player export:\n" + warnings.join("\n"));
    return result;
  } catch (e) {
    playerSetStatus("export failed: " + e.message, true);
    return null;
  }
}

async function playerExport() {
  if (!(await playerEnsureSaved())) return;
  const result = await playerExportNow();
  if (result) playerSetStatus(`exported to ${result.path}`);
}

async function playerDownloadZip() {
  if (!(await playerEnsureSaved())) return;
  playerSetStatus("exporting zip…");
  const link = document.createElement("a");
  link.href = `/api/webzip/${encodeURIComponent(game)}?t=${Date.now()}`;
  link.download = `${game}-web.zip`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  playerSetStatus("downloading zip…");
}

async function playerOpen() {
  if (!game) return;
  if (!(await playerEnsureSaved())) return;
  const result = await playerExportNow();
  if (!result) return;
  window.open(playerUrl(false), "_blank", "noopener");
}

if ($("emuplayer")) $("emuplayer").onclick = playerExport;
if ($("emuzip")) $("emuzip").onclick = playerDownloadZip;
if ($("emuopen")) $("emuopen").onclick = playerOpen;
