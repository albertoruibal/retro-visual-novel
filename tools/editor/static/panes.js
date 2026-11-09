"use strict";
// ------------------------------------------------------------------- pane
const EMPTY_PANE = {
  art: "No art yet",
  ref: "No reference images yet",
  song: "No songs yet",
  scene: "No scenes yet",
  flag: "No flags yet",
  item: "No items yet",
};

function optionTag(value, selected, label) {
  return `<option value="${value}"${selected ? " selected" : ""}>${label}</option>`;
}

function renderPane() {
  const m = $("main");
  if (view === "systems") { m.innerHTML = paneSystems(); wirePane(); return; }
  if (sel.kind === "game") { m.innerHTML = paneGame(); wirePane(); return; }
  if (!sel.id) {
    const msg = EMPTY_PANE[sel.kind] || "Nothing selected";
    m.innerHTML = `<p>${esc(msg)}. Use <b>+ Add</b> in the sidebar.</p>`;
    wirePane();
    return;
  }
  if (sel.kind === "art") m.innerHTML = paneArt(sel.id);
  else if (sel.kind === "ref") m.innerHTML = paneRef(sel.id);
  else if (sel.kind === "song") m.innerHTML = paneSong(sel.id);
  else if (sel.kind === "scene") m.innerHTML = paneScene(sel.id);
  else if (sel.kind === "flag") m.innerHTML = paneFlag(sel.id);
  else m.innerHTML = paneItem(sel.id);
  wirePane();
}

/* Source conversion options, mirroring scenefile. `rgb`/`none`/1.0 are the
 * defaults and are omitted from game.md on save. */
const MATCH_MODES = ["rgb", "perceptual"];
const PALETTE_MODES = ["none", "spectrum", "adaptive"];
const ADJUST_KEYS = ["saturation", "contrast", "brightness", "gamma"];
const DEFAULT_MATCH = "rgb";
const DEFAULT_PALETTE = "none";
const DEFAULT_PALETTE_COLORS = 16;
const DEFAULT_ADJUST = { saturation: 1, contrast: 1, brightness: 1, gamma: 1 };
/* Human labels for the dither dropdowns. */
const DITHER_LABELS = {
  off: "Off (hard nearest-colour snap)",
  bayer2: "Bayer 2×2 (coarse, rough)",
  bayer4: "Bayer 4×4 (ordered)",
  bayer8: "Bayer 8×8 (finer gradients)",
  noise: "Noise (grain, no ordered pattern)",
  floyd: "Floyd–Steinberg (error diffusion)",
  atkinson: "Atkinson (high contrast)",
  jarvis: "Jarvis–Judice–Ninke (smooth)",
  stucki: "Stucki (crisp)",
  sierra: "Sierra (smooth, light)",
};
/* Resolve a conversion key for an entry (an `# Art`, or null for the game):
 * the entry's own value when set, else the game default, else `def`. Mirrors
 * scenefile.conversion_options so the previews and the build agree. */
function convVal(entry, key, def) {
  const own = entry ? entry[key] : null;
  if (own !== undefined && own !== null && own !== "") return own;
  const gv = P && P.game ? P.game[key] : null;
  if (gv !== undefined && gv !== null && gv !== "") return gv;
  return def;
}
function gameMatch() {
  const v = P && P.game ? P.game.match : null;
  return MATCH_MODES.includes(v) ? v : DEFAULT_MATCH;
}
function gamePalette() {
  const v = P && P.game ? P.game.palette : null;
  return PALETTE_MODES.includes(v) ? v : DEFAULT_PALETTE;
}
function gamePaletteColors() {
  const n = +convVal(null, "palette_colors", DEFAULT_PALETTE_COLORS);
  return Number.isFinite(n) ? Math.min(256, Math.max(2, n))
                            : DEFAULT_PALETTE_COLORS;
}
function gameAdjust(key) {
  const n = +convVal(null, key, DEFAULT_ADJUST[key]);
  return Number.isFinite(n) ? n : DEFAULT_ADJUST[key];
}
/* Whether a `# Game` conversion key is explicitly set (its enable checkbox). */
function gameHas(key) {
  const v = P && P.game ? P.game[key] : null;
  return v !== undefined && v !== null && v !== "";
}
function convMatch(a) {
  const v = convVal(a, "match", DEFAULT_MATCH);
  return MATCH_MODES.includes(v) ? v : DEFAULT_MATCH;
}
function convPalette(a) {
  const v = convVal(a, "palette", DEFAULT_PALETTE);
  return PALETTE_MODES.includes(v) ? v : DEFAULT_PALETTE;
}
function convPaletteColors(a) {
  const n = +convVal(a, "palette_colors", DEFAULT_PALETTE_COLORS);
  return Number.isFinite(n) ? Math.min(256, Math.max(2, n))
                            : DEFAULT_PALETTE_COLORS;
}
function convAdjust(a, key) {
  const n = +convVal(a, key, DEFAULT_ADJUST[key]);
  return Number.isFinite(n) ? n : DEFAULT_ADJUST[key];
}

/* The conversion part of a preview query: the art's effective (possibly
 * unsaved) values, so the previews track the controls before a save. */
function convQuery(a) {
  const parts = [`lines=${artLines()}`,
                 `match=${encodeURIComponent(convMatch(a))}`];
  const pal = convPalette(a);
  parts.push(`palette=${encodeURIComponent(pal)}`);
  if (pal === "adaptive") parts.push(`palette_colors=${convPaletteColors(a)}`);
  for (const k of ADJUST_KEYS) {
    const v = convAdjust(a, k);
    if (v !== 1) parts.push(`${k}=${v}`);
  }
  return parts.join("&");
}
/* Markup for a per-art override slider: a checkbox turns the override on; when
 * off the slider is disabled and shows the inherited game value. */
function ovRange(id, label, min, max, step, value, isSet, inherited) {
  const v = isSet && value != null ? value : inherited;
  return `<div><label class="ovhead">
      <input type="checkbox" id="${id}-on"${isSet ? " checked" : ""}> ${label}
      <span class="val" id="${id}-v">${v}</span></label>
    <input id="${id}" type="range" min="${min}" max="${max}" step="${step}"
      value="${v}"${isSet ? "" : " disabled"}></div>`;
}

/* Markup for a global conversion slider: a checkbox enables the option; when
 * off the slider is disabled and shows the built-in default. A newly ticked
 * option starts at that default value (see wireGlobalRange). */
function gRange(id, label, min, max, step, value, on, def) {
  const v = on && value != null ? value : def;
  return `<div><label class="ovhead">
      <input type="checkbox" id="${id}-on"${on ? " checked" : ""}> ${label}
      <span class="val" id="${id}-v">${v}</span></label>
    <input id="${id}" type="range" min="${min}" max="${max}" step="${step}"
      value="${v}"${on ? "" : " disabled"}></div>`;
}

/* Built-in item-screen text, mirroring scenefile.inventory_strings. Shown as
 * placeholders so an empty field keeps the default. */
