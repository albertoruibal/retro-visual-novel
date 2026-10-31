"use strict";
/* Stage the editor's Python runtime and dependencies.
 *
 * The editor server is stdlib-only, but the build tools it drives need Pillow
 * and numpy (tools/zxart.py) and the spectrumizer CLI (Music tab).
 *
 *   dev        <root>/.venv          a virtualenv the Electron shell uses
 *                                    while developing (see pythonExe())
 *   packaged   <dir>/python          a *self-contained* CPython prefix plus
 *                                    the deps, from --stage <dir>
 *
 * The dev venv may still point at a system interpreter, but packaging must not:
 * a standalone CPython (installed by `uv python install 3.13`) is copied whole
 * with the requirements installed into it, so the app runs without any system
 * Python. If no standalone interpreter is found we fall back to copying the
 * venv (with a warning).
 *
 * Uses `uv` when available (fast, and `--relocatable` for the venv), otherwise
 * the stdlib `venv` module + pip.
 *
 * Usage:
 *   node electron/scripts/prepare-python.js [--stage <dir>]
 */
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = process.env.RVN_ROOT || process.env.ZXAD_ROOT
  ? path.resolve(process.env.RVN_ROOT || process.env.ZXAD_ROOT)
  : path.resolve(__dirname, "..", "..");
const VENV = path.join(ROOT, ".venv");
const REQS = path.join(ROOT, "tools", "requirements.txt");

function has(cmd) {
  const r = spawnSync(cmd, ["--version"], { stdio: "ignore" });
  return r.status === 0;
}

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: "inherit", cwd: ROOT, ...opts });
  if (r.error) {
    console.error(`cannot run ${cmd}: ${r.error.message}`);
    process.exit(1);
  }
  if (r.status !== 0) {
    console.error(`failed (${r.status}): ${cmd} ${args.join(" ")}`);
    process.exit(r.status || 1);
  }
}

// The interpreter inside a venv or a standalone CPython prefix.
function runtimePython(dir) {
  const win = process.platform === "win32";
  const cands = [
    path.join(dir, "bin", "python3"),        // unix venv / standalone
    path.join(dir, "bin", "python"),          // unix alternative
    path.join(dir, "python.exe"),             // win standalone at base
    path.join(dir, "Scripts", "python.exe"),  // win venv
  ];
  for (const c of cands) if (fs.existsSync(c)) return c;
  return win ? path.join(dir, "python.exe") : path.join(dir, "bin", "python3");
}

// Locate a uv-managed standalone CPython 3.13 prefix, if one is installed.
function managedPython() {
  const bases = [];
  if (process.env.UV_PYTHON_INSTALL_DIR) bases.push(process.env.UV_PYTHON_INSTALL_DIR);
  const home = process.env.HOME || process.env.USERPROFILE;
  if (home) bases.push(
    path.join(home, ".local", "share", "uv", "python"),
    path.join(home, "AppData", "Roaming", "uv", "python"),
    path.join(home, "Library", "Application Support", "uv", "python"));
  for (const base of bases) {
    let names;
    try { names = fs.readdirSync(base); } catch { continue; }
    const cps = names.filter((n) => /^cpython-3\.13/.test(n)).sort();
    if (!cps.length) continue;
    try { return fs.realpathSync(path.join(base, cps[cps.length - 1])); }
    catch { /* keep looking */ }
  }
  return null;
}

function ensureVenv() {
  const py = runtimePython(VENV);
  if (fs.existsSync(py)) {
    console.log("[prepare-python] reusing", VENV);
  } else {
    if (fs.existsSync(VENV)) {
      console.log("[prepare-python] removing incomplete", VENV);
      fs.rmSync(VENV, { recursive: true, force: true });
    }
    if (has("uv")) {
      console.log("[prepare-python] uv venv", VENV);
      run("uv", ["venv", "--relocatable", "--seed", "--python", "3.13", VENV]);
    } else {
      const base = process.platform === "win32" ? "python" : "python3";
      console.log("[prepare-python]", base, "-m venv", VENV);
      run(base, ["-m", "venv", VENV]);
    }
  }
  if (has("uv")) {
    run("uv", ["pip", "install", "--python", runtimePython(VENV), "-r", REQS]);
  } else {
    run(runtimePython(VENV), ["-m", "pip", "install", "-r", REQS]);
  }
  console.log("[prepare-python] ready:", runtimePython(VENV));
}

function installInto(py) {
  if (has("uv")) {
    run("uv", ["pip", "install", "--python", py,
               "--break-system-packages", "-r", REQS]);
  } else {
    run(py, ["-m", "pip", "install", "--break-system-packages", "-r", REQS]);
  }
}

// Build a self-contained <dst> runtime for packaging.
function stageRuntime(dst) {
  const managed = managedPython();
  fs.rmSync(dst, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(dst), { recursive: true });

  if (managed) {
    console.log("[prepare-python] standalone CPython:", managed);
    fs.cpSync(managed, dst, {
      recursive: true, dereference: false, verbatimSymlinks: true,
    });
    installInto(runtimePython(dst));
    console.log("[prepare-python] staged self-contained runtime:", dst);
    return;
  }

  console.warn("[prepare-python] WARNING: no standalone CPython found; " +
               "staging the venv, which still needs a system interpreter at " +
               "its base. Run `uv python install 3.13` to bundle one.");
  fs.cpSync(VENV, dst, {
    recursive: true, dereference: false, verbatimSymlinks: true,
  });
  console.log("[prepare-python] staged venv:", dst);
}

function main() {
  const args = process.argv.slice(2);
  const si = args.indexOf("--stage");
  const stageDir = si >= 0 ? args[si + 1] : null;

  if (!fs.existsSync(REQS)) {
    console.error(`missing ${REQS}`);
    process.exit(1);
  }

  ensureVenv();
  if (stageDir) stageRuntime(path.join(path.resolve(stageDir), "python"));
}

main();
