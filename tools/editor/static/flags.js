"use strict";
// ------------------------------------------------------- flags and items
/* A flag/item is just a name. Explicit declarations live in `# Game flags:` /
 * `items:`; names can also be derived from usage. Both are editable here.
 * `listKey` is "flags" or "items"; `kind` is "flag" or "item". */
function listKey(kind) { return kind === "flag" ? "flags" : "items"; }

function declaredList(kind) {
  const g = P.game || (P.game = {});
  const key = listKey(kind);
  if (!Array.isArray(g[key])) g[key] = [];
  return g[key];
}

/* `## <item-id>` blocks under `# Items`: an optional display `name:` and a per-item
 * description shown on the inventory screen. Stored top-level as
 * P.item_meta[id] = {id, name, desc:[lines]}. An item
 * with neither a name override nor a description has no entry. */
function itemMeta(id) {
  return (P.item_meta || {})[id] || {};
}

/* The display name shown in the item list / inventory band: the section's
 * `name:`, else the id. Mirrors scenefile.item_display_names. */
function itemName(id) {
  return itemMeta(id).name || id;
}

function itemDescLines(id) {
  const d = itemMeta(id).desc;
  return Array.isArray(d) ? d : [];
}

/* The item's own options, as raw authoring strings. */
function itemOpts(id) {
  const o = itemMeta(id).opts;
  return Array.isArray(o) ? o : [];
}

/* Write the `# Items` section, keeping it only while it has a name (different
 * from the id), a description or an option, mirroring scenefile.serialize. */
function setItemMeta(id, patch) {
  const m = (P.item_meta || (P.item_meta = {}));
  const cur = m[id] || { kind: "item", id, name: "", desc: [], opts: [] };
  let name = patch.name !== undefined ? String(patch.name || "").trim()
                                      : (cur.name || "");
  if (name === id) name = "";
  let desc = patch.desc !== undefined ? patch.desc : (cur.desc || []);
  desc = (desc || []).map(x => String(x).trim());
  let opts = patch.opts !== undefined ? patch.opts : (cur.opts || []);
  opts = (opts || []).map(x => String(x).trim()).filter(Boolean);
  if (name || desc.length || opts.length)
    m[id] = { kind: "item", id, name, desc, opts };
  else delete m[id];
}

function setItemDesc(id, lines) { setItemMeta(id, { desc: lines }); }
function setItemName(id, name) { setItemMeta(id, { name }); }
function setItemOpts(id, opts) { setItemMeta(id, { opts }); }

/* Every reference to `name` across scenes and # Items entries, as
 * {scene, field} (scene) or {item, field} (item entry) pairs. */
function usages(kind, name) {
  const out = [];
  P.scenes.forEach((s) => {
    if (kind === "flag" && s.ending === name) out.push({ scene: s.id, field: "ending" });
    (s.text || []).forEach((t) => {
      const p = parseCondLine(t);
      if (p.conds.some(c => c.name === name))
        out.push({ scene: s.id, field: "text" });
      if (kind === "flag") wordsIn(p.text).forEach((w) => {
        if (w.flag === name) out.push({ scene: s.id, field: "word" });
      });
    });
    s.opts.forEach((o) => {
      const p = parseOpt(o);
      const fields = kind === "flag" ? ["set", "unset"] : ["pick", "leave"];
      if ((p.conds || []).some(c => c.name === name))
        out.push({ scene: s.id, field: "condition" });
      fields.forEach((f) => { if (p[f] === name) out.push({ scene: s.id, field: f }); });
    });
  });
  Object.entries(P.item_meta || {}).forEach(([iid, meta]) => {
    (meta.desc || []).forEach((t) => {
      const p = parseCondLine(t);
      if (p.conds.some(c => c.name === name))
        out.push({ item: iid, field: "desc" });
    });
    (meta.opts || []).forEach((o) => {
      const p = parseOpt(o);
      const fields = kind === "flag" ? ["set", "unset"] : ["pick", "leave"];
      if ((p.conds || []).some(c => c.name === name))
        out.push({ item: iid, field: "condition" });
      fields.forEach((f) => { if (p[f] === name) out.push({ item: iid, field: f }); });
    });
  });
  return out;
}

function addEntity(kind) {
  const name = prompt(`New ${kind} name (letters, digits, underscore):`);
  if (!name) return;
  const id = name.trim().replace(/\s+/g, "_");
  if (!id) return;
  if (entityNames(kind).includes(id)) { alert(`"${id}" already exists.`); return; }
  declaredList(kind).push(id);
  sel = { kind, id };
  selMemo[kind] = id;
  markDirty(); renderAll();
}

/* Remove a name: its declaration and (after confirmation) every reference, so
 * it does not simply reappear as a derived name. */