const DEFAULT_PASSWORD_LABEL = "Enter the password:";
const DEFAULT_INV_DROP = "Drop";
const DEFAULT_INV_BACK = "Back";
const DEFAULT_POPUP_HINT = "Press a key";
/* Text colour tokens, mirroring scenefile.WORD_INKS. Plain names are the
 * bright variants; `dim_` clears the brightness bit. */
const WORD_COLOURS = ["black", "blue", "green", "cyan", "red", "magenta",
                      "yellow", "white"];
const WORD_COLOUR_TOKENS = [
  ...WORD_COLOURS,
  ...WORD_COLOURS.map(c => "dim_" + c),
];
const DEFAULT_TEXT_INK = "dim_white";
const DEFAULT_HIGHLIGHT_INK = "green";
const DEFAULT_TEXT_BG = "black";

/* Effective colour token for a `# Game` key, falling back to the default. */
function wordColour(key, def) {
  const v = String((P.game && P.game[key]) || "").trim().toLowerCase();
  return v && WORD_COLOUR_TOKENS.includes(v) ? v : def;
}

/* The pluggable build targets, driven by GET /api/targets.  Target options
 * are stored in game.md as `<id>_<key>: value` and surfaced through the
 * `game.extras` mapping, so the SPA never hard-codes a platform's settings. */
function gameTargets() {
  if (P && Array.isArray(P.game.targets) && P.game.targets.length)
    return P.game.targets.slice();
  return ["zx128"];
}
function targetSelected(id) { return gameTargets().includes(id); }
function targetOptionValue(target, o) {
  if (o.game_key) {
    const v = P && P.game ? P.game[o.game_key] : undefined;
    return v === undefined || v === null ? o.default : v;
  }
  const ex = (P && P.game && P.game.extras) || {};
  const v = ex[o.key] !== undefined ? ex[o.key] : o.default;
  if (o.kind === "choice" &&
      !targetOptionChoices(target, o).some((c) => String(c) === String(v)))
    return o.default;
  return v;
}
function isCpcBuild(target) {
  return !!target && (target.id === "cpc" || target.id === "cpc464");
}
function targetOptionChoices(target, o) {
  const choices = (o.choices || []).slice();
  if (isCpcBuild(target) && o.suffix === "art_rows") {
    const ex = (P && P.game && P.game.extras) || {};
    const mode = +(ex[target.id + "_mode"] ?? 1);
    if (mode !== 2) return choices.filter((c) => +c <= 12);
  }
  return choices;
}
function targetOptionOn(o, v) {
  if (v === true) return true;
  if (v === false || v == null) return false;
  const s = String(v).trim().toLowerCase();
  const on = String(o.on_value ?? "1").trim().toLowerCase();
  const off = String(o.off_value ?? "0").trim().toLowerCase();
  if (s === on || s === "1" || s === "true" || s === "on" ||
      s === "yes") return true;
  if (s === off || s === "" || s === "0" || s === "false" ||
      s === "off" || s === "no") return false;
  return false;
}
function cpcMenuForced(target, o) {
  if (!isCpcBuild(target) || o.suffix !== "menu") return false;
  const ex = (P && P.game && P.game.extras) || {};
  return +(ex[target.id + "_mode"] ?? 1) === 0;
}
function systemTargets() {
  return (TARGETS && TARGETS.targets) || [];
}

/* The platform shown in the Systems view: the remembered sub-tab when it still
 * exists, else the first selected platform, else the first registered one. */
function activeSystemId() {
  const list = systemTargets();
  if (!list.length) return "";
  if (systemsTab && list.some((t) => t.id === systemsTab)) return systemsTab;
  const picked = list.find((t) => targetSelected(t.id));
  return (picked || list[0]).id;
}

function systemTabs() {
  const active = activeSystemId();
  return `<div id="systems-tabs" class="systems-tabs" role="tablist"
    aria-label="Build systems">
    ${systemTargets().map((t) => {
      const on = t.id === active;
      const selected = targetSelected(t.id);
      return `<button type="button" class="subtab${on ? " active" : ""}"
        role="tab" data-sys="${esc(t.id)}" aria-selected="${on ? "true" : "false"}"
        title="${esc(t.label)}">${selected ? `<span class="tabdot"
        aria-hidden="true"></span>` : ""}${esc(t.label)}</button>`;
    }).join("")}
  </div>`;
}

function systemCard(t) {
  const selected = targetSelected(t.id);
  return `<div class="card" id="systems-pane" role="tabpanel"
    aria-label="${esc(t.label)}">
    <label style="display:flex;align-items:center;gap:8px">
      <input type="checkbox" class="tgcheck" data-tg="${esc(t.id)}"
             ${selected ? "checked" : ""}>
      <b>${esc(t.label)}</b>
      <span class="pill">${esc((t.outputs || []).join(" / "))}</span>
    </label>
    ${t.available === false
      ? `<div class="hint" style="color:#ff9b55">unavailable: ` +
        `${esc(t.unavailable_reason || "missing toolchain")}</div>`
      : `<div class="hint">${esc(t.description || "")}</div>`}
    <div class="tgopts" data-tg="${esc(t.id)}"
         style="display:${selected ? "block" : "none"}">
      ${(t.options || []).map(o => {
        const v = targetOptionValue(t, o);
        let field = "";
        if (o.kind === "choice") {
          field = `<select id="topt-${esc(o.key)}">${targetOptionChoices(t, o).map(c => {
            const label = o.suffix === "dither"
              ? (DITHER_LABELS[c] || c)
              : o.suffix === "title_ink"
                ? (String(c) === "text" ? "Same as text (default)"
                  : String(c).replace("_", " "))
                : c;
            return optionTag(esc(c), String(v) === String(c), esc(label));
          }).join("")}</select>`;
        } else if (o.kind === "bool") {
          const forced = cpcMenuForced(t, o);
          const on = forced || targetOptionOn(o, v);
          field = `<input id="topt-${esc(o.key)}" type="checkbox"` +
            `${on ? " checked" : ""}${forced ? " disabled" : ""}>`;
        } else if (o.kind === "int") {
          field = `<input id="topt-${esc(o.key)}" type="number" value="${esc(v)}"`;
          if (o.minimum != null) field += ` min="${esc(o.minimum)}"`;
          if (o.maximum != null) field += ` max="${esc(o.maximum)}"`;
          field += ">";
        } else {
          field = `<input id="topt-${esc(o.key)}" value="${esc(v == null ? "" : v)}">`;
        }
        return `<div style="margin-top:6px"><label>${esc(o.label)}</label>${field}
          ${o.help ? `<div class="hint">${esc(o.help)}</div>` : ""}</div>`;
      }).join("")}
      ${(t.options || []).length ? "" : `<div class="hint">No target-specific options.</div>`}
    </div>
  </div>`;
}

