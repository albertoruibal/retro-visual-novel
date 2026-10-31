"use strict";
/* Assemble electron/dist-resources/{engine,python} for packaging.
 *
 * electron-builder copies these to <resources>/{engine,python} (see the
 * "extraResources" block in package.json), which is exactly what main.js's
 * engineRoot()/pythonExe() look for in a packaged app.
 *
 *   engine   src/, vendor/, tools/ and docs/ (the server, build tools, SPA
 *            and the authoring documentation)
 *   python   the .venv staged by prepare-python.js
 *
 * z88dk is intentionally not bundled: the user points the editor at a toolchain
 * (Settings -> Build toolchain) or $Z88DK/RVN_Z88DK at runtime.
 *
 * Usage: node electron/scripts/bundle.js
 */
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = process.env.RVN_ROOT || process.env.ZXAD_ROOT
  ? path.resolve(process.env.RVN_ROOT || process.env.ZXAD_ROOT)
  : path.resolve(__dirname, "..", "..");
const OUT = path.join(__dirname, "..", "dist-resources");

const SKIP = new Set(["__pycache__", ".state.json", "out", ".venv", ".git"]);

function copyEngine() {
  const dst = path.join(OUT, "engine");
  fs.rmSync(dst, { recursive: true, force: true });
  fs.mkdirSync(dst, { recursive: true });
  for (const name of ["src", "vendor", "tools", "docs"]) {
    const from = path.join(ROOT, name);
    if (!fs.existsSync(from)) throw new Error(`missing ${from}`);
    fs.cpSync(from, path.join(dst, name), {
      recursive: true,
      dereference: false,
      verbatimSymlinks: true,
      filter: (src) => !SKIP.has(path.basename(src)),
    });
  }
  console.log("[bundle] engine ->", dst);
}

function runScript(name) {
  const r = spawnSync(process.execPath,
    [path.join(__dirname, name), "--stage", OUT],
    { stdio: "inherit", cwd: ROOT });
  if (r.status !== 0) process.exit(r.status || 1);
}

function main() {
  fs.mkdirSync(OUT, { recursive: true });
  copyEngine();
  runScript("prepare-python.js");
  console.log("[bundle] resources ready in", OUT);
}

main();
