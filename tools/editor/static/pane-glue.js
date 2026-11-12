"use strict";
// --------------------------------------------------------------- pane glue
function readConds(row) {
  return [...row.querySelectorAll(".ocond")].map((el) => ({
    kind: el.querySelector(".ckind").value,
    name: el.querySelector(".cname").value,
  })).filter((c) => c.name);
}
function addCond(row, list, i, write) {
  const o = parseOpt(list[i]);
  const name = entityNames("flag").concat(entityNames("item"))[0] || "";
  if (!name) return;
  o.conds = [...(o.conds || []), { kind: "if", name }];
  list[i] = fmtOpt(o);
  write(list);
  markDirty(); renderAll();
}

/* Add one condition to a scene text / item description line, using the same
 * first-flag default as options. */
function addLineCond(row, list, i, write) {
  const p = parseCondLine(list[i]);
  if ((p.conds || []).length >= 8) return;
  const name = entityNames("flag").concat(entityNames("item"))[0] || "";
  if (!name) return;
  p.conds = [...(p.conds || []), { kind: "if", name }];
  list[i] = fmtCondLine(p);
  write(list);
  markDirty(); renderAll();
}

/* Wire the row editor shared by scene text and item descriptions. */
function wireCondLines(get, set, max) {
  document.querySelectorAll(".txtline").forEach((row) => {
    const i = +row.dataset.i;
    const text = row.querySelector(".ttext");
    const grow = () => {
      text.style.height = "auto";
      text.style.height = text.scrollHeight + "px";
    };
    const upd = () => {
      const v = text.value.replace(/[\r\n]+/g, " ");
      if (v !== text.value) text.value = v;
      const list = get().slice();
      list[i] = fmtCondLine({ text: v, conds: readConds(row) });
      set(list);
      markDirty();
      grow();
    };
    text.oninput = upd;
    text.onkeydown = (e) => {
      if (e.key === "Enter") e.preventDefault();
    };
    grow();
    row.querySelectorAll("select").forEach((el) => el.onchange = upd);
    const addc = row.querySelector(".oaddcond");
    if (addc) addc.onclick = () => addLineCond(row, get().slice(), i, set);
    row.querySelectorAll(".cdel").forEach((btn) => {
      btn.onclick = () => {
        const ci = +btn.closest(".ocond").dataset.c;
        const p = parseCondLine(get()[i]);
        p.conds = (p.conds || []).filter((_, k) => k !== ci);
        const list = get().slice();
        list[i] = fmtCondLine(p);
        set(list);
        markDirty(); renderAll();
      };
    });
    const move = (dir) => {
      const list = get().slice();
      const j = i + dir;
      if (j < 0 || j >= list.length) return;
      [list[i], list[j]] = [list[j], list[i]];
      set(list);
      markDirty(); renderAll();
    };
    const up = row.querySelector(".up");
    if (up) up.onclick = () => move(-1);
    const down = row.querySelector(".down");
    if (down) down.onclick = () => move(1);
    const del = row.querySelector(".ldel");
    if (del) del.onclick = () => {
      const list = get().slice();
      list.splice(i, 1);
      set(list);
      markDirty(); renderAll();
    };
  });
  const add = document.querySelector(".ladd");
  if (add) add.onclick = () => {
    const list = get().slice();
    if (list.length >= max) return;
    list.push("");
    set(list);
    markDirty(); renderAll();
    const rows = document.querySelectorAll(".txtline");
    const last = rows[rows.length - 1];
    if (last) last.querySelector(".ttext").focus();
  };
}

