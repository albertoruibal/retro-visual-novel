"use strict";
/* Preload: the only native surface the SPA sees. Exposes a tiny, explicit API
 * on window.rvn so the renderer keeps its contextIsolation/nodeIntegration
 * locked down. A plain browser (no Electron) simply has no window.rvn and the
 * SPA falls back to path prompts. */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("rvn", {
  // Native folder pickers.
  openFolder: () => ipcRenderer.invoke("rvn:open-folder"),
  newFolder: () => ipcRenderer.invoke("rvn:new-folder"),
  // Generic directory picker (e.g. the z88dk toolchain path).
  pickDir: () => ipcRenderer.invoke("rvn:pick-dir"),
  // Persist the opened game so it reopens on the next launch.
  rememberFolder: (p) => ipcRenderer.invoke("rvn:remember-folder", p),
  // Persist every open game folder plus the active one (multi-game tabs).
  rememberGames: (folders, active) =>
    ipcRenderer.invoke("rvn:remember-games", { folders, active }),
  appInfo: () => ipcRenderer.invoke("rvn:app-info"),
  // File -> Open Game Folder… menu item.
  onOpenFolderRequest: (cb) =>
    ipcRenderer.on("rvn:open-folder-request", () => cb()),
});
