"use strict";
/* Electron main process for Retro Visual Novel.
 *
 * It boots the existing Python editor server (tools/editor/server.py) on a
 * loopback port, waits for it to answer /api/health, then loads it in a
 * BrowserWindow. The renderer keeps talking to the same JSON API, so the SPA,
 * JSSpeccy and Monaco are unchanged; the only native additions are the folder
 * picker (games open as folders) and remembering the open game folders.
 *
 * Layout:
 *   dev        engine root = the repository (this file's parent)
 *   packaged   engine root = <resources>/engine, Python = <resources>/python
 *
 * z88dk is not bundled: the build finds it via $Z88DK/$RVN_Z88DK, the path
 * saved in the editor Settings (z88dk_path), or a Snap install detected on Linux.
 */
const { app, BrowserWindow, Menu, dialog, ipcMain, nativeImage } = require("electron");
const { spawn, spawnSync } = require("child_process");
const http = require("http");
const net = require("net");
const fs = require("fs");
const path = require("path");

const APP_ID = "com.retrovisualnovel.editor";
const DEV_ROOT = path.resolve(__dirname, "..");
const ICON_PATH = path.join(app.getAppPath(), "build", "icon.png");
const WINDOW_ICON_SIZE = 192;

// Wayland resolves the dock/taskbar icon by matching the window's app_id to an
// installed .desktop file. Must be called before the `ready` event.
if (process.platform === "linux") app.setDesktopName(APP_ID);

function envFirst(...names) {
  for (const name of names) {
    const value = process.env[name];
    if (value) return value;
  }
  return "";
}

let serverProc = null;
let mainWindow = null;
let serverPort = null;
let quitting = false;

// --------------------------------------------------------------- settings
function settingsPath() {
  return path.join(app.getPath("userData"), "settings.json");
}

function readSettings() {
  try {
    return JSON.parse(fs.readFileSync(settingsPath(), "utf8")) || {};
  } catch {
    return {};
  }
}

function writeSettings(patch) {
  const next = { ...readSettings(), ...patch };
  try {
    fs.mkdirSync(path.dirname(settingsPath()), { recursive: true });
    fs.writeFileSync(settingsPath(), JSON.stringify(next, null, 2));
  } catch { /* non-fatal */ }
  return next;
}

// The product renames moved Electron's userData directory. Copy the previous
// settings once so the saved z88dk path and open game folders survive.
function migrateSettings() {
  const next = settingsPath();
  if (fs.existsSync(next)) return;
  for (const name of ["8-bit Visual Novel", "8-bit-visual-novel"]) {
    const old = path.join(app.getPath("appData"), name, "settings.json");
    try {
      if (!fs.existsSync(old)) continue;
      fs.mkdirSync(path.dirname(next), { recursive: true });
      fs.copyFileSync(old, next);
      return;
    } catch { /* try the next legacy location */ }
  }
}

// --------------------------------------------------------------- icon
function windowIcon() {
  const image = nativeImage.createFromPath(ICON_PATH);
  if (image.isEmpty()) return ICON_PATH;
  return image.resize({ width: WINDOW_ICON_SIZE, height: WINDOW_ICON_SIZE, quality: "best" });
}

// A bare AppImage installs nothing, so Wayland cannot match the window's app_id
// to a .desktop entry. Register a per-user entry + themed icon on first run.
function integrateAppImage() {
  if (process.platform !== "linux") return;
  const appImage = process.env.APPIMAGE;
  const appDir = process.env.APPDIR;
  if (!appImage || !appDir) return; // not an AppImage launch

  try {
    const dataHome = process.env.XDG_DATA_HOME || path.join(app.getPath("home"), ".local", "share");
    const iconDir = path.join(dataHome, "icons", "hicolor", "512x512", "apps");
    const appsDir = path.join(dataHome, "applications");
    const iconSrc = path.join(appDir, "usr", "share", "icons", "hicolor",
                              "512x512", "apps", "retro-visual-novel.png");
    if (!fs.existsSync(iconSrc)) return;

    fs.mkdirSync(iconDir, { recursive: true });
    fs.mkdirSync(appsDir, { recursive: true });
    fs.copyFileSync(iconSrc, path.join(iconDir, "retro-visual-novel.png"));

    const desktop = [
      "[Desktop Entry]",
      "Type=Application",
      "Name=Retro Visual Novel",
      "Comment=Editor + builder for the Retro Visual Novel creator",
      `Exec="${appImage}" --no-sandbox %U`,
      "Icon=retro-visual-novel",
      "Terminal=false",
      "Categories=Development;",
      `StartupWMClass=${APP_ID}`,
      "",
    ].join("\n");
    fs.writeFileSync(path.join(appsDir, `${APP_ID}.desktop`), desktop);

    spawnSync("gtk-update-icon-cache",
              ["-f", "-t", path.join(dataHome, "icons", "hicolor")],
              { stdio: "ignore" });
  } catch { /* best-effort: a missing dock icon must never block the app */ }
}