function wirePane() {
  if (sel.kind !== "game" && !sel.id) return;   /* empty tab has no controls */
  if (sel.kind === "game") {
    P.game.extras = P.game.extras || {};
    P.game.targets = Array.isArray(P.game.targets) ? P.game.targets : [];
    document.querySelectorAll(".tgcheck").forEach((cb) => {
      cb.onchange = () => {
        const id = cb.dataset.tg;
        let list = (P.game.targets || []).filter((x) => x !== id);
        if (cb.checked) list.push(id);
        if (!list.length) { cb.checked = true; return; }
        P.game.targets = list;
        if (!cb.checked) {
          const pre = id + "_";
          Object.keys(P.game.extras || {}).forEach((k) => {
            if (k.startsWith(pre)) delete P.game.extras[k];
          });
        }
        markDirty();
        renderAll();
      };
    });
    document.querySelectorAll("#systems-tabs .subtab").forEach((b) => {
      b.onclick = () => {
        systemsTab = b.dataset.sys;
        renderPane();
      };
    });
    document.querySelectorAll("[id^='topt-']").forEach((el) => {
      const key = el.id.slice(5);
      const target = TARGETS.targets?.find((t) => key.startsWith(t.id + "_"));
      const opt = target && (target.options || []).find(
        (o) => o.key === key);
      const apply = () => {
        const onValue = opt && opt.on_value != null ? opt.on_value : "1";
        const offValue = opt && opt.off_value != null ? opt.off_value : "0";
        let v = el.type === "checkbox"
          ? (el.checked ? onValue : offValue) : el.value;
        if (opt && opt.game_key) {
          P.game[opt.game_key] =
            (opt.kind === "int" || typeof opt.default === "number") ? +v : v;
          delete P.game.extras[key];
          markDirty();
          if (opt.game_key === "art_lines") redrawSelection();
          return;
        }
        if (opt && opt.kind === "bool") {
          if (el.checked === !!opt.default) delete P.game.extras[key];
          else P.game.extras[key] = v;
          markDirty();
          return;
        }
        const def = opt ? opt.default : undefined;
        if (String(v) === String(def)) delete P.game.extras[key];
        else P.game.extras[key] = v;
        markDirty();
        if (opt && opt.suffix === "art_rows") redrawSelection();
        if (target && (target.id === "cpc" || target.id === "cpc464")
            && opt && opt.key === "mode") {
          const rowsKey = target.id + "_art_rows";
          if (+v !== 2 && +(P.game.extras[rowsKey] ?? 0) > 12)
            delete P.game.extras[rowsKey];
          renderAll();
        }
      };
      el.onchange = apply;
      if (el.tagName === "INPUT" && el.type !== "checkbox")
        el.oninput = apply;
    });
    bindVal("gtitle", (v) => { P.game.title = v.trim(); renderTitle(); });
    bindVal("gprompt", (v) => P.game.prompt = v);
    bindVal("gnegative", (v) => P.game.negative_prompt = v);
    bindVal("ghires", (v) => P.game.hires = +v || 1, "change");
    bindVal("ghiressteps", (v) => P.game.hires_steps = Math.max(1, +v || 20), "input");
    bindVal("ghiresdenoise", (v) => P.game.hires_denoise = +v, "input");
    bindVal("grefinedenoise", (v) => P.game.refine_denoise = +v, "input");
    bindVal("gseed", (v) => P.game.seed = +v, "input");
    bindVal("gsteps", (v) => P.game.steps = +v, "input");
    bindVal("gcfg", (v) => P.game.cfg = +v, "input");
    bindVal("gwidth", (v) => P.game.width = +v, "input");
    bindVal("gheight", (v) => P.game.height = +v, "input");
    bindVal("gmatch", (v) => P.game.match = v, "change");
    bindVal("gpalette", (v) => P.game.palette = v, "change");
    /* Global colour sliders: a checkbox enables the option. Unticked it clears
     * the key (the engine default applies) and disables the slider; a newly
     * ticked slider starts at the option's default value. */
    const wireGlobalRange = (id, key, def, start, transform) => {
      const el = $(id), cb = $(id + "-on"), out = $(id + "-v");
      if (!el || !cb) return;
      const val = () => (transform ? transform(el.value) : +el.value);
      const sync = () => { if (out) out.textContent = el.value; };
      const apply = () => {
        if (cb.checked) {
          if (P.game[key] == null || P.game[key] === "") el.value = start;
          P.game[key] = val();
          el.disabled = false;
        } else {
          P.game[key] = null;
          el.value = def;
          el.disabled = true;
        }
        sync();
        markDirty();
      };
      el.addEventListener("input", () => {
        if (cb.checked) { P.game[key] = val(); sync(); }
      });
      el.addEventListener("change", () => {
        if (cb.checked) { P.game[key] = val(); markDirty(); }
      });
      cb.addEventListener("change", apply);
    };
    wireGlobalRange("gpalettecolors", "palette_colors", DEFAULT_PALETTE_COLORS, 2,
      (v) => Math.min(256, Math.max(2, +v || DEFAULT_PALETTE_COLORS)));
    ADJUST_KEYS.forEach((k) =>
      wireGlobalRange("g" + k, k, DEFAULT_ADJUST[k], DEFAULT_ADJUST[k]));
    bindVal("gtextink", (v) => {
      P.game.text_ink = v === DEFAULT_TEXT_INK ? "" : v;
    }, "change");
    bindVal("ghighlightink", (v) => {
      P.game.highlight_ink = v === DEFAULT_HIGHLIGHT_INK ? "" : v;
    }, "change");
    bindVal("gtextbg", (v) => {
      P.game.text_bg = v === DEFAULT_TEXT_BG ? "" : v;
    }, "change");
    bindVal("gstart", (v) => P.game.start = v.split(",").map(x => x.trim()).filter(Boolean));
    bindVal("gmusic", (v) => P.game.music = v || null, "change");
    bindVal("gpassword", (v) => P.game.password = v.trim());
    bindVal("gpasswordlabel", (v) => P.game.password_label = v.trim());
    bindVal("gpopuphint", (v) => P.game.popup_hint = v.trim());
    bindVal("gcarry", (v) => P.game.carry = Math.max(0, +v || 0), "input");
    bindVal("ginvdrop", (v) => P.game.inventory_drop = v.trim());
    bindVal("ginvback", (v) => P.game.inventory_back = v.trim());
  } else if (sel.kind === "flag" || sel.kind === "item") {
    const kind = sel.kind;
    if (kind === "flag") {
      bindVal("fname", (v) => renameEntity(kind, sel.id, v));
    } else {
      bindVal("iid", (v) => renameEntity(kind, sel.id, v));
      bindVal("iname", (v) => setItemName(sel.id, v));
    }
    const declEl = kind === "flag" ? "fdeclared" : "ideclared";
    const decl = $(declEl);
    if (decl) decl.onchange = () => {
      const list = declaredList(kind);
      const i = list.indexOf(sel.id);
      if (decl.checked && i < 0) list.push(sel.id);
      else if (!decl.checked && i >= 0) list.splice(i, 1);
      markDirty(); renderAll();
    };
    const held = $("iheld");
    if (held) held.onchange = () => {
      P.game.start = held.checked
        ? [...new Set([...(P.game.start || []), sel.id])]
        : (P.game.start || []).filter(x => x !== sel.id);
      markDirty(); renderAll();
    };
    wireCondLines(() => itemDescLines(sel.id),
                  (list) => setItemDesc(sel.id, list), 4);
    if (kind === "item") {
      const addi = $("addiopt");
      if (addi) addi.onclick = () => {
        setItemOpts(sel.id, [...itemOpts(sel.id), "New option -> -"]);
        markDirty(); renderAll();
      };
      document.querySelectorAll(".opt[data-i]").forEach((row) => {
        const i = +row.dataset.i;
        const upd = () => {
          const o = parseOpt(itemOpts(sel.id)[i]);
          o.target = row.querySelector(".otarget").value || "-";
          o.label = row.querySelector(".olabel").value;
          o.conds = readConds(row);
          o.inscene = row.querySelector(".oinscene").value;
          o.set = row.querySelector(".oset").value;
          o.unset = row.querySelector(".ounset").value;
          o.pick = row.querySelector(".opick").value;
          o.leave = row.querySelector(".oleave").value;
          o.clear = row.querySelector(".oclear input").checked;
          o.popup = row.querySelector(".opopup").value;
          const list = itemOpts(sel.id).slice();
          list[i] = fmtOpt(o);
          setItemOpts(sel.id, list);
          markDirty();
        };
        row.querySelectorAll("input,select").forEach((el) => el.onchange = upd);
        const addc = row.querySelector(".oaddcond");
        if (addc) addc.onclick = () => addCond(row, itemOpts(sel.id).slice(), i,
          (list) => setItemOpts(sel.id, list));
        row.querySelectorAll(".cdel").forEach((btn) => {
          btn.onclick = () => {
            const ci = +btn.closest(".ocond").dataset.c;
            const o = parseOpt(itemOpts(sel.id)[i]);
            o.conds = (o.conds || []).filter((_, k) => k !== ci);
            const list = itemOpts(sel.id).slice();
            list[i] = fmtOpt(o);
            setItemOpts(sel.id, list);
            markDirty(); renderAll();
          };
        });
        const move = (dir) => {
          const list = itemOpts(sel.id).slice();
          const j = i + dir;
          if (j < 0 || j >= list.length) return;
          [list[i], list[j]] = [list[j], list[i]];
          setItemOpts(sel.id, list);
          markDirty(); renderAll();
        };
        const up = row.querySelector(".up");
        if (up) up.onclick = () => move(-1);
        const down = row.querySelector(".down");
        if (down) down.onclick = () => move(1);
        const del = row.querySelector(".del");
        if (del) del.onclick = () => {
          const list = itemOpts(sel.id).slice();
          list.splice(i, 1);
          setItemOpts(sel.id, list);
          markDirty(); renderAll();
        };
      });
    }
    wireUsagePills();
  } else if (sel.kind === "ref") {
    const r = (P.refs || []).find(x => x.id === sel.id);
    bindVal("rid", (v) => renameRef(r.id, v));
    bindVal("rprompt", (v) => r.prompt = v);
    if ($("refgen")) $("refgen").onclick = () => regenerateRef(r);
    if ($("refine")) $("refine").onclick = () => refineEntry("ref", r);
    if ($("refgenstop")) {
      $("refgenstop").onclick = stopGeneration;
      $("refgenstop").disabled = !activeJob;
    }
    $("refupload").onclick = () => $("refuploadfile").click();
    $("refuploadfile").onchange = (e) => {
      const f = e.target.files && e.target.files[0];
      e.target.value = "";
      if (f) uploadRef(f, r);
    };
    drawRefPicker(r.id);
  } else if (sel.kind === "art") {
    const a = P.arts.find(x => x.id === sel.id);
    bindVal("aid", (v) => renameArt(a.id, v));
    bindVal("aprompt", (v) => a.prompt = v);
    drawArtRefs(a);
    if ($("gen")) $("gen").onclick = () => regenerate(a);
    if ($("refine")) $("refine").onclick = () => refineEntry("art", a);
    if ($("genstop")) {
      $("genstop").onclick = stopGeneration;
      $("genstop").disabled = !activeJob;
    }
    $("upload").onclick = () => $("uploadfile").click();
    $("uploadfile").onchange = (e) => {
      const f = e.target.files && e.target.files[0];
      e.target.value = "";
      if (f) uploadArt(f, a);
    };
    const refresh = () => { drawArtView(a.id, "all"); markDirty(); };
    bindVal("amatch", (v) => { a.match = v || null; refresh(); }, "change");
    bindVal("apalette", (v) => { a.palette = v || null; refresh(); }, "change");
    const wireOv = (id, key, inherited, transform) => {
      const el = $(id), cb = $(id + "-on"), out = $(id + "-v");
      if (!el || !cb) return;
      const val = () => (transform ? transform(+el.value) : +el.value);
      const sync = () => { if (out) out.textContent = el.value; };
      const apply = () => {
        if (cb.checked) {
          a[key] = val();
          el.disabled = false;
        } else {
          a[key] = null;
          el.value = inherited;
          el.disabled = true;
        }
        sync();
        refresh();
      };
      el.addEventListener("input", () => {
        if (cb.checked) { a[key] = val(); sync(); }
      });
      el.addEventListener("change", () => { if (cb.checked) refresh(); });
      cb.addEventListener("change", apply);
    };
    wireOv("apalettecolors", "palette_colors", gamePaletteColors(),
           (v) => Math.min(256, Math.max(2, v || DEFAULT_PALETTE_COLORS)));
    ADJUST_KEYS.forEach((k) => wireOv("a" + k, k, gameAdjust(k)));
    drawArtView(a.id, "all");
    drawArtPicker(a.id);
  } else if (sel.kind === "song") {
    /* Resolve the id live: renaming updates `sel.id` without re-rendering the
     * pane (to keep the caret), so the upload/convert handlers must not use a
     * snapshot taken before the rename. */
    const s = { get id() { return sel.kind === "song" ? sel.id : ""; } };
    bindVal("songid", (v) => renameSong(sel.id, v));
    const status = $("songstatus");
    if (status) {
      const missing = (P.issues || []).some(i =>
        i.section === "song" && i.id === s.id && /no module/.test(i.msg));
      status.textContent = missing ? "no module yet — upload a .pt3"
        : "module present";
      status.className = "status " + (missing ? "bad" : "ok");
    }
    $("songupload").onclick = () => $("songuploadfile").click();
    $("songuploadfile").onchange = (e) => {
      const f = e.target.files && e.target.files[0];
      e.target.value = "";
      if (f) uploadSong(f, s);
    };
    $("songconvert").onclick = () => $("songmidfile").click();
    $("songmidfile").onchange = (e) => {
      const f = e.target.files && e.target.files[0];
      e.target.value = "";
      if (f) convertSong(f, s);
    };
    $("songreconvert").onclick = () => reconvertSong(s);
    ["ctrimstart", "ctrimend"].forEach((id) => {
      const el = $(id);
      if (el) el.onchange = () => saveCutValues(s.id);
    });
    restoreCutValues(s.id);
    loadSongSource(s.id);
  } else if (sel.kind === "scene") {
    const s = P.scenes.find(x => x.id === sel.id);
    bindVal("sid", (v) => { s.id = v.trim(); }, "input");
    bindVal("stitle", (v) => s.title = v);
    bindVal("sart", (v) => { s.art = v; drawSceneArt(s); }, "change");
    bindVal("sending", (v) => { s.ending = v.trim() || null; });
    bindVal("smusic", (v) => { s.music = v || null; }, "change");
    wireCondLines(() => s.text, (list) => { s.text = list; }, 8);
    $("addopt").onclick = () => {
      s.opts.push("New option -> " + (P.scenes[0] ? P.scenes[0].id : ""));
      markDirty(); renderAll();
    };
    document.querySelectorAll(".opt[data-i]").forEach((row) => {
      const i = +row.dataset.i;
      const otarget = row.querySelector(".otarget");
      const otopen = row.querySelector(".otopen");
      const syncOpen = () => {
        if (otopen) otopen.disabled = !otarget.value || otarget.value === "-" ||
          !P.scenes.some(x => x.id === otarget.value);
      };
      const upd = () => {
        const o = parseOpt(s.opts[i]);
        o.label = row.querySelector(".olabel").value;
        o.target = otarget.value;
        o.conds = readConds(row);
        o.set = row.querySelector(".oset").value;
        o.unset = row.querySelector(".ounset").value;
        o.pick = row.querySelector(".opick").value;
        o.leave = row.querySelector(".oleave").value;
        o.clear = row.querySelector(".oclear input").checked;
        o.popup = row.querySelector(".opopup").value;
        s.opts[i] = fmtOpt(o);
        syncOpen();
        markDirty();
      };
      row.querySelectorAll("input,select").forEach((el) => el.onchange = upd);
      if (otopen) otopen.onclick = () => {
        if (!otopen.disabled) openScene(otarget.value);
      };
      syncOpen();
      const addc = row.querySelector(".oaddcond");
      if (addc) addc.onclick = () => addCond(row, s.opts.slice(), i,
        (list) => { s.opts = list; });
      row.querySelectorAll(".cdel").forEach((btn) => {
        btn.onclick = () => {
          const ci = +btn.closest(".ocond").dataset.c;
          const o = parseOpt(s.opts[i]);
          o.conds = (o.conds || []).filter((_, k) => k !== ci);
          s.opts[i] = fmtOpt(o);
          markDirty(); renderAll();
        };
      });
      const move = (dir) => {
        const j = i + dir;
        if (j < 0 || j >= s.opts.length) return;
        [s.opts[i], s.opts[j]] = [s.opts[j], s.opts[i]];
        markDirty(); renderAll();
      };
      const up = row.querySelector(".up");
      if (up) up.onclick = () => move(-1);
      const down = row.querySelector(".down");
      if (down) down.onclick = () => move(1);
      const del = row.querySelector(".del");
      if (del) del.onclick = () => {
        s.opts.splice(i, 1); markDirty(); renderAll();
      };
    });
    drawSceneArt(s);
  }
}