function paneSystems() {
  const list = systemTargets();
  if (!list.length) {
    return `<h2>Build systems <span class="pill">built by the Build button</span></h2>
    <div class="card"><div class="hint">No build targets are registered.</div></div>`;
  }
  const t = list.find((x) => x.id === activeSystemId()) || list[0];
  return `<h2>Build systems <span class="pill">built by the Build button</span></h2>
  <div class="hint">Pick a platform's tab to configure it; tick its checkbox to
    include it in the build.</div>
  ${systemTabs()}
  ${systemCard(t)}
  <div class="hint">Each system's options are stored in its
    <code>## &lt;system-id&gt;</code> block under <code># Systems</code> in <code>game.md</code>, so the same selection
    and settings apply on the command line.</div>`;
}

function paneGame() {
  const g = P.game;
  return `<h2>Game settings <span class="pill">shared by every art</span></h2>
  <div class="card">
    <label>Game title</label>
    <input id="gtitle" value="${esc(g.title || "")}" placeholder="Untitled game">
    <div class="hint">Shown as the editor title; stored in the <code># Game</code> section.</div>
  </div>
  <div class="card">
    <label>Common prompt (prefixed to every art prompt)</label>
    <textarea id="gprompt" rows="4">${esc(g.prompt)}</textarea>
    <div class="hint">The model receives "&lt;common prompt&gt;, &lt;art prompt&gt;"; an art with
      reference images also gets a "keep the same design as in the reference image" (or
      "image 1, image 2") clause.</div>
    <div class="grid5" style="margin-top:10px">
      <div><label>Seed</label><input id="gseed" type="number" value="${esc(g.seed)}"></div>
      <div><label>Steps</label><input id="gsteps" type="number" value="${esc(g.steps)}"></div>
      <div><label>CFG</label><input id="gcfg" type="number" step="0.1" value="${esc(g.cfg)}"></div>
      <div><label>Width</label><input id="gwidth" type="number" value="${esc(g.width)}"></div>
      <div><label>Height</label><input id="gheight" type="number" value="${esc(g.height)}"></div>
    </div>
    <div class="hint" style="margin-top:6px">These apply to every art. Generate
      at <b>512×256</b> (2:1) so a source scaled to the art band crops
      vertically; the converter scales/crops anything else, per art (drag the
      box on the <b>Art</b> tab's Original image to pick the crop).</div>
  </div>
  <div class="card">
    <h3>Generation quality</h3>
    <label>Negative prompt (what to avoid)</label>
    <textarea id="gnegative" rows="2">${esc(g.negative_prompt || "")}</textarea>
    <div class="hint">Sent as the model's negative prompt. Keep it to quality
      terms (blurry, artifacts, deformed); avoid "text" so the title logo can
      still be drawn.</div>
    <div class="grid4" style="margin-top:10px">
      <div><label>High-res pass</label>
        <select id="ghires">
          <option value="1"${(g.hires || 1) <= 1 ? " selected" : ""}>Off</option>
          <option value="2"${(g.hires || 1) === 2 ? " selected" : ""}>2×</option>
          <option value="3"${(g.hires || 1) === 3 ? " selected" : ""}>3×</option>
          <option value="4"${(g.hires || 1) === 4 ? " selected" : ""}>4×</option>
        </select></div>
      <div><label>Pass steps</label><input id="ghiressteps" type="number" value="${esc(g.hires_steps || 20)}"></div>
      <div><label>Pass denoise</label>
        <input id="ghiresdenoise" type="number" step="0.05" value="${esc(g.hires_denoise ?? 0.4)}"></div>
      <div><label>Refine strength</label>
        <input id="grefinedenoise" type="number" step="0.05" value="${esc(g.refine_denoise ?? 0.45)}"></div>
    </div>
    <div class="hint">The high-res pass renders the base image, then refines it
      at <b>width×scale</b>; the output PNG is the high-res version. The Art
      tab's <b>Refine 2×</b> instead starts from the current image and keeps its
      composition.</div>
  </div>
  <div class="card">
    <h3>Art conversion <span class="pill">sliders: tick to enable; unticked = default</span></h3>
    <div class="hint">Dithering is chosen per build system on the
      <b>Systems</b> tab.</div>
    <label>Colour matching</label>
    <select id="gmatch">
      <option value="rgb"${gameMatch() === "rgb" ? " selected" : ""}>Plain RGB (default)</option>
      ${optionTag("perceptual", gameMatch() === "perceptual",
                  "Perceptual (redmean) — keeps more colour")}
    </select>
    <div class="hint">How a pixel's distance to a Spectrum colour is measured.
      <b>Perceptual</b> weighs hues the eye reads as more different, so the
      chosen ink/paper pair looks closer to the source.</div>
    <label>Source palette</label>
    <select id="gpalette">
      <option value="none"${gamePalette() === "none" ? " selected" : ""}>None (default)</option>
      ${optionTag("spectrum", gamePalette() === "spectrum",
                  "Snap to the 16 Spectrum colours")}
      <option value="adaptive"${gamePalette() === "adaptive" ? " selected" : ""}>Adaptive (median-cut)</option>
    </select>
    ${gRange("gpalettecolors", "Adaptive colours", 2, 256, 1,
             P.game.palette_colors, gameHas("palette_colors"),
             DEFAULT_PALETTE_COLORS)}
    <div class="hint">Pre-reduces the scaled source before the cell search
      (<b>Adaptive</b> uses this many colours, default 16). Useful for noisy
      AI images.</div>
    <label>Source colour adjustments</label>
    <div class="grid4">
      ${ADJUST_KEYS.map(k => gRange("g" + k,
        k.charAt(0).toUpperCase() + k.slice(1), 0, k === "gamma" ? 4 : 3, 0.05,
        P.game[k], gameHas(k), DEFAULT_ADJUST[k])).join("")}
    </div>
    <div class="hint">Applied to the image before quantising (1 = unchanged).
      Raising <b>Saturation</b> pushes muted art closer to the Spectrum's flat
      palette, so less colour is lost. Each art may override every option here
      on the Art tab.</div>
  </div>
  <div class="card">
    <h3>Text colours</h3>
    <div class="grid4">
      <div><label>Text colour</label>
        <select id="gtextink">
          ${WORD_COLOUR_TOKENS.map(c =>
            optionTag(c, wordColour("text_ink", DEFAULT_TEXT_INK) === c,
                      c.replace("_", " "))).join("")}
        </select></div>
      <div><label>Highlight colour</label>
        <select id="ghighlightink">
          ${WORD_COLOUR_TOKENS.map(c =>
            optionTag(c, wordColour("highlight_ink", DEFAULT_HIGHLIGHT_INK) === c,
                      c.replace("_", " "))).join("")}
        </select></div>
      <div><label>Text background</label>
        <select id="gtextbg">
          ${WORD_COLOUR_TOKENS.map(c =>
            optionTag(c, wordColour("text_bg", DEFAULT_TEXT_BG) === c,
                      c.replace("_", " "))).join("")}
        </select></div>
    </div>
    <div class="hint"><b>Text</b> colours scene text, normal options and
      unselected inventory items; <b>Highlight</b> colours selected options,
      every selectable <code>{{like this}}</code> word, the selected inventory
      item and the <code>&gt;</code> markers; <b>Text background</b> sets the
      paper behind all text. ZX, CPC Modes 0/2, SMS and MSX2 use these colours
      (each snaps to the nearest hardware ink); CPC Mode 1 is monochrome and
      ignores them, and Game Boy Color uses its colour palettes; both also mark
      selection with <code>&gt;</code>. Blank or unknown uses the defaults (<b>dim
      white</b>, <b>green</b> and <b>black</b>).</div>
  </div>
  <div class="card">
    <h3>Inventory</h3>
    <div class="group" style="margin-top:8px;border-top:0;padding-top:0">
      <div class="group-title">Starting inventory</div>
      <label>Items held before the first scene (comma-separated)</label>
      <input id="gstart" value="${esc((g.start || []).join(", "))}">
      <div class="hint">These are inventory items the player begins with. Add and
        edit flags and items on the <b>Flags</b> and <b>Items</b> tabs; an item
        can also be marked "held at start" there.</div>
    </div>
    <div class="group">
      <div class="group-title">Carrying</div>
      <label>Maximum carried items (0 = unlimited)</label>
      <input id="gcarry" type="number" min="0" value="${esc(g.carry || 0)}">
      <div class="hint">When full, <code>pick</code> options are hidden. On the
        pinned layout, held items are shown on the inventory band in the text
        colour; the selected one is highlighted and marked with
        <code>&gt;</code>; press down off the last option to reach them, then
        up/down to pick one and ENTER to open it, which offers a <b>Drop</b>
        entry so the player can free space. A system with <b>Pop-up options</b>
        enabled on the <b>Systems</b> tab lists them in the action dialog
        instead. An option can test several flags with repeated
        <code>if</code>/<code>unless</code> conditions.</div>
    </div>
  </div>
  <div class="card">
    <h3>Music</h3>
    ${songNames().length
      ? `<label>Default song for every scene</label>
    <select id="gmusic">
      <option value=""${!g.music ? " selected" : ""}>— off —</option>
      <option value="on"${g.music === "on" ? " selected" : ""}>on (first song)</option>
      <option value="off"${g.music === "off" ? " selected" : ""}>off</option>
      ${songNames().map(n => optionTag(esc(n), g.music === n, esc(n))).join("")}
    </select>`
      : `<div class="hint">No songs declared. Add songs and upload their
        <code>.pt3</code> modules on the <b>Music</b> tab.</div>`}
    <div class="hint">A scene's own <code>music:</code> overrides this. The
      engine only restarts the player when the selected song changes.</div>
  </div>
  <div class="card">
    <h3>Boot password</h3>
    <label>Ask for a password before the first scene</label>
    <input id="gpassword" value="${esc(g.password || "")}" placeholder="(none)">
    <div class="hint">When set, the game opens on a screen showing the
      <b>game title</b> and asks the player to type this word on the Spectrum
      keyboard; a correct entry starts the first scene, a wrong one shows an
      error and lets them retry. Case-insensitive, at most 16 characters, no
      spaces. Blank means the game starts straight away.</div>
  </div>
  <div class="card">
    <h3>Labels</h3>
    <label>Password prompt (boot screen)</label>
    <input id="gpasswordlabel" value="${esc(g.password_label || "")}"
           placeholder="${esc(DEFAULT_PASSWORD_LABEL)}">
    <div class="hint">Shown above the input on the boot screen, when a
      <b>password</b> is set in the Boot password card. Blank uses the default
      shown. Up to 62 columns.</div>
    <div class="group">
      <div class="group-title">Popups</div>
      <label>Message dismiss prompt</label>
      <input id="gpopuphint" value="${esc(g.popup_hint || "")}"
             placeholder="${esc(DEFAULT_POPUP_HINT)}">
      <div class="hint">Shown at the bottom of an option's <code>msg</code>
        popup. Leave blank to use the default shown. Up to 62 columns.</div>
    </div>
    <div class="group">
      <div class="group-title">Inventory</div>
      <label>Drop entry label</label>
      <input id="ginvdrop" value="${esc(g.inventory_drop || "")}"
             placeholder="${esc(DEFAULT_INV_DROP)}">
      <label>Back entry label</label>
      <input id="ginvback" value="${esc(g.inventory_back || "")}"
             placeholder="${esc(DEFAULT_INV_BACK)}">
      <div class="hint">Held items appear on the inventory band in the text
        colour, or in the action dialog when the system enables
        <b>Pop-up options</b>; the selected one is highlighted and marked with
        <code>&gt;</code>; press down off the last option to reach them, then up/down
        (or S/W, or left/right) to pick one and ENTER to open it. The item screen
        shows its description and its options (pinned to the bottom of the text
        band on ZX, directly below the description on the other systems), then a
        Drop entry (when a <code>carry:</code> cap is set) and a Back entry. Leave a
        field blank to use the default shown. Up to 62 columns
        each; stored in the <code># Game</code> section.</div>
    </div>
  </div>`;
}