// Dev runs from the checkout, so Wayland also needs a throwaway desktop entry.
let devDesktopFile = null;
function registerDevDesktop() {
  if (process.platform !== "linux" || app.isPackaged) return;
  if (process.env.XDG_SESSION_TYPE !== "wayland" && !process.env.WAYLAND_DISPLAY) return;

  const icon = path.join(DEV_ROOT, "electron", "build", "icon.png");
  const dir = path.join(app.getPath("home"), ".local", "share", "applications");
  const file = path.join(dir, `${APP_ID}.desktop`);
  const contents = [
    "[Desktop Entry]",
    "Type=Application",
    "Name=Retro Visual Novel (dev)",
    `Icon=${icon}`,
    "Exec=retro-visual-novel-dev %U",
    `StartupWMClass=${APP_ID}`,
    "NoDisplay=true",
    "Categories=Development;",
    "",
  ].join("\n");
  try {
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(file, contents);
    devDesktopFile = file;
  } catch { /* best-effort: a missing icon must not block the dev run */ }
}

function unregisterDevDesktop() {
  if (!devDesktopFile) return;
  try { fs.rmSync(devDesktopFile); } catch { /* already gone */ }
  devDesktopFile = null;
}

// --------------------------------------------------------------- paths
function engineRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "engine")
    : DEV_ROOT;
}

// A venv/standalone Python can lay its interpreter out a few ways.
function pythonCandidates(base) {
  return [
    path.join(base, "bin", "python3"),       // unix venv / standalone
    path.join(base, "bin", "python"),         // unix alternative
    path.join(base, "python.exe"),            // win standalone at base
    path.join(base, "Scripts", "python.exe"), // win venv
  ];
}

function pythonExe() {
  if (app.isPackaged) {
    for (const c of pythonCandidates(path.join(process.resourcesPath, "python")))
      if (fs.existsSync(c)) return c;
  } else {
    // Dev: prefer the venv staged by scripts/prepare-python.js.
    for (const c of pythonCandidates(path.join(engineRoot(), ".venv")))
      if (fs.existsSync(c)) return c;
  }
  return process.platform === "win32" ? "python" : "python3";
}

// Locate the z88dk toolchain. Nothing is bundled, so an explicit
// Z88DK/RVN_Z88DK wins, then the path saved in the editor Settings
// (z88dk_path), then a Snap install. A configured-but-missing path is returned
// as-is so the build reports it instead of silently falling back.
function z88dkDir() {
  const envZ88dk = envFirst("RVN_Z88DK", "ZXAD_Z88DK");
  if (isZ88dkDir(process.env.Z88DK)) return process.env.Z88DK;
  if (isZ88dkDir(envZ88dk)) return envZ88dk;
  const stored = readSettings().z88dk_path;
  if (stored) return stored;
  const detected = detectSnapZ88dk();
  if (detected) return detected;
  return process.env.Z88DK || envZ88dk || "";
}

// The z88dk Snap keeps its tree at $SNAP (/snap/z88dk/current).
function snapZ88dkCandidates() {
  if (process.platform !== "linux") return [];
  const dirs = [];
  if (process.env.SNAP_NAME === "z88dk" && process.env.SNAP)
    dirs.push(process.env.SNAP);
  dirs.push("/snap/z88dk/current", "/var/lib/snapd/snap/z88dk/current");
  return dirs;
}

function detectSnapZ88dk() {
  return snapZ88dkCandidates().find(isZ88dkDir) || "";
}

function isZ88dkDir(dir) {
  return !!dir && (
    fs.existsSync(path.join(dir, "bin", "z88dk-z80asm")) ||
    fs.existsSync(path.join(dir, "bin", "zcc")) ||
    fs.existsSync(path.join(dir, "bin", "zcc.exe")));
}

// --------------------------------------------------------------- command line
// The desktop build can also act as a headless builder:
//
//   Retro Visual Novel.AppImage --build <game-folder> [--target zx,sms]
//   Retro Visual Novel.AppImage --build <game-folder> --all-targets
//   Retro Visual Novel.AppImage --list-targets
//
// This path never opens a window, so it works on a headless machine. It uses
// the bundled engine/Python and the same settings file as the GUI for z88dk.
const CLI_VERSION = require("./package.json").version;

