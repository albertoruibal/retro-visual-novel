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

  var STORAGE_KEY = D.storageKey || D.slug || "game";
  var STATE_KEY = "rvn.web." + STORAGE_KEY + ".state";
  var STATE_VERSION = 1;

  var flags = new Set(D.startItems);
  var current = startScene;
  var sheetItem = null;
  var currentArt = null;
  var lastScene = "";

  var popupMenu = !!D.popupMenu;
  var app = $("app");
  var gameTitle = $("gametitle");
  var sceneTitle = $("scenetitle");
  var sceneText = $("scenetext");
  var optionsEl = $("options");
  var optionsButton = $("optionsbutton");
  var optionsMenu = $("optionsmenu");
  var menuList = $("menulist");
  var menuClose = $("menuclose");
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
  var musicEl = $("music");
  var soundBtn = $("sound");
  var musicEnabled = !!(D.songs && Object.keys(D.songs).length);
  var soundOn = true;
  var currentSong = null;

  function soundKey() {
    return "rvn.web." + STORAGE_KEY + ".sound";
  }

  function loadSoundPref() {
    try {
      if (window.localStorage.getItem(soundKey()) === "0") soundOn = false;
    } catch (e) { /* storage unavailable */ }
  }

  function saveSoundPref() {
    try {
      window.localStorage.setItem(soundKey(), soundOn ? "1" : "0");
    } catch (e) { /* storage unavailable */ }
  }

  function updateSoundButton() {
    if (!soundBtn) return;
    soundBtn.hidden = !musicEnabled;
    soundBtn.textContent = soundOn ? "Sound: on" : "Sound: off";
    soundBtn.setAttribute("aria-pressed", soundOn ? "true" : "false");
  }

  function tryMusicPlay() {
    if (!musicEnabled || !soundOn || !currentSong || !musicEl.src) return;
    var playing = musicEl.play();
    if (playing && typeof playing.catch === "function") {
      playing.catch(function () { /* autoplay is unlocked by the next gesture */ });
    }
  }

  function syncMusic(song) {
    if (!musicEnabled) return;
    if (!song || !D.songs[song]) {
      currentSong = null;
      musicEl.pause();
      musicEl.removeAttribute("src");
      musicEl.load();
      return;
    }
    if (currentSong === song) {
      tryMusicPlay();
      return;
    }
    currentSong = song;
    musicEl.src = D.songs[song].src;
    musicEl.currentTime = 0;
    tryMusicPlay();
  }

  function toggleSound() {
    soundOn = !soundOn;
    saveSoundPref();
    updateSoundButton();
    if (soundOn) tryMusicPlay();
    else musicEl.pause();
  }

  function unlockAudio() {
    if (musicEnabled && soundOn && currentSong) tryMusicPlay();
  }

  function setColours() {
    var colours = D.textColors || {};
    var root = document.documentElement.style;
    if (D.mono) document.documentElement.classList.add("mono");
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

  function visibleOptions(scene) {
    var out = [];
    for (var i = 0; i < scene.opts.length; i++) {
      if (optionVisible(scene.opts[i])) out.push(scene.opts[i]);
    }
    return out;
  }

  function heldItems() {
    var held = [];
    for (var i = 0; i < D.itemOrder.length; i++) {
      if (flags.has(D.itemOrder[i])) held.push(D.itemOrder[i]);
    }
    return held;
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
      if (given[2] > 0 && given[3] > 0) {
        var x0 = Math.max(0, Math.min(natW, given[0] / 100 * natW));
        var y0 = Math.max(0, Math.min(natH, given[1] / 100 * natH));
        var x1 = Math.max(x0 + 1,
                          Math.min(natW, (given[0] + given[2]) / 100 * natW));
        var y1 = Math.max(y0 + 1,
                          Math.min(natH, (given[1] + given[3]) / 100 * natH));
        var cw = x1 - x0;
        var ch = cw / bandAspect;
        if (ch <= natH) {
          var nh = Math.max(1, Math.min(natH, Math.round(ch)));
          var ny0 = Math.round((y0 + y1) / 2 - nh / 2);
          ny0 = Math.max(0, Math.min(natH - nh, ny0));
          return [x0 / natW * 100, ny0 / natH * 100,
                  cw / natW * 100, nh / natH * 100];
        }
        var nw = Math.max(1, Math.min(natW, Math.round(natH * bandAspect)));
        var nx0 = Math.round((x0 + x1) / 2 - nw / 2);
        nx0 = Math.max(0, Math.min(natW - nw, nx0));
        return [nx0 / natW * 100, 0, nw / natW * 100, 100];
      }
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
    optionsEl.hidden = popupMenu;
    optionsButton.hidden = !popupMenu;
    if (popupMenu) return;
    var opts = visibleOptions(scene);
    for (var i = 0; i < opts.length; i++) {
      (function (choice) {
        optionsEl.appendChild(optionButton(choice, function () {
          activateOption(choice, function () { navigate(choice.target); });
        }));
      })(opts[i]);
    }
    if (!opts.length) {
      var empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = scene.ending ? "The End." : "No options are available.";
      optionsEl.appendChild(empty);
    }
  }

  function renderInventory() {
    inventoryEl.replaceChildren();
    var held = heldItems();
    inventoryEl.hidden = popupMenu || held.length === 0;
    if (popupMenu) return;
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

  function menuOpen() {
    return !!optionsMenu && !optionsMenu.hidden;
  }

  function menuEntry(label, onClick) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "option";
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
  }

  function renderMenu() {
    var scene = scenes[current] || scenes[startScene];
    if (!scene) return;
    menuList.replaceChildren();
    var opts = visibleOptions(scene);
    for (var i = 0; i < opts.length; i++) {
      (function (choice) {
        menuList.appendChild(menuEntry(choice.label || "", function () {
          closeMenu();
          activateOption(choice, function () { navigate(choice.target); });
        }));
      })(opts[i]);
    }
    var held = heldItems();
    for (var j = 0; j < held.length; j++) {
      (function (itemId) {
        var meta = D.items[itemId] || { name: itemId };
        menuList.appendChild(menuEntry("* " + (meta.name || itemId),
                                      function () {
          closeMenu();
          openItem(itemId);
        }));
      })(held[j]);
    }
    if (!opts.length && !held.length) {
      var empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = scene.ending
        ? "The End." : "No options are available.";
      menuList.appendChild(empty);
    }
  }

  function openMenu() {
    if (!optionsMenu || !optionsMenu.hidden) return;
    renderMenu();
    optionsMenu.hidden = false;
    var first = menuList.querySelector(".option");
    if (first) first.focus();
    else if (menuClose) menuClose.focus();
  }

  function closeMenu() {
    if (!optionsMenu || optionsMenu.hidden) return;
    optionsMenu.hidden = true;
    if (optionsButton && !optionsButton.hidden) optionsButton.focus();
  }

  function moveFocus(nodes, key) {
    var focusable = Array.prototype.slice.call(nodes);
    if (!focusable.length) return;
    var index = focusable.indexOf(document.activeElement);
    if (index === -1) index = key === "ArrowDown" ? -1 : focusable.length;
    index += key === "ArrowDown" ? 1 : -1;
    if (index < 0) index = focusable.length - 1;
    if (index >= focusable.length) index = 0;
    focusable[index].focus();
  }

  function renderScene(scroll) {
    closeMenu();
    var scene = scenes[current] || scenes[startScene];
    if (!scene) { fatal("This game has no playable scene."); return; }
    current = scene.id;
    if (scene.ending) flags.add(scene.ending);
    document.title = D.title || "Visual Novel";
    sceneTitle.textContent = scene.title || scene.id;
    syncMusic(scene.music);
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
    currentSong = null;
    musicEl.pause();
    renderScene(true);
  });

  if (soundBtn) soundBtn.addEventListener("click", toggleSound);
  document.addEventListener("pointerdown", unlockAudio, true);
  document.addEventListener("keydown", unlockAudio, true);

  $("itemclose").addEventListener("click", closeItem);
  sheet.addEventListener("click", function (event) {
    if (event.target === sheet) closeItem();
  });
  optionsButton.addEventListener("click", openMenu);
  menuClose.addEventListener("click", closeMenu);
  optionsMenu.addEventListener("click", function (event) {
    if (event.target === optionsMenu) closeMenu();
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
    if (menuOpen()) {
      if (event.key === "Escape" || event.key === " ") {
        event.preventDefault();
        closeMenu();
      } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
        event.preventDefault();
        moveFocus(menuList.querySelectorAll(".option"), event.key);
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
    if (popupMenu && event.key === " ") {
      event.preventDefault();
      openMenu();
      return;
    }
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    moveFocus(document.querySelectorAll("#options .option, #inventory button"),
              event.key);
    event.preventDefault();
  });

  loadSoundPref();
  updateSoundButton();
  musicEl.volume = 0.65;
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
