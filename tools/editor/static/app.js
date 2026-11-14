"use strict";
// ------------------------------------------------------------------ start
$("save").onclick = save;
$("reload").onclick = () => {
  if (!(dirty || rawDirty) || confirm("Discard unsaved changes?")) load();
};
$("opengame").onclick = openGameFolder;
$("newgame").onclick = newGame;
$("editorsettings").onclick = () => openServerSettings();
$("gamelabel").onclick = (e) => { e.stopPropagation(); toggleGameMenu(); };
document.addEventListener("click", (e) => {
  if (!$("gamepickpop").hidden && !$("gamepick").contains(e.target)) closeGameMenu();
});
$("settingsclose").onclick = closeServerSettings;
$("settingsmodal").addEventListener("click", (e) => {
  if (e.target === $("settingsmodal")) closeServerSettings();
});
if (window.rvn && typeof window.rvn.onOpenFolderRequest === "function")
  window.rvn.onOpenFolderRequest(openGameFolder);
document.querySelector('.item[data-tab="game"]').onclick = () => {
  sel = { kind: "game" };
  if (view !== "settings") setView("settings"); else renderAll();
};
$("regenall").onclick = regenAll;
$("regenmissing").onclick = regenMissing;
$("stopgen").onclick = stopGeneration;
$("build").onclick = () => runBuild();
$("buildone").onclick = () => runBuild([$("buildtarget").value]);
document.querySelectorAll(".viewtab").forEach((b) =>
  b.addEventListener("click", () => setView(b.dataset.view)));
$("mobsel").onchange = (e) => {
  const v = e.target.value;
  let kind = modeSelKind(view), id = v;
  if (v.startsWith("art:")) { kind = "art"; id = v.slice(4); }
  else if (v.startsWith("ref:")) { kind = "ref"; id = v.slice(4); }
  sel = { kind, id };
  selMemo[kind] = id;
  renderAll();
};
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("gamepickpop").hidden) { closeGameMenu(); return; }
  if (e.key === "Escape" && !$("settingsmodal").hidden) { closeServerSettings(); return; }
});
$("addart").onclick = addArt;
$("addref").onclick = addRef;
$("addsong").onclick = addSong;
$("addscene").onclick = addScene;
$("addflag").onclick = () => addEntity("flag");
$("additem").onclick = () => addEntity("item");
$("rawsave").onclick = saveRaw;
$("rawrevert").onclick = loadRaw;
$("buildclear").onclick = () => { $("buildlog").textContent = ""; };
if ($("variantpick")) {
  $("variantpick").onchange = (e) => switchVariant(e.target.value);
}
window.addEventListener("resize", () => {
  if (EDIT_MODES.includes(view)) redrawSelection();
});
window.addEventListener("beforeunload", (e) => {
  if (dirty || rawDirty) { e.preventDefault(); e.returnValue = ""; }
});
const session = loadSession();
if (session.game) game = session.game;
if (session.variant) variant = session.variant;
if (session.view === "web") session.view = "emu";
if (VIEWS.includes(session.view)) view = session.view;
const hashView = location.hash.slice(1) === "web" ? "emu" : location.hash.slice(1);
if (VIEWS.includes(hashView)) view = hashView;
load().catch((e) => { document.getElementById("main").innerHTML =
  "<p style='color:#ff5d5d'>Failed to load project: " + esc(e.message) + "</p>"; });