function cliUsage() {
  return [
    `Retro Visual Novel ${CLI_VERSION}`,
    "",
    "Usage:",
    "  retro-visual-novel --build <game-folder> [options]",
    "  retro-visual-novel --list-targets",
    "",
    "Options:",
    "  -b, --build <folder>   game folder (or its game.md); repeat for several games",
    "  -t, --target <list>    comma-separated targets (default: those selected in game.md)",
    "      --all-targets      build every target regardless of the game's selection",
    "      --list-targets     list the target plugins and their availability",
    "  -h, --help             show this help",
    "  -V, --version          show the app version",
    "",
    "z88dk is read from $Z88DK, then the editor Settings, then a Snap install.",
    "Outputs stay in each game folder (the .tap/.sna/.sms/.rom/.dsk/.gbc files).",
  ].join("\n");
}

function cliTargets(value) {
  return String(value || "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
}

function parseCli(argv) {
  const cli = { build: [], targets: [], allTargets: false, listTargets: false,
                help: false, version: false, error: "" };
  let saw = false;
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--build" || arg === "-b") {
      saw = true;
      const value = argv[++i];
      if (value === undefined) { cli.error = "--build needs a game folder"; break; }
      cli.build.push(value);
    } else if (arg.startsWith("--build=")) {
      saw = true;
      cli.build.push(arg.slice("--build=".length));
    } else if (arg === "--target" || arg === "--targets" || arg === "-t") {
      saw = true;
      const value = argv[++i];
      if (value === undefined) { cli.error = "--target needs a target list"; break; }
      cli.targets.push(...cliTargets(value));
    } else if (arg.startsWith("--target=")) {
      saw = true;
      cli.targets.push(...cliTargets(arg.slice("--target=".length)));
    } else if (arg === "--all-targets" || arg === "--all") {
      saw = true;
      cli.allTargets = true;
    } else if (arg === "--list-targets") {
      saw = true;
      cli.listTargets = true;
    } else if (arg === "--help" || arg === "-h") {
      saw = true;
      cli.help = true;
    } else if (arg === "--version" || arg === "-V") {
      saw = true;
      cli.version = true;
    }
  }
  return saw ? cli : null;
}

function cliGameDir(value) {
  if (!value) return "";
  const p = path.resolve(process.cwd(), value);
  try {
    const st = fs.statSync(p);
    if (st.isFile() && path.basename(p) === "game.md") return path.dirname(p);
    if (st.isDirectory() && fs.existsSync(path.join(p, "game.md"))) return p;
  } catch { /* handled below */ }
  return "";
}

function cliEnv(game, z88dk) {
  const env = { ...process.env, RVN_SETTINGS: settingsPath() };
  if (z88dk) env.Z88DK = z88dk;
  if (game) env.RVN_GAME = game;
  delete env.RVN_GAMES;
  delete env.ZXAD_GAMES;
  delete env.ZXAD_GAME;
  delete env.ZXAD_SETTINGS;
  return env;
}

function runCli(cli) {
  if (cli.error) {
    console.error(`rvn: ${cli.error}\n`);
    console.error(cliUsage());
    return 2;
  }
  if (!cli.build.length && !cli.listTargets) {
    console.error("rvn: no --build folder given\n");
    console.error(cliUsage());
    return 2;
  }
  const py = pythonExe();
  const root = engineRoot();
  const script = path.join(root, "tools", "build.py");
  if (!fs.existsSync(script)) {
    console.error(`rvn: build tool not found at ${script}`);
    return 1;
  }

  const z88dk = process.env.Z88DK || z88dkDir();
  if (cli.listTargets) {
    const r = spawnSync(py, [script, "list-targets"],
      { cwd: root, env: cliEnv("", z88dk), stdio: "inherit" });
    if (r.error) { console.error(`rvn: ${r.error.message}`); return 1; }
    return r.status || 0;
  }

  if (!z88dk || !isZ88dkDir(z88dk)) {
    console.error("rvn: no usable z88dk found.");
    console.error("Set $Z88DK, or choose the toolchain in the editor's Settings first.");
    return 1;
  }

  let failed = 0;
  for (const value of cli.build) {
    const game = cliGameDir(value);
    if (!game) {
      console.error(`rvn: not a game folder (no game.md): ${value}`);
      failed++;
      continue;
    }
    const args = [script, "build", game];
    if (cli.allTargets) args.push("--all");
    else if (cli.targets.length) args.push(...cli.targets);
    console.log(`\n=== ${path.basename(game)} ===`);
    const r = spawnSync(py, args, { cwd: root, env: cliEnv(game, z88dk),
                                    stdio: "inherit" });
    if (r.error) {
      console.error(`rvn: ${r.error.message}`);
      failed++;
    } else if (r.status) {
      failed++;
    }
  }
  return failed ? 1 : 0;
}

