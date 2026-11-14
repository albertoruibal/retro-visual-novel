"use strict";
// -------------------------------------------------------------- actions
async function save() {
  $("save").disabled = true;
  try {
    try {
      P = await api("PUT", "/api/project", P);
    } catch (e) {
      if (e.status !== 409) throw e;
      const ok = confirm(
        "the story file was changed on disk by another user or process since you " +
        "loaded it.\n\nOK: overwrite their changes with your version.\n" +
        "Cancel: keep your work and reload the game to see their edits.");
      if (!ok) return false;
      P = await api("PUT", "/api/project", Object.assign({}, P, { force: true }));
    }
    try { TARGETS = await api("GET", "/api/targets"); } catch { /* keep */ }
    dirty = false; renderAll();
    if (typeof refreshEmuSystems === "function") refreshEmuSystems();
    return true;
  } catch (e) { alert("save failed: " + e.message); return false; }
  finally { $("save").disabled = false; }
}

function refreshBuildTargets() {
  const sel = $("buildtarget");
  if (!sel) return;
  const ids = (typeof gameTargets === "function") ? gameTargets() : ["zx128"];
  const list = ((typeof systemTargets === "function") ? systemTargets() : [])
    .filter((t) => ids.includes(t.id));
  const prev = sel.value;
  sel.innerHTML = list.map((t) =>
    `<option value="${esc(t.id)}">${esc(t.label)}</option>`).join("");
  if (list.some((t) => t.id === prev)) sel.value = prev;
  const none = !list.length;
  sel.disabled = none;
  const btn = $("buildone");
  if (btn) btn.disabled = none;
}

async function runBuild(requested) {
  const explicit = Array.isArray(requested) && requested.length ? requested : null;
  await loadServerSettings();
  const tg = explicit ||
    ((typeof gameTargets === "function") ? gameTargets() : ["zx128"]);
  const needCc65 = tg.some((t) => t === "c64" || t === "nes" || t === "oric");
  const needZ88dk = tg.some((t) => t !== "c64" && t !== "nes" &&
                                    t !== "oric" && t !== "web");
  if (needZ88dk && !SERVER.z88dk_available) {
    const miss = (SERVER.z88dk_missing || []).join(", ");
    setBuildStatus(miss ? `z88dk incomplete — missing ${miss}`
                        : "z88dk not ready — see Settings", "bad");
    openServerSettings("z88dk");
    return;
  }
  if (needCc65 && !SERVER.cc65_available) {
    const miss = (SERVER.cc65_missing || []).join(", ");
    setBuildStatus(miss ? `cc65 incomplete — missing ${miss}`
                        : "cc65 not ready — see Settings", "bad");
    openServerSettings("cc65");
    return;
  }
  if (view === "raw" && rawDirty) { await saveRaw(); if (rawDirty) return; }
  else if (dirty && !(await save())) return;
  if (typeof gameTargets === "function" && !tg.length) {
    alert("Select at least one system in the Systems tab first.");
    return;
  }
  showBuildLog();
  $("buildlog").textContent = "starting…";
  setBuildStatus("building…");
  try {
    const r = await api("POST", "/api/build",
                        explicit ? { targets: explicit } : {});
    build = r.build;
    const tick = async () => {
      const b = await api("GET", "/api/build/" + build);
      $("buildlog").textContent = (b.log || []).join("\n") || b.status;
      $("buildlog").scrollTop = $("buildlog").scrollHeight;
      if (b.status === "running" || b.status === "queued") {
        setTimeout(tick, 1200);
      } else {
        let extra = "";
        if (b.targets) {
          extra = "\n\n" + Object.entries(b.targets).map(([id, t]) =>
            `[${id}] ${t.status}` +
            (t.seconds != null ? ` in ${t.seconds.toFixed(1)}s` : "") +
            (t.returncode != null ? " rc=" + t.returncode : "") +
            (t.error ? ": " + t.error : "")).join("\n");
        }
        $("buildlog").textContent += `\n[${b.status} rc=${b.returncode}]` + extra;
        setBuildStatus(b.status === "done" ? "done" : b.status,
                       b.status === "done" ? "ok" : "bad");
        refreshEmuSystems(true);
      }
    };
    tick();
  } catch (e) {
    $("buildlog").textContent = "build error: " + e.message;
    setBuildStatus("error", "bad");
    if (/cc65/i.test(e.message)) openServerSettings("cc65");
    else if (/z88dk/i.test(e.message)) openServerSettings("z88dk");
  }
}

