"use strict";
// -------------------------------------------------------------- Web Player
/* The Emulator tab's Web Player previews the exported combined player.  The
 * export itself (story runtime, selected emulators, downloadable files and
 * rendered music) is a build step in tools/webgame.py; the server only writes
 * <game>/web/ and serves those files.  Pending edits are saved before an
 * export or preview.  The top-bar Export player button drives playerExport(). */

let playerLoadedGame = null;
let playerLoadedRev = null;

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
    if (warnings.length) console.warn("player export:\n" + warnings.join("\n"));
    return result;
  } catch (e) {
    console.error("player export failed:", e);
    return null;
  }
}

async function playerExport() {
  if (!game || playerStarting) return;
  const button = $("exportplayer");
  playerStarting = true;
  try {
    if (!(await playerEnsureSaved())) return;
    if (button) { button.disabled = true; button.textContent = "Exporting…"; }
    const result = await playerExportNow();
    if (!result) {
      alert("Export failed — see the browser console for details.");
      return;
    }
    if (typeof reloadPlayerPreview === "function") reloadPlayerPreview();
  } finally {
    playerStarting = false;
    if (button) { button.disabled = false; button.textContent = "Export player"; }
  }
}

if ($("exportplayer")) $("exportplayer").onclick = playerExport;