function serverEnv(port, games) {
  const env = {
    ...process.env,
    EDITOR_HOST: "127.0.0.1",
    EDITOR_PORT: String(port),
  };
  const z88dk = process.env.Z88DK || z88dkDir();
  if (z88dk) env.Z88DK = z88dk;
  env.RVN_SETTINGS = settingsPath();       // share UI settings + open games
  // Reopen every remembered game folder at startup (the SPA restores which one
  // was active from its own session; the server just needs the set).
  if (games && games.length) env.RVN_GAMES = JSON.stringify(games);
  // The desktop app is the source of truth for these; do not let legacy values
  // inherited from the shell confuse the server.
  delete env.ZXAD_SETTINGS;
  delete env.ZXAD_GAMES;
  delete env.ZXAD_GAME;
  return env;
}

// --------------------------------------------------------------- helpers
function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

function httpOk(port) {
  return new Promise((resolve) => {
    const req = http.get({
      host: "127.0.0.1", port, path: "/api/health", timeout: 1000,
    }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

async function waitForHealth(port, tries = 100) {
  for (let i = 0; i < tries; i++) {
    if (serverProc && serverProc.exitCode !== null) return false;
    if (await httpOk(port)) return true;
    await new Promise((r) => setTimeout(r, 150));
  }
  return false;
}

// Is `p` a game folder (contains a game.md)?
function isGameDir(p) {
  try {
    return fs.statSync(path.join(p, "game.md")).isFile();
  } catch {
    return false;
  }
}

// The game folders to reopen at startup: every remembered open folder that
// still exists, else the last opened one (an install from before multi-game).
function rememberedGames(settings) {
  const out = [];
  const seen = new Set();
  for (const p of (Array.isArray(settings.openGames) ? settings.openGames : [])) {
    if (typeof p === "string" && isGameDir(p) && !seen.has(p)) {
      seen.add(p);
      out.push(p);
    }
  }
  if (!out.length) {
    const last = settings.lastGame || settings.activeGame;
    if (typeof last === "string" && isGameDir(last)) out.push(last);
  }
  return out;
}

// --------------------------------------------------------------- server
async function startServer() {
  const root = engineRoot();
  const py = pythonExe();
  const port = await findFreePort();
  const settings = readSettings();
  const games = rememberedGames(settings);

  const env = serverEnv(port, games);
  console.log(`[rvn] engine: ${root}`);
  console.log(`[rvn] python: ${py}`);
  console.log(`[rvn] z88dk: ${env.Z88DK || "(not found; Build will need one on PATH)"}`);
  if (games.length) console.log(`[rvn] open games: ${games.join(", ")}`);

  serverProc = spawn(py, [path.join(root, "tools", "editor", "server.py")], {
    cwd: root,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  serverProc.stdout.on("data", (d) => process.stdout.write("[server] " + d));
  serverProc.stderr.on("data", (d) => process.stderr.write("[server] " + d));
  serverProc.on("exit", (code, signal) => {
    serverProc = null;
    if (!quitting) {
      dialog.showErrorBox("Editor server stopped",
        `The editor server exited unexpectedly (code ${code}, signal ${signal}).`);
      app.quit();
    }
  });

  if (!await waitForHealth(port)) {
    throw new Error(
      `The editor server did not start (python: ${py}).\n` +
      `Set PATH/Z88DK or run \`npm run start\` from a machine with Python 3.`);
  }
  return port;
}

function stopServer() {
  quitting = true;
  if (!serverProc) return;
  const pid = serverProc.pid;
  try {
    if (process.platform === "win32") {
      // Kill the whole tree: the server may have a build (zcc/z80asm) running.
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      serverProc.kill("SIGTERM");
    }
  } catch { /* already gone */ }
  serverProc = null;
}

// --------------------------------------------------------------- window
function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1320, height: 880, minWidth: 900, minHeight: 600,
    title: "Retro Visual Novel",
    icon: windowIcon(),
    backgroundColor: "#191c22",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });
  mainWindow.on("closed", () => { mainWindow = null; });
  mainWindow.loadURL(`http://127.0.0.1:${port}`);
  if (envFirst("RVN_SMOKE", "ZXAD_SMOKE")) {
    mainWindow.webContents.once("did-finish-load", async () => {
      try {
        const keys = await mainWindow.webContents.executeJavaScript(
          "Object.keys(window.rvn || {})");
        console.log("SMOKE: window.rvn =", JSON.stringify(keys));
      } catch (e) {
        console.log("SMOKE: bridge check failed:", e && e.message);
      }
      console.log("SMOKE: window loaded", mainWindow.webContents.getURL());
      const remember = envFirst("RVN_SMOKE_REMEMBER", "ZXAD_SMOKE_REMEMBER");
      if (remember) {
        await mainWindow.webContents.executeJavaScript(
          `window.rvn.rememberFolder(${JSON.stringify(remember)})`);
      }
      console.log("SMOKE: settings", settingsPath(), JSON.stringify(readSettings()));
      setTimeout(() => app.quit(), 500);
    });
  }
}

function buildMenu() {
  const isMac = process.platform === "darwin";
  const template = [
    ...(isMac ? [{ role: "appMenu" }] : []),
    {
      label: "File",
      submenu: [
        {
          label: "Open Game Folder…",
          accelerator: "CmdOrCtrl+O",
          click: () => mainWindow && mainWindow.webContents.send("rvn:open-folder-request"),
        },
        { type: "separator" },
        isMac ? { role: "close" } : { role: "quit" },
      ],
    },
    { role: "editMenu" },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    { role: "windowMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// --------------------------------------------------------------- ipc
ipcMain.handle("rvn:open-folder", async () => {
  const r = await dialog.showOpenDialog(mainWindow, {
    title: "Open a game folder",
    properties: ["openDirectory"],
  });
  if (r.canceled || !r.filePaths.length) return null;
  return r.filePaths[0];
});

ipcMain.handle("rvn:new-folder", async () => {
  const r = await dialog.showOpenDialog(mainWindow, {
    title: "Choose where to create the game",
    buttonLabel: "Create here",
    properties: ["openDirectory", "createDirectory"],
  });
  if (r.canceled || !r.filePaths.length) return null;
  return r.filePaths[0];
});

ipcMain.handle("rvn:pick-dir", async () => {
  const r = await dialog.showOpenDialog(mainWindow, {
    title: "Select a folder",
    properties: ["openDirectory"],
  });
  if (r.canceled || !r.filePaths.length) return null;
  return r.filePaths[0];
});

ipcMain.handle("rvn:remember-folder", (_e, p) => {
  if (typeof p === "string" && p) writeSettings({ lastGame: p });
  return true;
});

// Remember all open game folders + the active one, so every tab reopens.
ipcMain.handle("rvn:remember-games", (_e, payload) => {
  const folders = (payload && Array.isArray(payload.folders) ? payload.folders : [])
    .filter((p) => typeof p === "string" && p);
  const active = payload && typeof payload.active === "string" ? payload.active : "";
  writeSettings({ openGames: folders, activeGame: active,
                  lastGame: active || folders[0] || "" });
  return true;
});

ipcMain.handle("rvn:app-info", () => ({
  platform: process.platform,
  version: app.getVersion(),
  packaged: app.isPackaged,
}));

// --------------------------------------------------------------- lifecycle
// Some Linux/container setups need the Chromium sandbox disabled; opt in with
// RVN_NO_SANDBOX=1. Must be set before the app becomes ready.
if (process.platform === "linux" && envFirst("RVN_NO_SANDBOX", "ZXAD_NO_SANDBOX")) {
  app.commandLine.appendSwitch("no-sandbox");
}

const cli = parseCli(process.argv.slice(1));
if (cli) {
  if (cli.help) {
    console.log(cliUsage());
    process.exit(0);
  }
  if (cli.version) {
    console.log(CLI_VERSION);
    process.exit(0);
  }
  process.exit(runCli(cli));
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    migrateSettings();
    integrateAppImage();
    registerDevDesktop();
    buildMenu();
    try {
      serverPort = await startServer();
      createWindow(serverPort);
    } catch (e) {
      dialog.showErrorBox("Cannot start the editor", String((e && e.message) || e));
      app.quit();
    }
  });

  app.on("activate", () => {
    // macOS: recreate a window on the still-running server.
    if (BrowserWindow.getAllWindows().length === 0 && serverProc && serverPort) {
      createWindow(serverPort);
    }
  });
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
app.on("before-quit", stopServer);
app.on("will-quit", unregisterDevDesktop);
process.on("exit", stopServer);