/* "Used by" pills for a flag/item, linking back to the scenes that reference
 * it. Clicking a pill opens that scene. */
function entityUsageCard(kind, name) {
  const uses = usages(kind, name);
  if (!uses.length) return "<div class='card'><h3>Used by</h3><em>not used anywhere</em></div>";
  const counts = {};
  uses.forEach(u => {
    const key = (u.scene ? "s:" : "i:") + (u.scene || u.item);
    counts[key] = (counts[key] || 0) + 1;
  });
  const pills = Object.keys(counts).map(key => {
    const isScene = key.startsWith("s:");
    const id = key.slice(2);
    const attr = isScene ? `data-scene="${esc(id)}"` : `data-item="${esc(id)}"`;
    return `<span class="pill usage" ${attr}>${esc(id)}${counts[key] > 1 ? ` ×${counts[key]}` : ""}</span>`;
  }).join(" ");
  return `<div class="card"><h3>Used by</h3>${pills}
    <div class="hint">Click a scene or item to open it.</div></div>`;
}

function paneFlag(id) {
  if (!entityNames("flag").includes(id)) return "<p>missing flag</p>";
  const declared = declaredList("flag").includes(id);
  return `<h2>Flag: ${esc(id)}</h2>
  <div class="card">
    <label>Name</label>
    <input id="fname" value="${esc(id)}">
    <div class="hint">Renaming updates every <code>if</code>, <code>set</code>,
      <code>unset</code>, <code>ending:</code> and text condition that uses it.</div>
    <label style="display:flex;align-items:center;gap:8px;margin-top:12px">
      <input type="checkbox" id="fdeclared"${declared ? " checked" : ""}>
      <span>Declare in <code># Game flags:</code> (exists before any use)</span>
    </label>
    <div class="hint">Unchecking removes only the declaration; if the flag is
      still used by a scene it stays in the id table.</div>
  </div>
  <div class="card">
    <h3>Effects</h3>
    <div class="hint">A scene option <b>sets</b> this flag with <code>set</code>
      and <b>unsets</b> it with <code>unset</code>; options and text lines
      <b>test</b> it with <code>if</code>. Add those on the scene's Options.</div>
  </div>
  ${entityUsageCard("flag", id)}`;
}

