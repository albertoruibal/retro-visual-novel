"use strict";
// ------------------------------------------------------------------ raw
/* Source tab: edit the selected game's game.md verbatim in a vendored Monaco
 * (markdown highlighting, line numbers). Monaco is loaded lazily the first
 * time the tab opens, so the rest of the editor never pays for it. Saves go
 * through /api/raw, which validates with the shared parser and keeps a .bak;
 * on success the project is reloaded so the structured tabs match.
 *
 * The editor's own dark theme ("rvn-dark") mirrors the app's CSS variables,
 * and the codicon font + workers resolve from /monaco/vs (see server.py). */
const RAW_THEME = {
  base: "vs-dark", inherit: true, rules: [
    { token: "comment", foreground: "7b8598", fontStyle: "italic" },
    { token: "keyword", foreground: "7c6cff" },
    { token: "string", foreground: "3ddc84" },
    { token: "number", foreground: "f5c84b" },
    { token: "tag", foreground: "5b9dff" },
    { token: "strong", fontStyle: "bold" },
    { token: "emphasis", fontStyle: "italic" },
  ],
  colors: {
    "editor.background": "#10131a",
    "editor.foreground": "#e9edf5",
    "editorLineNumber.foreground": "#4a5468",
    "editorLineNumber.activeForeground": "#aab4c7",
    "editorCursor.foreground": "#5b9dff",
    "editor.selectionBackground": "#2b3b57",
    "editor.lineHighlightBackground": "#161a23",
    "editorWidget.background": "#161a23",
    "editorWidget.border": "#2a3140",
    "editorIndentGuide.background": "#1d222d",
  },
};

/* Load Monaco's AMD bundle once. The classic loader defines a global
 * `require`, so the tab works without a bundler; index.html loads loader.js
 * from /monaco/vs where the server serves the nested assets. */
function ensureMonaco() {
  if (monacoP) return monacoP;
  monacoP = new Promise((resolve, reject) => {
    if (typeof self.require === "undefined" || !self.require.config) {
      reject(new Error("Monaco loader not available"));
      return;
    }
    self.MonacoEnvironment = {
      getWorkerUrl: () => "/monaco/vs/base/worker/workerMain.js",
    };
    self.require.config({ paths: { vs: "/monaco/vs" } });
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "/monaco/vs/editor/editor.main.css";
    document.head.appendChild(css);
    self.require(["vs/editor/editor.main"], (monaco) => {
      monaco.editor.defineTheme("rvn-dark", RAW_THEME);
      /* Ctrl/Cmd+click a scene/art/song/item/flag/group reference to jump to
       * its definition. The link map comes from the shared parser via the
       * validate response (rawOutline), so no parsing happens here. */
      monaco.languages.registerDefinitionProvider("markdown", {
        provideDefinition(model, position) {
          const l = rawOutline.find((x) =>
            position.lineNumber === x.line &&
            position.column >= x.startColumn && position.column <= x.endColumn);
          if (!l) return null;
          return {
            uri: model.uri,
            range: new monaco.Range(l.defLine, l.defStartColumn,
                                    l.defLine, l.defEndColumn),
          };
        },
      });
      monacoApi = monaco;
      resolve(monaco);
    }, reject);
  });
  return monacoP;
}

/* Create the Source editor on first use. Ctrl/Cmd+S saves, matching the old
 * textarea; the change event only reports dirtiness (never the reverse). */
async function createRawEditor() {
  const monaco = await ensureMonaco();
  if (rawEditor) return rawEditor;
  rawEditor = monaco.editor.create($("raweditor"), {
    value: "",
    language: "markdown",
    theme: "rvn-dark",
    automaticLayout: true,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    wordWrap: "off",
    fontSize: 12.5,
    fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace',
    tabSize: 2,
    renderWhitespace: "none",
  });
  rawEditor.onDidChangeModelContent(() => {
    if (suppressRawChange) return;
    markRawDirty();
    scheduleRawCheck();
  });
  rawEditor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, saveRaw);
  return rawEditor;
}

/* Draw the validation issues as Monaco squiggles: an error/warn marker on its
 * line plus a red gutter strip, so the offending line is obvious at a glance.
 * A file-level issue (no line) is pinned to line 1. */
let rawDecorations = [];   // Monaco whole-line decorations for error lines