function removeEntity(kind, name) {
  const uses = usages(kind, name);
  const what = kind === "item" ? "item" : "flag";
  if (uses.length &&
      !confirm(`"${name}" is used in ${uses.length} place(s). Delete the ${what} and remove those references?`))
    return;
  const key = listKey(kind);
  P.game[key] = (P.game[key] || []).filter(x => x !== name);
  if (kind === "item") P.game.start = (P.game.start || []).filter(x => x !== name);
  if (kind === "item" && P.item_meta) delete P.item_meta[name];
  P.scenes.forEach((s) => {
    if (kind === "flag" && s.ending === name) s.ending = null;
    s.text = (s.text || []).map((t) => {
      const p = parseCondLine(t);
      p.conds = p.conds.filter(c => c.name !== name);
      if (kind === "flag") p.text = dropWordFlag(p.text, name);
      return fmtCondLine(p);
    });
    s.opts = s.opts.map((o) => {
      const p = parseOpt(o);
      p.conds = (p.conds || []).filter(c => c.name !== name);
      if (kind === "flag") {
        for (const f of ["set", "unset"])
          if (p[f] === name) p[f] = "";
      } else {
        if (p.pick === name) p.pick = ""; if (p.leave === name) p.leave = "";
      }
      return fmtOpt(p);
    });
  });
  Object.values(P.item_meta || {}).forEach((meta) => {
    meta.desc = (meta.desc || []).map((t) => {
      const p = parseCondLine(t);
      p.conds = p.conds.filter(c => c.name !== name);
      return fmtCondLine(p);
    });
    meta.opts = (meta.opts || []).map((o) => {
      const p = parseOpt(o);
      p.conds = (p.conds || []).filter(c => c.name !== name);
      if (kind === "flag") {
        for (const f of ["set", "unset"])
          if (p[f] === name) p[f] = "";
      } else {
        if (p.pick === name) p.pick = ""; if (p.leave === name) p.leave = "";
      }
      return fmtOpt(p);
    });
  });
  if (sel.kind === kind && sel.id === name)
    sel = { kind, id: null };
  if (selMemo[kind] === name) selMemo[kind] = null;
  markDirty(); renderAll();
}

/* Rename a flag/item and repoint every reference (option tokens, endings,
 * text conditions, start:). Called on each keystroke. */
function renameEntity(kind, old, next) {
  next = next.trim();
  if (!next || next === old) return;
  if (entityNames(kind).includes(next)) return;
  const key = listKey(kind);
  P.game[key] = (P.game[key] || []).map(x => x === old ? next : x);
  if (kind === "item") P.game.start = (P.game.start || []).map(x => x === old ? next : x);
  if (kind === "item" && P.item_meta && P.item_meta[old]) {
    P.item_meta[next] = P.item_meta[old];
    P.item_meta[next].id = next;
    delete P.item_meta[old];
  }
  P.scenes.forEach((s) => {
    if (kind === "flag" && s.ending === old) s.ending = next;
    s.text = (s.text || []).map((t) => {
      const p = parseCondLine(t);
      for (const c of p.conds) if (c.name === old) c.name = next;
      if (kind === "flag") p.text = remapWords(p.text, old, next);
      return fmtCondLine(p);
    });
    s.opts = s.opts.map((o) => {
      const p = parseOpt(o);
      for (const c of (p.conds || [])) if (c.name === old) c.name = next;
      if (kind === "flag") {
        for (const f of ["set", "unset"])
          if (p[f] === old) p[f] = next;
      } else {
        if (p.pick === old) p.pick = next; if (p.leave === old) p.leave = next;
      }
      return fmtOpt(p);
    });
  });
  Object.values(P.item_meta || {}).forEach((meta) => {
    meta.desc = (meta.desc || []).map((t) => {
      const p = parseCondLine(t);
      for (const c of p.conds) if (c.name === old) c.name = next;
      return fmtCondLine(p);
    });
    meta.opts = (meta.opts || []).map((o) => {
      const p = parseOpt(o);
      for (const c of (p.conds || [])) if (c.name === old) c.name = next;
      if (kind === "flag") {
        for (const f of ["set", "unset"])
          if (p[f] === old) p[f] = next;
      } else {
        if (p.pick === old) p.pick = next; if (p.leave === old) p.leave = next;
      }
      return fmtOpt(p);
    });
  });
  if (sel.kind === kind && sel.id === old) sel.id = next;
  if (selMemo[kind] === old) selMemo[kind] = next;
  markDirty(); renderSidebar();
  const h = document.querySelector("#main h2");
  if (h && kind === "item") {
    h.firstChild.textContent = `Item: ${itemName(next)} `;
    const pill = h.querySelector(".pill");
    if (pill) pill.textContent = next;
  } else if (h) {
    h.firstChild.textContent = `Flag: ${next} `;
  }
}