function systemFlagNames() {
  const flags = P.system_flags && P.system_flags.length
    ? P.system_flags
    : ["system_zx", "system_zx128", "system_zx48", "system_sms",
       "system_cpc", "system_cpc464", "system_msx2", "system_gb",
       "system_c64", "system_nes", "system_oric"];
  return flags.slice();
}
function condNameOptions(selv) {
  const names = [...new Set([...entityNames("flag"), ...entityNames("item")])]
    .filter(n => !systemFlagNames().includes(n));
  const system = systemFlagNames().filter(n => !names.includes(n));
  const opt = (n) =>
    `<option value="${esc(n)}"${n === selv ? " selected" : ""}>${esc(n)}</option>`;
  let html = `<option value="">—</option>`;
  if (names.length)
    html += `<optgroup label="Flags / items">${names.map(opt).join("")}</optgroup>`;
  if (system.length)
    html += `<optgroup label="Build system">${system.map(opt).join("")}</optgroup>`;
  return html;
}
/* Repeatable `if`/`unless` conditions for one option. Every one must hold. */
function condEditor(p) {
  const rows = (p.conds || []).map((c, i) => `<span class="ocond" data-c="${i}">
      <select class="ckind" title="Condition kind">
        <option value="if"${c.kind === "if" ? " selected" : ""}>if</option>
        <option value="unless"${c.kind === "unless" ? " selected" : ""}>unless</option>
      </select>
      <select class="cname" title="Flag or item">${condNameOptions(c.name)}</select>
      <button class="cdel" title="Remove condition">×</button>
    </span>`).join("");
  return `<div class="oconds">${rows}<button class="oaddcond" title="Add a condition">+ condition</button></div>`;
}

/* One row per scene text / item description logical line: the rendered text,
 * then the postfix conditions on the right (`-> if a unless b` in game.md).
 * The text is a soft-wrapping textarea so a long logical line shows its word
 * breaks while the source keeps it on one line. */
function condLineRows(lines, opts) {
  opts = opts || {};
  const max = opts.max || 8;
  const rows = lines.map((line, i) => {
    const p = parseCondLine(line);
    return `<div class="txtline" data-i="${i}">
      <textarea class="ttext" rows="1" wrap="soft"
        placeholder="${esc(opts.placeholder || "line")}">${esc(p.text)}</textarea>
      <span class="larrow" title="Conditions are written after -> in game.md">→</span>
      ${condEditor(p)}
      <span class="oactions">
        <button class="up" title="Move line up"${i === 0 ? " disabled" : ""}>↑</button>
        <button class="down" title="Move line down"${i === lines.length - 1 ? " disabled" : ""}>↓</button>
        <button class="ldel" title="Delete line">×</button>
      </span>
    </div>`;
  }).join("");
  return `<div class="txtlines">${rows || `<em>${esc(opts.empty || "no lines")}</em>`}</div>
    <button class="ladd"${lines.length >= max ? " disabled" : ""}>+ Add line</button>`;
}

function paneItem(id) {
  if (!entityNames("item").includes(id)) return "<p>missing item</p>";
  const declared = declaredList("item").includes(id);
  const held = (P.game.start || []).includes(id);
  const selFlag = (selv, label) => `<option value="">${label} —</option>` +
    entityNames("flag").map(n =>
      `<option value="${esc(n)}"${n === selv ? " selected" : ""}>${esc(n)}</option>`).join("");
  const selItem = (selv, label) => `<option value="">${label} —</option>` +
    entityNames("item").map(n =>
      `<option value="${esc(n)}"${n === selv ? " selected" : ""}>${esc(n)}</option>`).join("");
  const selScene = (selv) => `<option value="">inscene —</option>` + P.scenes.map(x =>
    `<option value="${esc(x.id)}"${x.id === selv ? " selected" : ""}>${esc(x.id)}</option>`).join("");
  const selTarget = (selv) =>
    `<option value="-"${!selv || selv === "-" ? " selected" : ""}>— same scene —</option>` +
    P.scenes.map(x =>
      `<option value="${esc(x.id)}"${x.id === selv ? " selected" : ""}>${esc(x.id)}</option>`).join("");

  const raw = itemOpts(id);
  const rows = raw.map((o, i) => {
    const p = parseOpt(o);
    return `<div class="opt iopt" data-i="${i}">
      <input class="olabel" placeholder="label (<=62)" value="${esc(p.label)}">
      ${condEditor(p)}
      <select class="oinscene"
              title="Show only when the item was opened from this scene">${selScene(p.inscene)}</select>
      <select class="otarget"
              title="Apply the effects, then go to this scene">${selTarget(p.target)}</select>
      <select class="oset"><option value="">set flag —</option>
        ${selFlag(p.set, "set flag").replace('<option value="">set flag —</option>', "")}</select>
      <select class="ounset"><option value="">unset flag —</option>
        ${selFlag(p.unset, "unset flag").replace('<option value="">unset flag —</option>', "")}</select>
      <select class="opick"><option value="">take item —</option>
        ${selItem(p.pick, "take item").replace('<option value="">take item —</option>', "")}</select>
      <select class="oleave"><option value="">remove item —</option>
        ${selItem(p.leave, "remove item").replace('<option value="">remove item —</option>', "")}</select>
      <label class="oclear" title="Wipe all flags/items and re-grant start: names">
        <input type="checkbox"${p.clear ? " checked" : ""}></label>
      <span class="oactions">
        <button class="up" title="Move option up"${i === 0 ? " disabled" : ""}>↑</button>
        <button class="down" title="Move option down"${i === raw.length - 1 ? " disabled" : ""}>↓</button>
        <button class="del" title="Delete option">×</button>
      </span>
      <input class="opopup" placeholder="popup message (optional)"
             value="${esc(p.popup || "")}">
    </div>`;
  }).join("");

  return `<h2>Item: ${esc(itemName(id))} <span class="pill">${esc(id)}</span></h2>
  <div class="card">
    <label>ID (token)</label>
    <input id="iid" value="${esc(id)}">
    <div class="hint">The ASCII token used by <code>pick</code>, <code>leave</code>
      and <code>start:</code>. Renaming updates every reference.</div>
    <label>Name</label>
    <input id="iname" value="${esc(itemMeta(id).name || "")}"
      placeholder="${esc(id)}">
    <div class="hint">The display name shown in the item list and the inventory
      band; multi-word is fine (max 58 columns). Blank uses the id.</div>
    <label style="display:flex;align-items:center;gap:8px;margin-top:12px">
      <input type="checkbox" id="ideclared"${declared ? " checked" : ""}>
      <span>Declare in <code># Game items:</code> (exists before any use)</span>
    </label>
    <label style="display:flex;align-items:center;gap:8px;margin-top:8px">
      <input type="checkbox" id="iheld"${held ? " checked" : ""}>
      <span>Held at start (listed in <code># Game start:</code>)</span>
    </label>
  </div>
  <div class="card">
    <h3>Description</h3>
    <label>Shown in the inventory screen. Up to 4 logical lines; long
      lines word-wrap on screen.</label>
    ${condLineRows(itemDescLines(id), { max: 4,
      placeholder: "description line", empty: "no description" })}
    <div class="hint">Add conditions on the right to show a line only then;
      they are written after <code>-&gt;</code> in the source
      (<code>text -&gt; if &lt;flag&gt; unless &lt;flag&gt;</code>). Saved as an
      <code>## ${esc(id)}</code> block under <code># Items</code> with a <code>name:</code>,
      <code>desc:</code> and/or <code>opt:</code> line. Held items show on the
      inventory band in the text colour, or in the action dialog on systems
      with <b>Pop-up options</b> enabled (the selected one is highlighted and
      marked with <code>&gt;</code>); choosing one opens its screen to read this
      description (and drop it when a <code>carry:</code> cap is set). With
      <b>Pop-up options</b> an overlong description scrolls; the pinned item
      screen must fit the worst case across flag/item combinations.</div>
  </div>
  <div class="card">
    <h3>Options</h3>
    <div class="hint">Choosing one applies its effects, then goes to its target
      scene; <b>— same scene —</b> redraws the current one. An optional
      <b>popup message</b> is shown first (long ones scroll). <code>inscene</code>
      shows it only when the item was opened from that scene. A Drop entry (with
      a <code>carry:</code> cap) and a Back entry follow; on ZX the whole entry
      list is pinned to the bottom of the text band (or of the wider dialog
      pane when <b>Pop-up options</b> is enabled).</div>
    ${raw.length ? `<div class="opt opthead iopt">
      <div>Label</div><div>Conditions (all must hold)</div>
      <div>Only in scene</div><div>Go to scene</div><div>Set flag</div>
      <div>Unset flag</div><div>Take item</div><div>Remove item</div>
      <div>Clear</div><div>Order</div>
      <div class="opopuphead">Popup message (optional, shown before the action)</div>
    </div>` : ""}
    ${rows || "<em>no options</em>"}
    <button id="addiopt">+ Add option</button>
  </div>
  <div class="card">
    <h3>Effects</h3>
    <div class="hint">A scene option <b>takes</b> this item with <code>pick</code>
      (hidden while held, so it cannot be taken twice) and <b>removes</b> it with
      <code>leave</code>. Set those on the scene's Options.</div>
  </div>
  ${entityUsageCard("item", id)}`;
}

