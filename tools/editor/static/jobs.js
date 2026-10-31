"use strict";
function pollJob(id) {
  if (pollingJobs.has(id)) return;
  pollingJobs.add(id);
  activeJob = id; renderStopButton();
  const tick = async () => {
    try {
      const j = await api("GET", "/api/job/" + id);
      if (j.status === "done") {
        pollingJobs.delete(id); activeJob = null; renderStopButton();
        if ($("genstatus")) $("genstatus").textContent = `done (${j.bytes} bytes)`;
        if ($("gen")) $("gen").disabled = false;
        if ($("refgen")) $("refgen").disabled = false;
        if ($("refine")) $("refine").disabled = false;
        if ($("genbar")) $("genbar").innerHTML = "";
        if (j.kind === "ref" || j.ref) refreshRefImages(j.ref);
        else {
          refreshArtImages(j.art);
          if (j.refs && j.refs.length) refreshRefImages(null);
        }
        return;
      }
      if (j.status === "error" || j.status === "cancelled") {
        pollingJobs.delete(id); activeJob = null; renderStopButton();
        if ($("genstatus")) $("genstatus").textContent =
          j.status === "cancelled" ? "stopped" : "error: " + (j.error || "");
        if ($("gen")) $("gen").disabled = false;
        if ($("refgen")) $("refgen").disabled = false;
        if ($("refine")) $("refine").disabled = false;
        if ($("genbar")) $("genbar").innerHTML = "";
        return;
      }
      if ($("genstatus")) $("genstatus").textContent = j.status + "…";
      jobTimers[id] = setTimeout(tick, 1500);
    } catch (e) {
      pollingJobs.delete(id); activeJob = null; renderStopButton();
      if ($("genstatus")) $("genstatus").textContent = "lost: " + e.message;
      if ($("gen")) $("gen").disabled = false;
      if ($("refgen")) $("refgen").disabled = false;
      if ($("refine")) $("refine").disabled = false;
    }
  };
  tick();
}

/* Poll a regenerate-all job, reporting progress per entry (references first,
 * then arts) in the Build log tab and redrawing the active preview when it
 * finishes. Shared by a fresh run (`regenAll`) and a page reload that
 * reattaches to a live job. */
function pollGenerateAll(id) {
  if (pollingJobs.has(id)) return;
  pollingJobs.add(id);
  activeJob = id; renderStopButton();
  const log = $("buildlog");
  const tick = async () => {
    try {
      const j = await api("GET", "/api/job/" + id);
      const total = j.total || (P ? P.arts.length : 0);
      if (j.status === "done" || j.status === "error" ||
          j.status === "cancelled") {
        const errs = j.errors || [];
        pollingJobs.delete(id); activeJob = null; renderStopButton();
        if (log) log.textContent = j.status === "cancelled"
          ? `images stopped at ${j.done || 0}/${total}`
          : `images: ${j.done}/${total} (${errs.length} error(s))`;
        if (errs.length && log) log.textContent += "\n" +
          errs.map(e => `${e.art || e.ref}: ${e.error}`).join("\n");
        setBuildStatus(j.status === "cancelled" ? "stopped"
          : `images ${j.done}/${total}`, j.status === "error" ? "bad" : "ok");
        refreshArtImages(null);
        refreshRefImages(null);
        return;
      }
      if (log) log.textContent =
        `regenerating ${j.current || "…"} (${j.done || 0}/${total})…`;
      setBuildStatus(`images ${j.done || 0}/${total}`);
      jobTimers[id] = setTimeout(tick, 1500);
    } catch (e) {
      pollingJobs.delete(id); activeJob = null; renderStopButton();
      if (log) log.textContent = "generate lost: " + e.message;
      setBuildStatus("error", "bad");
    }
  };
  tick();
}

/* Reattach to a generation still running server-side (reported in the project
 * payload as `active_job`) after a page reload, so the Stop button works and
 * the progress display resumes. */
function reattachJob(job) {
  if (!job || !job.id) return;
  if (job.kind === "all") pollGenerateAll(job.id);
  else pollJob(job.id);
}

/* Enable/disable the Regenerate/Stop images buttons from `activeJob`, so both
 * the art pane and the top art bar reflect a run in progress. */
function renderStopButton() {
  const running = !!activeJob;
  if ($("regenall")) $("regenall").disabled = running || !GAMES.length;
  if ($("regenmissing")) $("regenmissing").disabled = running || !GAMES.length;
  if ($("stopgen")) $("stopgen").disabled = !running;
  if ($("genstop")) $("genstop").disabled = !running;
  if ($("refgen")) $("refgen").disabled = running;
  if ($("refgenstop")) $("refgenstop").disabled = !running;
  if ($("refine")) $("refine").disabled = running;
}

/* Abort the active generation job: the server interrupts the SD pass and a
 * *-all worker stops before the next art. The poller observes "cancelled". */
async function stopGeneration() {
  if (!activeJob) return;
  const jid = activeJob;
  $("stopgen").disabled = true;
  try {
    await api("DELETE", "/api/job/" + jid);
  } catch (e) {
    if ($("genstatus")) $("genstatus").textContent = "stop failed: " + e.message;
  }
}

/* Regenerate every art of the selected game server-side (the server reads
 * game.md, so flush pending edits first). Progress is reported per art in
 * the Build log tab; the active preview is redrawn at the end. `missing`
 * asks the server to render only arts with no PNG yet. */
async function regenImages(missing) {
  if (!game || !AI.image) return;
  if ((dirty || rawDirty) && !(await save())) return;
  const log = $("buildlog");
  if (log) log.textContent = missing ? "generating missing images…"
                                     : "regenerating images…";
  setBuildStatus("generating…");
  try {
    const r = await api("POST", "/api/generate_all",
                        missing ? { missing: true } : {});
    pollGenerateAll(r.job);
  } catch (e) {
    activeJob = null; renderStopButton();
    if (log) log.textContent = "generate failed: " + e.message;
    setBuildStatus("error", "bad");
  }
}

function regenAll() { return regenImages(false); }
function regenMissing() { return regenImages(true); }

function redrawSelection() {
  if (!sel.id) return;
  if (sel.kind === "art") drawArtView(sel.id, "all");
  else if (sel.kind === "scene") {
    const s = P.scenes.find(x => x.id === sel.id);
    if (s) drawSceneArt(s);
  }
}

// ----------------------------------------------------------------- issues
function renderIssues() {
  const el = $("issues");
  const list = P.issues || [];
  if (!list.length) { el.innerHTML = "<em>no issues</em>"; return; }
  el.innerHTML = list.map((i) =>
    `<div class="issue ${i.level}">
      <div>${esc(i.msg)}</div>
      <div class="where">${esc(i.section)} · ${esc(i.id)}</div>
    </div>`).join("");
}