/* Scene pane shows the selected scene's Spectrum band (2x), or a hint if the
 * scene has no art assigned. Clicking the band jumps to that art in the Art
 * tab so it can be edited. */
function drawSceneArt(s) {
  const v = $("sceneart");
  if (!s || !s.art) {
    if (v) v.innerHTML = "<em>no art assigned</em>";
    return;
  }
  drawArtView(s.art, "nirvana", "sceneart");
  if (v) v.querySelectorAll("img").forEach((img) => {
    img.style.cursor = "pointer";
    img.title = `Edit art "${s.art}"`;
    img.onclick = () => openArt(s.art);
  });
}

/* Select an art and switch to the Art tab to edit it. */
function openArt(id) {
  if (!P || !P.arts.some((a) => a.id === id)) return;
  sel = { kind: "art", id };
  selMemo.art = id;
  setView("art");
}

/* Select a scene and switch to the Scenes tab to edit it. */
function openScene(id) {
  if (!P || !P.scenes.some((s) => s.id === id)) return;
  sel = { kind: "scene", id };
  selMemo.scene = id;
  setView("scenes");
}

/* Select an inventory item and switch to the Items tab to edit it. */
function openItem(id) {
  if (!P || !entityNames("item").includes(id)) return;
  sel = { kind: "item", id };
  selMemo.item = id;
  setView("items");
}

/* Wire the "Used by" pills: a scene pill opens the scene, an item pill the
 * item (the two are distinguished by their data attribute). */
function wireUsagePills() {
  document.querySelectorAll(".pill.usage").forEach((el) => {
    el.onclick = () => {
      if (el.dataset.item) openItem(el.dataset.item);
      else openScene(el.dataset.scene);
    };
  });
}

function bindVal(id, fn, ev = "input") {
  const el = $(id);
  if (!el) return;
  el.addEventListener(ev, () => { fn(el.value); markDirty(); });
}