function paneRef(id) {
  const r = (P.refs || []).find(x => x.id === id);
  if (!r) return "<p>missing reference</p>";
  const uses = P.arts.filter(a => (a.refs || []).includes(id)).length;
  return `<h2>Reference: ${esc(r.id)} <span class="pill">${uses} art</span></h2>
  <div class="card">
    <label>Name (id)</label>
    <input id="rid" value="${esc(r.id)}">
    <div class="hint">Renaming updates every art that selects this reference.</div>
    <label>Reference prompt</label>
    <textarea id="rprompt" rows="4">${esc(r.prompt || "")}</textarea>
    <div class="hint">References are generated separately from this prompt
      into <code>assets/refs/&lt;id&gt;/</code>. They are sent to the image
      model when an art selects them; they are never built into the game.</div>
  </div>
  <div class="card">
    <div id="refview" class="artview vertical">${refImageHtml(r)}</div>
    <div style="margin-top:12px; display:flex; gap:8px; align-items:center; flex-wrap:wrap">
      ${AI.image ? '<button id="refgen" class="primary">Regenerate reference</button>' +
        '<button id="refine">Refine 2×</button>' +
        '<button id="refgenstop" class="danger">Stop</button>' : ""}
      <button id="refupload">Upload image</button>
      <input id="refuploadfile" type="file" accept="image/*" style="display:none">
      <span id="genstatus" class="status"></span>
    </div>
    <div id="genbar"></div>
  </div>
  <div class="card">
    <h3>Images <span class="pill" id="refpickcount"></span></h3>
    <div id="refpicker" class="artpicker"></div>
    <div class="hint" style="margin-top:8px">Every generation and upload adds
      a new image; the highlighted one is sent to the model when an art uses
      this reference. The × button deletes a candidate after confirmation.</div>
  </div>
  <div class="card"><h3>Used by</h3>${P.arts.filter(a => (a.refs || []).includes(id))
    .map(a => `<span class="pill">${esc(a.id)}</span>`).join(" ")
    || "<em>no art selects this reference</em>"}</div>`;
}

function paneArt(id) {
  const a = P.arts.find(x => x.id === id);
  if (!a) return "<p>missing art</p>";
  const scenes = P.scenes.filter(s => s.art === id).map(s => s.title || s.id);
  return `<h2>Art: ${esc(a.id)} <span class="pill">${scenes.length} scene(s)</span></h2>
  <div class="card">
    <label>Name (id)</label>
    <input id="aid" value="${esc(a.id)}">
    <div class="hint">Renaming updates every scene that uses this art.</div>
    <label>Subject prompt</label>
    <textarea id="aprompt" rows="4">${esc(a.prompt)}</textarea>
    <div class="hint">Seed, steps, CFG and size are shared by every art and are
      edited on the <b>Game settings</b> tab.</div>
  </div>
  <div class="card">
    <h3>Reference images <span class="pill">generation only</span></h3>
    <div id="artrefs" class="artpicker"></div>
    <div class="hint" style="margin-top:8px">Click a reference to include or
      exclude it for this art. Each one is generated separately from its own
      prompt on the <b>References</b> list; they are not built into the game.</div>
  </div>
  <div class="card">
    <div id="artview" class="artview vertical"></div>
    <div style="margin-top:12px; display:flex; gap:8px; align-items:center; flex-wrap:wrap">
      ${AI.image ? '<button id="gen" class="primary">Regenerate image</button>' +
        '<button id="refine">Refine 2×</button>' +
        '<button id="genstop" class="danger">Stop</button>' : ""}
      <button id="upload">Upload image</button>
      <input id="uploadfile" type="file" accept="image/*" style="display:none">
      <span id="genstatus" class="status"></span>
    </div>
    <div class="hint" style="margin-top:6px">Upload an image (512×256 recommended);
      it is scaled to the game's size and used instead of a generated one.</div>
    <div class="hint" style="margin-top:4px">Drag the box on the <b>Original</b>
      to move it, or a corner to resize it — it keeps the ZX art band's aspect, so
      the crop is never distorted. Other systems keep the crop's full width and
      re-fit its height to their own band aspect. The previews update when you
      release.</div>
    <div id="genbar"></div>
  </div>
  <div class="card">
    <h3>Images <span class="pill" id="artpickcount"></span></h3>
    <div id="artpicker" class="artpicker"></div>
    <div class="hint" style="margin-top:8px">Every generation and upload adds
      a new image to this art's folder. Click one to use it for this art; the
      highlighted image is what the build reads. The × button deletes a
      candidate after confirmation.</div>
  </div>
  <div class="card">
    <h3>Conversion overrides <span class="pill">blank / unticked = game default</span></h3>
    <div class="hint">Dithering is chosen per build system on the
      <b>Systems</b> tab.</div>
    <label>Colour matching</label>
    <select id="amatch">
      <option value="">Game default (${gameMatch()})</option>
      <option value="rgb"${a.match === "rgb" ? " selected" : ""}>Plain RGB</option>
      <option value="perceptual"${a.match === "perceptual" ? " selected" : ""}>Perceptual (redmean)</option>
    </select>
    <label>Source palette</label>
    <select id="apalette">
      <option value="">Game default (${gamePalette()})</option>
      <option value="none"${a.palette === "none" ? " selected" : ""}>None</option>
      <option value="spectrum"${a.palette === "spectrum" ? " selected" : ""}>Snap to the 16 Spectrum colours</option>
      <option value="adaptive"${a.palette === "adaptive" ? " selected" : ""}>Adaptive (median-cut)</option>
    </select>
    ${ovRange("apalettecolors", "Adaptive colours", 2, 256, 1,
              a.palette_colors, a.palette_colors != null, gamePaletteColors())}
    <label>Source colour adjustments</label>
    <div class="grid4">
      ${ADJUST_KEYS.map((k) => ovRange("a" + k,
        k.charAt(0).toUpperCase() + k.slice(1), 0, k === "gamma" ? 4 : 3, 0.05,
        a[k], a[k] != null, gameAdjust(k))).join("")}
    </div>
    <div class="hint">Overrides the <b>Game settings</b> conversion options for
      this art only; the previews above update as you change them.</div>
  </div>
  <div class="card">
    <h3>Used by</h3>
    ${scenes.length
      ? scenes.map(s => `<span class="pill">${esc(s)}</span>`).join(" ")
      : "<em>no scene uses this art</em>"}
  </div>`;
}