function paintRawMarkers() {
  if (!rawEditor || !monacoApi) return;
  const model = rawEditor.getModel();
  if (!model) return;
  const sev = monacoApi.MarkerSeverity;
  const clamp = (n) => Math.max(1, Math.min(model.getLineCount(), n || 1));
  const markers = rawIssues.map((it) => {
    const line = clamp(it.line);
    const section = it.section + (it.id ? " " + it.id : "");
    return {
      severity: it.level === "error" ? sev.Error : sev.Warning,
      message: `${it.level} · ${section}: ${it.msg}`,
      startLineNumber: line, startColumn: 1,
      endLineNumber: line, endColumn: model.getLineMaxColumn(line),
      source: "game.md",
    };
  });
  monacoApi.editor.setModelMarkers(model, "game.md", markers);
  // Tint and gutter-mark the whole error line (warnings are marker-only, so
  // the red rows stand out). Classnames are styled in graph.css.
  const seen = new Set();
  const decos = [];
  for (const it of rawIssues) {
    if (it.level !== "error") continue;
    const line = clamp(it.line);
    if (seen.has(line)) continue;
    seen.add(line);
    decos.push({
      range: new monacoApi.Range(line, 1, line, 1),
      options: { isWholeLine: true, className: "raw-err-line",
                 linesDecorationsClassName: "raw-err-gutter" },
    });
  }
  rawDecorations = rawEditor.deltaDecorations(rawDecorations, decos);
  const errs = rawIssues.filter(i => i.level === "error").length;
  const warns = rawIssues.length - errs;
  if (errs) {
    const first = rawIssues.find(i => i.level === "error");
    const line = Math.max(1, first.line || 1);
    rawEditor.revealLineInCenterIfOutsideViewport(line);
    renderRawStatus(`${errs} error${errs > 1 ? "s" : ""} — line ${line}` +
      (warns ? `, ${warns} warning${warns > 1 ? "s" : ""}` : ""), "bad");
  } else if (warns) {
    renderRawStatus(`${warns} warning${warns > 1 ? "s" : ""}`, "");
  } else {
    renderRawStatus(rawDirty ? "unsaved changes — no errors" : "saved", "ok");
  }
}

function clearRawMarkers() {
  rawIssues = [];
  rawOutline = [];
  if (rawEditor && monacoApi) {
    const model = rawEditor.getModel();
    if (model) monacoApi.editor.setModelMarkers(model, "game.md", []);
    rawDecorations = rawEditor.deltaDecorations(rawDecorations, []);
  }
}

/* Live checker: after a pause in typing, lint the buffer server-side and mark
 * the lines. Failures are silent (the tab must still work when offline); an
 * explicit Save surfaces the same issues with an alert. */
async function checkRaw(force) {
  if (!game || !rawEditor || (!rawDirty && !force)) return;
  const text = rawEditor.getValue();
  try {
    const r = await api("POST", "/api/validate", { text });
    if (rawEditor.getValue() !== text) return;   // buffer moved on; discard
    rawIssues = r.issues || [];
    rawOutline = r.outline || [];
    paintRawMarkers();
  } catch { /* lint is best-effort */ }
}

function scheduleRawCheck() {
  clearTimeout(rawCheckTimer);
  rawCheckTimer = setTimeout(checkRaw, 500);
}

function setRawValue(text) {
  suppressRawChange = true;
  rawEditor.setValue(text == null ? "" : text);
  suppressRawChange = false;
}

function clearRawDirty() {
  rawDirty = false;
  $("rawbody").classList.remove("raw-dirty");
  clearRawMarkers();
}

function renderRawStatus(msg, cls) {
  const el = $("rawstatus");
  if (!el) return;
  el.textContent = msg || "";
  el.className = "status " + (cls || "");
}

function markRawDirty() {
  rawDirty = true;
  $("rawbody").classList.add("raw-dirty");
  renderRawStatus("unsaved changes", "bad");
}

async function loadRaw() {
  if (!game) return;
  renderRawStatus("loading…");
  try {
    const ed = await createRawEditor();
    const r = await api("GET", "/api/raw");
    setRawValue(r.text);
    rawRevision = r.revision || null;
    clearRawDirty();
    ed.layout();
    renderRawStatus("saved", "ok");
    checkRaw(true);              // surface any pre-existing errors on the lines
  } catch (e) {
    if (rawEditor) setRawValue("");
    clearRawDirty();
    renderRawStatus(e.message, "bad");
  }
}

async function saveRaw() {
  if (!game) return;
  const btn = $("rawsave");
  btn.disabled = true;
  renderRawStatus("saving…");
  try {
    const body = { text: rawEditor ? rawEditor.getValue() : "",
                   revision: rawRevision };
    let r;
    try {
      r = await api("PUT", "/api/raw", body);
    } catch (e) {
      if (e.status !== 409) throw e;
      const ok = confirm(
        "game.md was changed on disk by another user or process since you " +
        "opened the Source tab.\n\nOK: overwrite their changes with your " +
        "version.\nCancel: keep this buffer; Reload to load theirs.");
      if (!ok) {
        renderRawStatus("not saved — game.md changed on disk", "bad");
        return;
      }
      r = await api("PUT", "/api/raw",
                    Object.assign({}, body, { force: true }));
    }
    rawRevision = r.revision || null;
    clearRawDirty();
    await load();
    renderRawStatus("saved — reloaded project", "ok");
  } catch (e) {
    // A validation failure returns the issues with their lines: mark them and
    // jump to the first, instead of only a modal that does not say where.
    if (e.body && Array.isArray(e.body.issues) && e.body.issues.length) {
      rawIssues = e.body.issues;
      paintRawMarkers();
    } else {
      renderRawStatus("save failed", "bad");
      alert("save failed: " + e.message);
    }
  } finally {
    btn.disabled = false;
  }
}

