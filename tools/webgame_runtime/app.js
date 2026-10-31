(function () {
  "use strict";

  var D = window.RVN_GAME;
  var $ = function (id) { return document.getElementById(id); };

  function fatal(message) {
    var el = $("fatal");
    if (el) {
      el.textContent = message;
      el.hidden = false;
    }
    var app = $("app");
    if (app) app.hidden = true;
  }

  if (!D || !Array.isArray(D.scenes) || !D.scenes.length) {
    fatal("This game has no scenes to play.");
    return;
  }

  var scenes = {};
  D.scenes.forEach(function (scene) { scenes[scene.id] = scene; });
  var startScene = D.startScene && scenes[D.startScene]
    ? D.startScene : D.scenes[0].id;
  var bandAspect = 256 / (8 * Math.max(1, Number(D.artRows) || 10));

  var STATE_KEY = "rvn.web." + (D.slug || "game") + ".state";
  var STATE_VERSION = 1;

  var flags = new Set(D.startItems);
  var current = startScene;
  var sheetItem = null;
  var currentArt = null;
  var lastScene = "";

  var app = $("app");
  var gameTitle = $("gametitle");
  var sceneTitle = $("scenetitle");
  var sceneText = $("scenetext");
  var optionsEl = $("options");
  var inventoryEl = $("inventory");
  var artImg = $("artimg");
  var artPlaceholder = $("artplaceholder");
  var sheet = $("itemsheet");
  var itemTitle = $("itemtitle");
  var itemDesc = $("itemdesc");
  var itemOpts = $("itemopts");
  var password = $("password");
  var passwordForm = $("passwordform");
  var passwordInput = $("passwordinput");
  var passwordError = $("passworderror");
  var messagePopup = $("messagepopup");
  var messageText = $("messagetext");
  var messageClose = $("messageclose");
  var messageDone = null;

  function setColours() {
    var colours = D.textColors || {};
    var root = document.documentElement.style;
    root.setProperty("--ink", colours.ink || "#c0c0c0");
    root.setProperty("--highlight", colours.highlight || "#00ff00");
    root.setProperty("--bg", colours.bg || "#000000");
    root.setProperty("--band-aspect", String(bandAspect));
  }

  function condOk(conds) {
    if (!conds) return true;
    for (var i = 0; i < conds.length; i++) {
      var kind = conds[i][0];
      var name = conds[i][1];
      var on = flags.has(name);
      if (kind === "unless" ? on : !on) return false;
    }
    return true;
  }

  function countItems() {
    var n = 0;
    for (var i = 0; i < D.itemOrder.length; i++) {
      if (flags.has(D.itemOrder[i])) n++;
    }
    return n;
  }

  function optionVisible(opt) {
    if (!condOk(opt.cond)) return false;
    if (opt.inscene && opt.inscene !== current) return false;
    if (opt.pick && flags.has(opt.pick)) return false;
    if (opt.pick && D.carry > 0 && countItems() >= D.carry) return false;
    return true;
  }

  function applyEffects(opt) {
    if (opt.clear) flags = new Set(D.startItems);
    if (opt.set) flags.add(opt.set);
    if (opt.unset) flags.delete(opt.unset);
    if (opt.pick) flags.add(opt.pick);
    if (opt.leave) flags.delete(opt.leave);
  }

  function closeMessage() {
    if (messagePopup.hidden) return;
    messagePopup.hidden = true;
    var done = messageDone;
    messageDone = null;
    if (done) done();
  }

  function showMessage(text, done) {
    messageClose.textContent = D.popupHint || "Continue";
    messageText.textContent = text;
    messageDone = done || null;
    messagePopup.hidden = false;
    setTimeout(function () { messageClose.focus(); }, 30);
  }

  function activateOption(opt, after) {
    var run = function () {
      applyEffects(opt);
      after();
    };
    if (opt.popup) showMessage(opt.popup, run);
    else run();
  }

  function resetState() {
    flags = new Set(D.startItems);
    current = startScene;
    closeItem();
  }

  function saveState() {
    try {
      window.localStorage.setItem(STATE_KEY, JSON.stringify({
        v: STATE_VERSION,
        slug: D.slug || "",
        scene: current,
        flags: Array.from(flags)
      }));
    } catch (e) { /* storage unavailable: play without persistence */ }
  }

  function clearState() {
    try { window.localStorage.removeItem(STATE_KEY); } catch (e) { /* ignore */ }
  }

  function restoreState() {
    var stored = null;
    try {
      stored = JSON.parse(window.localStorage.getItem(STATE_KEY) || "null");
    } catch (e) { stored = null; }
    if (!stored || stored.v !== STATE_VERSION || !Array.isArray(stored.flags)) {
      resetState();
      return;
    }
    flags = new Set();
    for (var i = 0; i < stored.flags.length; i++) {
      if (typeof stored.flags[i] === "string") flags.add(stored.flags[i]);
    }
    current = scenes[stored.scene] ? stored.scene : startScene;
  }

  function navigate(target) {
    if (target && target !== "-" && scenes[target]) {
      current = target;
      renderScene(true);
    } else {
      renderScene(false);
    }
  }

  function cropRect(crop, natW, natH) {
    if (Array.isArray(crop) && crop.length === 4) {
      var given = crop.map(Number);
      if (given[2] > 0 && given[3] > 0) return given;
    }
    var w = 100;
    var h = 100;
    if (natW / natH > bandAspect) {
      w = (natH * bandAspect / natW) * 100;
    } else {
      h = (natW / bandAspect / natH) * 100;
    }
    return [(100 - w) / 2, (100 - h) / 2, w, h];
  }

  function layoutArt() {
    if (!currentArt || !artImg.naturalWidth || !artImg.naturalHeight) return;
    var rect = cropRect(currentArt.crop, artImg.naturalWidth,
                        artImg.naturalHeight);
    artImg.style.width = (10000 / rect[2]) + "%";
    artImg.style.height = (10000 / rect[3]) + "%";
    artImg.style.left = (-(rect[0] / rect[2]) * 100) + "%";
    artImg.style.top = (-(rect[1] / rect[3]) * 100) + "%";
  }

  function renderArt(scene) {
    currentArt = D.arts[scene.art] || null;
    if (!currentArt || !currentArt.src) {
      artImg.hidden = true;
      artImg.removeAttribute("src");
      artPlaceholder.hidden = false;
      return;
    }
    artPlaceholder.hidden = true;
    artImg.hidden = false;
    artImg.alt = scene.title ? scene.title + " artwork" : "Scene artwork";
    artImg.onload = layoutArt;
    artImg.onerror = function () {
      artImg.hidden = true;
      artPlaceholder.hidden = false;
    };
    if (artImg.getAttribute("src") !== currentArt.src) {
      artImg.src = currentArt.src;
    } else if (artImg.complete) {
      layoutArt();
    }
  }

  function textNode(text) {
    return document.createTextNode(text);
  }

  function renderLineText(container, segments) {
    for (var i = 0; i < segments.length; i++) {
      var seg = segments[i];
      if (!seg.text) continue;
      if (seg.flag && !flags.has(seg.flag)) {
        (function (flag, text) {
          var word = document.createElement("button");
          word.type = "button";
          word.className = "word";
          word.textContent = text;
          word.addEventListener("click", function () {
            flags.add(flag);
            renderScene(false);
          });
          container.appendChild(word);
        })(seg.flag, seg.text);
      } else {
        container.appendChild(textNode(seg.text));
      }
    }
  }

  function renderText(scene) {
    sceneText.replaceChildren();
    for (var i = 0; i < scene.text.length; i++) {
      var line = scene.text[i];
      if (!condOk(line.cond)) continue;
      var p = document.createElement("p");
      renderLineText(p, line.segments);
      sceneText.appendChild(p);
    }
  }

  function optionButton(opt, onClick) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "option";
    button.appendChild(textNode(opt.label || ""));
    button.addEventListener("click", onClick);
    return button;
  }

  function renderOptions(scene) {
    optionsEl.replaceChildren();
    var shown = 0;
    for (var i = 0; i < scene.opts.length; i++) {
      var opt = scene.opts[i];
      if (!optionVisible(opt)) continue;
      (function (choice) {
        optionsEl.appendChild(optionButton(choice, function () {
          activateOption(choice, function () { navigate(choice.target); });
        }));
      })(opt);
      shown++;
    }
    if (!shown) {
      var empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = scene.ending ? "The End." : "No options are available.";
      optionsEl.appendChild(empty);
    }
  }

  function renderInventory() {
    inventoryEl.replaceChildren();
    var held = [];
    for (var i = 0; i < D.itemOrder.length; i++) {
      var id = D.itemOrder[i];
      if (flags.has(id)) held.push(id);
    }
    inventoryEl.hidden = held.length === 0;
    for (var j = 0; j < held.length; j++) {
      (function (itemId) {
        var meta = D.items[itemId] || { name: itemId };
        var button = document.createElement("button");
        button.type = "button";
        button.textContent = meta.name || itemId;
        button.setAttribute("aria-label", "Open " + (meta.name || itemId));
        button.addEventListener("click", function () { openItem(itemId); });
        inventoryEl.appendChild(button);
      })(held[j]);
    }
  }

  function renderScene(scroll) {
    var scene = scenes[current] || scenes[startScene];
    if (!scene) { fatal("This game has no playable scene."); return; }
    current = scene.id;
    if (scene.ending) flags.add(scene.ending);
    document.title = D.title || "Visual Novel";
    sceneTitle.textContent = scene.title || scene.id;
    renderArt(scene);
    renderText(scene);
    renderOptions(scene);
    renderInventory();
    if (scroll && lastScene !== current) {
      window.scrollTo(0, 0);
    }
    lastScene = current;
    saveState();
  }

  function closeItem() {
    sheetItem = null;
    sheet.hidden = true;
  }

  function openItem(id) {
    sheetItem = id;
    renderSheet();
    sheet.hidden = false;
    var close = $("itemclose");
    if (close) close.focus();
  }

  function renderSheet() {
    if (!sheetItem) return;
    var meta = D.items[sheetItem] || { name: sheetItem, desc: [], opts: [] };
    itemTitle.textContent = meta.name || sheetItem;
    itemDesc.replaceChildren();
    for (var i = 0; i < (meta.desc || []).length; i++) {
      var line = meta.desc[i];
      if (!condOk(line.cond)) continue;
      var p = document.createElement("p");
      p.textContent = line.text;
      itemDesc.appendChild(p);
    }
    itemOpts.replaceChildren();
    var shown = 0;
    for (var j = 0; j < (meta.opts || []).length; j++) {
      var opt = meta.opts[j];
      if (!optionVisible(opt)) continue;
      (function (choice) {
        itemOpts.appendChild(optionButton(choice, function () {
          activateOption(choice, function () {
            closeItem();
            navigate(choice.target);
          });
        }));
      })(opt);
      shown++;
    }
    if (D.carry > 0) {
      var drop = document.createElement("button");
      drop.type = "button";
      drop.className = "option";
      drop.textContent = D.inventory.drop || "Drop";
      drop.addEventListener("click", function () {
        flags.delete(sheetItem);
        closeItem();
        renderScene(false);
      });
      itemOpts.appendChild(drop);
      shown++;
    }
    var back = document.createElement("button");
    back.type = "button";
    back.className = "option";
    back.textContent = D.inventory.back || "Back";
    back.addEventListener("click", closeItem);
    itemOpts.appendChild(back);
    if (!shown) itemOpts.classList.add("only-back");
    else itemOpts.classList.remove("only-back");
  }

  function renderPassword() {
    $("passwordtitle").textContent = D.title || "";
    $("passwordlabel").textContent = D.passwordLabel || "Enter the password:";
    passwordError.hidden = true;
    passwordInput.value = "";
    password.hidden = false;
    app.hidden = true;
    setTimeout(function () { passwordInput.focus(); }, 30);
  }

  function unlock() {
    password.hidden = true;
    app.hidden = false;
    restoreState();
    renderScene(true);
  }

  passwordForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var value = passwordInput.value;
    if (value.toLowerCase() === String(D.password).toLowerCase()
        && value.length === String(D.password).length) {
      unlock();
    } else {
      passwordError.hidden = false;
      passwordError.textContent = "That password is not correct.";
      passwordInput.select();
    }
  });

  $("restart").addEventListener("click", function () {
    if (!window.confirm("Restart the story?")) return;
    clearState();
    resetState();
    renderScene(true);
  });

  $("itemclose").addEventListener("click", closeItem);
  sheet.addEventListener("click", function (event) {
    if (event.target === sheet) closeItem();
  });
  messageClose.addEventListener("click", closeMessage);
  messagePopup.addEventListener("click", function (event) {
    if (event.target === messagePopup) closeMessage();
  });

  document.addEventListener("keydown", function (event) {
    if (!messagePopup.hidden) {
      if (event.key === "Escape" || event.key === "Enter"
          || event.key === " ") {
        event.preventDefault();
        closeMessage();
      }
      return;
    }
    if (!sheet.hidden) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeItem();
      }
      return;
    }
    if (!password.hidden) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    var focusable = Array.prototype.slice.call(
      document.querySelectorAll("#options .option, #inventory button"));
    if (!focusable.length) return;
    var index = focusable.indexOf(document.activeElement);
    if (index === -1) index = event.key === "ArrowDown" ? -1 : focusable.length;
    index += event.key === "ArrowDown" ? 1 : -1;
    if (index < 0) index = focusable.length - 1;
    if (index >= focusable.length) index = 0;
    focusable[index].focus();
    event.preventDefault();
  });

  setColours();
  gameTitle.textContent = D.title || "";
  if (D.password) {
    renderPassword();
  } else {
    app.hidden = false;
    restoreState();
    renderScene(true);
  }
})();