function paneSong(id) {
  if (!songNames().includes(id)) return "<p>missing song</p>";
  const scenes = P.scenes.filter(s => (s.music || "") === id)
    .map(s => s.title || s.id);
  const isDefault = (P.game.music || "") === id;
  return `<h2>Song: ${esc(id)}</h2>
  <div class="card">
    <label>Name (id)</label>
    <input id="songid" value="${esc(id)}">
    <div class="hint">The module is <code>assets/music/${esc(id)}.pt3</code>.
      Renaming updates the <code># Game</code> default and every scene that plays it.</div>
  </div>
  <div class="card">
    <h3>Module</h3>
    <div id="songstatus" class="status">loading…</div>
    <audio id="songaudio" controls preload="none"
      src="/api/songpreview/${encodeURIComponent(game)}/${encodeURIComponent(id)}"
      style="width:100%;margin-top:12px"></audio>
    <div class="hint" style="margin-top:4px">Playback is rendered server-side by
      <a href="https://github.com/revengator/spectrumizer" target="_blank"
        rel="noopener noreferrer">spectrumizer</a>'s software AY: faithful for
      converted modules, approximate for
      other trackers. The first play renders the whole module (a few seconds).</div>
    <div style="margin-top:12px">
      <button id="songupload" class="primary">Upload .pt3</button>
      <input id="songuploadfile" type="file" accept=".pt3,application/octet-stream" style="display:none">
    </div>
    <div class="hint" style="margin-top:6px">A PT3 module, at most 4158 bytes
      (the AY player buffer). Uploading replaces the current file.
      Plays on ZX, CPC 6128 and MSX2; the Master System build converts it to SN76489 PSG audio,
      and the Game Boy Color build to Game Boy APU audio.</div>
  </div>
  <div class="card">
    <h3>Convert from MIDI</h3>
    <div class="hint">Arranges a MIDI down to the AY's 3 channels with
      <a href="https://github.com/revengator/spectrumizer" target="_blank"
        rel="noopener noreferrer">spectrumizer</a>, stores it as
      <code>assets/music/${esc(id)}.pt3</code> and keeps the source as
      <code>assets/music/${esc(id)}.mid</code>.</div>
    <div class="hint" id="songsource" style="margin-top:4px">source: —</div>
    <div class="grid4" style="margin-top:10px">
      <div><label>Style</label>
        <select id="cstyle">
          <option value="faithful">faithful</option>
          <option value="chiptune">chiptune</option>
        </select></div>
      <div><label>Bass</label>
        <select id="cbass">
          <option value="normal">normal</option>
          <option value="envelope">buzzer</option>
          <option value="envelope-tone">buzzer+tone</option>
        </select></div>
      <div><label>Transpose</label>
        <input id="ctranspose" type="number" step="1" value="0"></div>
      <div><label>Rows / beat</label>
        <input id="crows" type="number" min="1" max="16" step="1" value="4"></div>
    </div>
    <div class="grid4" style="margin-top:10px">
      <div><label>Channel C</label>
        <select id="cvoice" title="Third AY voice: harmony, arpeggios or echo">
          <option value="">harmony</option>
          <option value="arps">arpeggios</option>
          <option value="echo">echo</option>
        </select></div>
      <div><label>Arp speed</label>
        <input id="carpspeed" type="number" min="1" max="8" step="1" value="1"></div>
      <div><label>Speed (frames/row)</label>
        <input id="cspeed" type="number" min="0" max="255" step="1" placeholder="auto"></div>
      <div><label>Loop position</label>
        <input id="cloop" type="number" min="0" max="255" step="1" value="0"></div>
    </div>
    <div style="margin-top:10px">
      <label for="cauthor">Author</label>
      <input id="cauthor" type="text" maxlength="32" placeholder="SPECTRUMIZER">
    </div>
    <label style="display:flex;align-items:center;gap:8px;margin-top:12px">
      <input type="checkbox" id="cautotranspose"><span>Auto-transpose into the AY register</span></label>
    <label style="display:flex;align-items:center;gap:8px">
      <input type="checkbox" id="cvibrato"><span>Vibrato on the lead</span></label>
    <label style="display:flex;align-items:center;gap:8px">
      <input type="checkbox" id="cnodynamics"><span>No dynamics (flat channel volume)</span></label>
    <div class="hint" style="margin-top:4px">Rows/beat, channel C voice, arp speed,
      speed and loop position map straight onto spectrumizer's flags; the
      defaults are used when left blank.</div>
    <div class="grid4" style="margin-top:12px">
      <div><label>Cut from (s)</label>
        <input id="ctrimstart" type="number" min="0" step="0.1" placeholder="start"></div>
      <div><label>Cut to (s)</label>
        <input id="ctrimend" type="number" min="0" step="0.1" placeholder="end"></div>
    </div>
    <div class="hint" style="margin-top:4px">Trim a long MIDI before conversion:
      a blank field means the start / end of the source. The cut is applied in
      memory only — the stored <code>.mid</code> stays the full original, so
      <b>Re-convert</b> can re-cut it without re-uploading.</div>
    <div style="margin-top:12px">
      <button id="songconvert" class="primary">Convert MIDI → PT3</button>
      <button id="songreconvert" title="Rebuild the .pt3 from the stored original .mid">Re-convert stored .mid</button>
      <input id="songmidfile" type="file" accept=".mid,.midi,audio/midi,audio/x-midi"
        style="display:none">
    </div>
    <div class="hint" style="margin-top:6px">Keep the source public-domain or
      your own: the module inherits the MIDI's licence. Output must fit the
      4158-byte player buffer or the conversion is rejected.</div>
  </div>
  <div class="card">
    <h3>Used by</h3>
    ${isDefault ? `<span class="pill">default for every scene</span> ` : ""}
    ${scenes.length
      ? scenes.map(s => `<span class="pill">${esc(s)}</span>`).join(" ")
      : (isDefault ? "" : "<em>no scene plays this song directly</em>")}
  </div>`;
}

