"use strict";
// -------------------------------------------------------------- actions
async function save() {
  $("save").disabled = true;
  try {
    P = await api("PUT", "/api/project", P);
    try { TARGETS = await api("GET", "/api/targets"); } catch { /* keep */ }
    dirty = false; renderAll();
    if (typeof refreshEmuSystems === "function") refreshEmuSystems();
    if (view === "web" && typeof reloadWeb === "function") reloadWeb();
    return true;
  } catch (e) { alert("save failed: " + e.message); return false; }
  finally { $("save").disabled = false; }
}

async function runBuild() {
  await loadServerSettings();
  if (!SERVER.z88dk_available) {
    const miss = (SERVER.z88dk_missing || []).join(", ");
    setBuildStatus(miss ? `z88dk incomplete — missing ${miss}`
                        : "z88dk not ready — see Settings", "bad");
    openServerSettings("z88dk");
    return;
  }
  if (view === "raw" && rawDirty) { await saveRaw(); if (rawDirty) return; }
  else if (dirty && !(await save())) return;
  if (typeof gameTargets === "function" && !gameTargets().length) {
    alert("Select at least one system in the Systems tab first.");
    return;
  }
  showBuildLog();
  $("buildlog").textContent = "starting…";
  setBuildStatus("building…");
  try {
    const r = await api("POST", "/api/build", {});
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
        $("run").disabled = b.status !== "done";
        setBuildStatus(b.status === "done" ? "done" : b.status,
                       b.status === "done" ? "ok" : "bad");
        refreshEmuSystems();
      }
    };
    tick();
  } catch (e) {
    $("buildlog").textContent = "build error: " + e.message;
    setBuildStatus("error", "bad");
    if (/z88dk/i.test(e.message)) openServerSettings("z88dk");
  }
}