function paneScene(id) {
  const s = P.scenes.find(x => x.id === id);
  if (!s) return "<p>missing scene</p>";
  const sceneOpts = P.scenes.map(x =>
    `<option value="${esc(x.id)}"${x.id === s.id ? " disabled" : ""}>${esc(x.id)}</option>`).join("");
  const artOpts = `<option value="">— none —</option>` + P.arts.map(a =>
    `<option value="${esc(a.id)}"${a.id === s.art ? " selected" : ""}>${esc(a.id)}</option>`).join("");
  const flagOpts = (selv) => `<option value="">—</option>` + entityNames("flag").map(n =>
    `<option value="${esc(n)}"${n === selv ? " selected" : ""}>${esc(n)}</option>`).join("");
  const itemOpts = (selv) => `<option value="">—</option>` + entityNames("item").map(n =>
    `<option value="${esc(n)}"${n === selv ? " selected" : ""}>${esc(n)}</option>`).join("");
  const opts = s.opts.map((o, i) => {
    const p = parseOpt(o);
    const hasTarget = p.target && p.target !== "-" &&
      P.scenes.some(x => x.id === p.target);
    return `<div class="opt" data-i="${i}">
      <input class="olabel" placeholder="label (<=62)" value="${esc(p.label)}">
      <span class="otargetwrap">
        <select class="otarget"><option value="">— target —</option>
          <option value="-"${p.target === "-" ? " selected" : ""}>— same scene —</option>
          ${P.scenes.map(x =>
            optionTag(esc(x.id), x.id === p.target, esc(x.id))).join("")}</select>
        <button type="button" class="otopen"
                title="Open the target scene"${hasTarget ? "" : " disabled"}>open ↗</button>
      </span>
      ${condEditor(p)}
      <select class="oset"><option value="">set flag —</option>
        ${flagOpts(p.set).replace('<option value="">—</option>', "")}</select>
      <select class="ounset"><option value="">unset flag —</option>
        ${flagOpts(p.unset).replace('<option value="">—</option>', "")}</select>
      <select class="opick"><option value="">take item —</option>
        ${itemOpts(p.pick).replace('<option value="">—</option>', "")}</select>
      <select class="oleave"><option value="">remove item —</option>
        ${itemOpts(p.leave).replace('<option value="">—</option>', "")}</select>
      <label class="oclear" title="Wipe all flags/items and re-grant start: names">
        <input type="checkbox"${p.clear ? " checked" : ""}></label>
      <span class="oactions">
        <button class="up" title="Move option up"${i === 0 ? " disabled" : ""}>↑</button>
        <button class="down" title="Move option down"${i === s.opts.length - 1 ? " disabled" : ""}>↓</button>
        <button class="del" title="Delete option">×</button>
      </span>
      <input class="opopup" placeholder="popup message (optional)"
             value="${esc(p.popup || "")}">
    </div>`;
  }).join("");

  return `<h2>Scene: ${esc(s.title || s.id)} <span class="pill">${esc(s.id)}</span></h2>
  <div class="card">
    <div class="row">
      <div><label>Id</label><input id="sid" value="${esc(s.id)}"></div>
      <div><label>Name</label><input id="stitle" value="${esc(s.title)}"></div>
    </div>
    <div class="row">
      <div><label>Art</label><select id="sart">${artOpts}</select></div>
      <div><label>Ending flag (optional, set when reached)</label>
        <input id="sending" value="${esc(s.ending || "")}"></div>
    </div>
    <div class="row">
      <div><label>Music</label><select id="smusic">
        <option value=""${!s.music ? " selected" : ""}>— default —</option>
        <option value="on"${s.music === "on" ? " selected" : ""}>on (game default)</option>
        <option value="off"${s.music === "off" ? " selected" : ""}>off (silence)</option>
        ${songNames().map(n => optionTag(esc(n), s.music === n, esc(n))).join("")}
      </select></div>
      <div><label>Resolved song</label>
        <input value="${esc(resolvedSong(s) || "off")}" disabled></div>
    </div>
    <label>Text (one logical line per row, up to 8; long lines word-wrap)</label>
    ${condLineRows(s.text, { max: 8, placeholder: "text line",
      empty: "no text" })}
    <div class="hint">Add conditions on the right to show a line only then; they
      are written after <code>-&gt;</code> in the source
      (<code>text -&gt; if &lt;flag&gt; unless &lt;flag&gt;</code>).
      Mark a selectable word <code>{{like this}}</code> or
      <code>{{like this|flag}}</code> (flag defaults to the word): the player
      moves up onto it and presses ENTER to set the flag once, which can reveal
      other text/options. Up to 8 per scene; colours on the Game tab.
      The scene title shows on row 0, above the art. On the pinned ZX layout
      the editor checks the worst-case wrapped text + options against the rows
      below the art (all flag/item combinations). <b>Pop-up options</b> puts
      the options in the action dialog and scrolls overflowing text.</div>
  </div>
  <div class="card">
    <h3>Art preview</h3>
    <div id="sceneart" class="artview"></div>
  </div>
  <div class="card">
    <h3>Options</h3>
    <div class="hint">Choosing an option applies its effects, then goes to its
      target. An optional <b>popup message</b> is shown first (long ones scroll)
      and dismissed before the action runs.</div>
    ${s.opts.length ? `<div class="opt opthead">
      <div>Label</div><div>Target scene</div>
      <div>Conditions (all must hold)</div><div>Set flag</div>
      <div>Unset flag</div><div>Take item</div><div>Remove item</div>
      <div>Clear</div><div>Order</div>
      <div class="opopuphead">Popup message (optional, shown before the action)</div>
    </div>` : ""}
    ${opts || "<em>no options</em>"}
    <button id="addopt">+ Add option</button>
  </div>
  <div class="card">
    <h3>Links out</h3>
    <div class="graph">${s.opts.map(o => esc(o)).join("\n") || "—"}</div>
  </div>`;
}

