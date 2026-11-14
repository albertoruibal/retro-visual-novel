(function () {
  "use strict";

  var D = window.RVN_PLAYER;
  var $ = function (id) { return document.getElementById(id); };
  var player = $("player");
  var fatalEl = $("fatal");
  var screenEl = $("screen");
  var bootEl = $("boot");
  var bootTitle = $("boottitle");
  var bootCopy = $("bootcopy");
  var titleEl = $("title");
  var systemsEl = $("systems");
  var systemLabel = $("systemlabel");
  var deckEl = $("deck");
  var deckName = $("deck-media-name");
  var statusEl = $("status");
  var hintEl = $("hint");
  var reloadEl = $("reload");
  var fullscreenEl = $("fullscreen");
  var webTapEl = $("webtap");
  var screenWrap = document.querySelector(".screenwrap");
  var menuToggle = $("menutoggle");
  var menuClose = $("menuclose");
  var sidebar = $("sidebar");
  var menuScrim = $("menuscrim");
  var mobileQuery = window.matchMedia
    ? window.matchMedia("(max-width: 900px)") : null;

  function fatal(message) {
    if (fatalEl) {
      fatalEl.textContent = message;
      fatalEl.hidden = false;
    }
    if (player) player.hidden = true;
  }

  function menuIsOpen() {
    return !!(sidebar && sidebar.classList.contains("open"));
  }

  function setMenu(open) {
    if (!sidebar || !menuToggle) return;
    if (open && mobileQuery && !mobileQuery.matches) open = false;
    var wasOpen = menuIsOpen();
    sidebar.classList.toggle("open", open);
    menuToggle.setAttribute("aria-expanded", open ? "true" : "false");
    menuToggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    if (menuScrim) menuScrim.hidden = !open;
    document.body.classList.toggle("menu-open", open);
    if (open && !wasOpen && menuClose) {
      menuClose.focus();
    } else if (!open && wasOpen && menuToggle) {
      menuToggle.focus();
    }
  }

  var variantsEl = $("variants");
  var variantPick = $("variantpick");

  function variantList(data) {
    if (data && Array.isArray(data.variants) && data.variants.length) {
      return data.variants.map(function (item, index) {
        var id = String(item.id || ("v" + (index + 1)));
        return {
          id: id,
          label: item.label || id,
          src: item.src || "",
          popupMenu: !!item.popupMenu,
          systems: Array.isArray(item.systems) ? item.systems : []
        };
      });
    }
    if (data && data.web && data.web.src) {
      return [{
        id: "default",
        label: "default",
        src: data.web.src,
        popupMenu: !!data.web.popupMenu,
        systems: Array.isArray(data.systems) ? data.systems : []
      }];
    }
    if (data && Array.isArray(data.systems)) {
      return [{
        id: "default",
        label: "default",
        src: "",
        popupMenu: false,
        systems: data.systems
      }];
    }
    return [];
  }

  var variants = D ? variantList(D) : [];
  if (!variants.length || !variants.some(function (item) {
    return item.src || item.systems.length;
  })) {
    fatal("This player has no game data.");
    return;
  }
  player.hidden = false;

  var currentVariant = variants[0];
  var systems = [];
  var byId = {};
  var current = "";
  var hasWeb = false;
  var bootSeq = 0;
  var emulator = null;
  var speccy = null;
  var speccyPromise = null;
  var resizeTimer = null;

  function variantKey() {
    return "rvn.player." + (D.slug || "game") + ".variant";
  }

  function storageKey() {
    return "rvn.player." + (D.slug || "game") + ".system." +
      currentVariant.id;
  }

  function findVariant(id) {
    var found = null;
    variants.forEach(function (item) { if (item.id === id) found = item; });
    return found;
  }

  function storedVariant() {
    try {
      var value = window.localStorage.getItem(variantKey());
      if (value && findVariant(value)) return value;
    } catch (error) { /* storage unavailable */ }
    return variants[0].id;
  }

  function touchDevice() {
    if (!window.matchMedia) return false;
    if (window.matchMedia("(pointer: coarse)").matches) return true;
    return navigator.maxTouchPoints > 0 &&
      window.matchMedia("(max-width: 820px)").matches;
  }

  function defaultSystem() {
    return systems[0] ? systems[0].id : "";
  }

  function applyVariant(id) {
    currentVariant = findVariant(id) || variants[0];
    hasWeb = !!currentVariant.src;
    systems = currentVariant.systems.slice();
    if (hasWeb) {
      systems.push({
        id: "web",
        label: "Web version",
        kind: "web",
        machine: "HTML5",
        media: "web",
        mediaLabel: "Web",
        popupMenu: currentVariant.popupMenu
      });
    }
    byId = {};
    systems.forEach(function (system) { byId[system.id] = system; });
    current = defaultSystem();
  }

  function storedSystem() {
    try {
      var value = window.localStorage.getItem(storageKey());
      if (value && byId[value]) return value;
    } catch (error) { /* storage unavailable */ }
    return defaultSystem();
  }

  function setStatus(text, bad) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
    statusEl.className = "status" + (bad ? " bad" : "");
  }

  function showBoot(title, copy) {
    bootTitle.textContent = title;
    bootCopy.textContent = copy || "";
    bootEl.hidden = false;
    if (deckEl) deckEl.classList.add("is-loading");
  }

  function hideBoot() {
    bootEl.hidden = true;
    if (deckEl) deckEl.classList.remove("is-loading");
  }

  function setAspect(system) {
    screenEl.className = "screen" + (system.kind === "web" ? " web" : "");
    if (system.kind === "web" || shortLandscape()) {
      screenEl.style.aspectRatio = "";
      screenEl.style.maxWidth = "";
    } else {
      var aspect = system.aspect || (4 / 3);
      screenEl.style.aspectRatio = String(aspect);
      screenEl.style.maxWidth = "calc(76dvh * " + aspect + ")";
    }
  }

  function updatePanel(system) {
    systemLabel.textContent = system.label || system.id;
    if (webTapEl) webTapEl.hidden = system.kind !== "web";
    var media = system.media || (system.kind === "web" ? "web" : "cartridge");
    if (deckEl) deckEl.dataset.media = media;
    if (deckName) deckName.textContent = system.mediaLabel || media;
    if (system.kind === "web") {
      hintEl.textContent = currentVariant.popupMenu
        ? "The mobile-first web novel. SPACE opens the options menu; tap or click an option, word or item."
        : "The mobile-first web novel. Tap or click an option, word or item.";
    } else if (system.emulator === "jsspeccy" && speccyTouchWanted()) {
      hintEl.textContent = "Use the on-screen pad: the arrows move, ENTER confirms and SPACE opens the action dialog.";
    } else {
      hintEl.textContent = "Click the screen first so the emulator receives the keyboard.";
    }
    reloadEl.disabled = false;
    var variant = variants.length > 1 ? currentVariant.label + " — " : "";
    document.title = (D.title || "Visual Novel") + " — " + variant +
      (system.label || system.id);
  }

  function setActive(id) {
    Array.prototype.forEach.call(
      systemsEl.querySelectorAll("button[data-system]"),
      function (button) {
        var active = button.dataset.system === id;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      });
  }

  function renderSystems() {
    systemsEl.replaceChildren();
    systems.forEach(function (system) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "button system";
      button.dataset.system = system.id;
      button.textContent = system.label || system.id;
      button.addEventListener("click", function () {
        setMenu(false);
        boot(system.id);
      });
      systemsEl.appendChild(button);
    });
  }

  function renderVariants() {
    if (!variantsEl || !variantPick) return;
    if (variants.length < 2) {
      variantsEl.hidden = true;
      return;
    }
    variantsEl.hidden = false;
    variantPick.replaceChildren();
    variants.forEach(function (variant) {
      var option = document.createElement("option");
      option.value = variant.id;
      option.textContent = variant.label;
      variantPick.appendChild(option);
    });
    variantPick.value = currentVariant.id;
  }

  function changeVariant(id) {
    if (!id || id === currentVariant.id) return;
    var wanted = current;
    try { window.localStorage.setItem(variantKey(), id); }
    catch (error) { /* ignore */ }
    applyVariant(id);
    renderVariants();
    renderSystems();
    boot(byId[wanted] ? wanted : (storedSystem() || current));
  }

  function stop() {
    if (emulator && typeof emulator.exit === "function") {
      try { emulator.exit(); } catch (error) { /* already gone */ }
    }
    emulator = null;
    speccy = null;
    removeSpeccyTouchPad();
    screenEl.innerHTML = "";
    screenEl.className = "screen";
    screenEl.style.aspectRatio = "";
    screenEl.style.maxWidth = "";
    screenEl.style.width = "";
    screenEl.style.height = "";
  }

  function ensureSpeccy() {
    if (window.JSSpeccy) return Promise.resolve(window.JSSpeccy);
    if (speccyPromise) return speccyPromise;
    speccyPromise = new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = "emulator/jsspeccy/jsspeccy.js";
      script.onload = function () {
        if (window.JSSpeccy) resolve(window.JSSpeccy);
        else reject(new Error("JSSpeccy did not load"));
      };
      script.onerror = function () { reject(new Error("JSSpeccy did not load")); };
      document.head.appendChild(script);
    });
    return speccyPromise;
  }

  function screenBox() {
    var style = window.getComputedStyle(screenEl);
    var width = screenEl.clientWidth - parseFloat(style.paddingLeft)
      - parseFloat(style.paddingRight);
    var height = screenEl.clientHeight - parseFloat(style.paddingTop)
      - parseFloat(style.paddingBottom);
    return { width: width, height: height };
  }

  function applySpeccyCrop(zoom) {
    var canvas = screenEl.querySelector("canvas");
    var app = canvas && canvas.parentElement;
    if (!canvas || !app) return;
    var fullW = 320 * zoom;
    var fullH = 240 * zoom;
    var boxW = 256 * zoom;
    var boxH = 192 * zoom;
    if (shortLandscape() && screenWrap) {
      var pad = speccyTouchPad();
      var reserve = pad ? pad.offsetHeight + 10 : 0;
      boxW = screenWrap.clientWidth;
      boxH = Math.max(0, screenWrap.clientHeight - reserve);
      screenEl.style.aspectRatio = "auto";
      screenEl.style.maxWidth = "none";
    }
    screenEl.style.width = boxW + "px";
    screenEl.style.height = boxH + "px";
    app.style.width = boxW + "px";
    app.style.height = boxH + "px";
    app.style.overflow = "hidden";
    canvas.style.width = fullW + "px";
    canvas.style.height = fullH + "px";
    canvas.style.maxWidth = "none";
    canvas.style.position = "absolute";
    canvas.style.left = ((boxW - fullW) / 2) + "px";
    canvas.style.top = ((boxH - fullH) / 2) + "px";
  }

  var SPECCY_TOUCH_KEYS = {
    left: 53, down: 54, up: 55, right: 56,
    enter: 13, space: 32, music: 80
  };

  function speccyTouchWanted() {
    return touchDevice();
  }

  function speccyKeyboardRoot() {
    var canvas = screenEl.querySelector("canvas");
    return canvas && canvas.parentElement;
  }

  function sendSpeccyKey(root, keyCode, down) {
    if (!root) return;
    var event = new KeyboardEvent(down ? "keydown" : "keyup", {
      bubbles: true, cancelable: true
    });
    ["keyCode", "which"].forEach(function (prop) {
      try {
        Object.defineProperty(event, prop, { get: function () { return keyCode; } });
      } catch (error) { /* older browsers */ }
    });
    root.dispatchEvent(event);
  }

  function speccyTouchPad() {
    return document.getElementById("speccy-touch");
  }

  function removeSpeccyTouchPad() {
    var pad = speccyTouchPad();
    if (pad) {
      var root = pad._speccyRoot;
      Array.prototype.forEach.call(
        pad.querySelectorAll("button[data-key].pressed"),
        function (button) {
          sendSpeccyKey(root, SPECCY_TOUCH_KEYS[button.dataset.key], false);
        });
      pad.remove();
    }
    if (screenWrap) screenWrap.classList.remove("has-touch");
  }

  function buildSpeccyTouchPad() {
    removeSpeccyTouchPad();
    var root = speccyKeyboardRoot();
    if (!root || !speccyTouchWanted() || !screenWrap) return null;

    var pad = document.createElement("div");
    pad.id = "speccy-touch";
    pad.className = "speccy-touch";
    pad.setAttribute("role", "group");
    pad.setAttribute("aria-label", "Spectrum controls");
    pad._speccyRoot = root;

    var dpad = document.createElement("div");
    dpad.className = "touch-dpad";
    var actions = document.createElement("div");
    actions.className = "touch-actions";
    function addButton(parent, key, label, aria) {
      var button = document.createElement("button");
      button.type = "button";
      button.dataset.key = key;
      button.textContent = label;
      button.setAttribute("aria-label", aria || label);
      parent.appendChild(button);
    }
    addButton(dpad, "up", "▲", "Up");
    addButton(dpad, "left", "◀", "Left");
    addButton(dpad, "down", "▼", "Down");
    addButton(dpad, "right", "▶", "Right");
    addButton(actions, "enter", "ENTER", "Confirm");
    addButton(actions, "space", "SPACE", "Menu");
    addButton(actions, "music", "P", "Music");
    pad.appendChild(dpad);
    pad.appendChild(actions);

    Array.prototype.forEach.call(
      pad.querySelectorAll("button[data-key]"),
      function (button) {
        var code = SPECCY_TOUCH_KEYS[button.dataset.key];
        var pressed = false;
        function press(event) {
          event.preventDefault();
          if (pressed) return;
          pressed = true;
          button.classList.add("pressed");
          try { button.setPointerCapture(event.pointerId); } catch (error) { /* ignore */ }
          sendSpeccyKey(root, code, true);
        }
        function release(event) {
          if (!pressed) return;
          pressed = false;
          button.classList.remove("pressed");
          if (event) event.preventDefault();
          sendSpeccyKey(root, code, false);
        }
        button.addEventListener("pointerdown", press);
        button.addEventListener("pointerup", release);
        button.addEventListener("pointercancel", release);
        button.addEventListener("pointerleave", release);
        button.addEventListener("lostpointercapture", release);
        button.addEventListener("contextmenu", function (event) {
          event.preventDefault();
        });
      });

    screenWrap.classList.add("has-touch");
    screenWrap.appendChild(pad);
    return pad;
  }

  function shortLandscape() {
    return !!(window.matchMedia &&
      window.matchMedia("(max-width: 900px) and (orientation: landscape) and (max-height: 560px)").matches);
  }

  function speccyZoom() {
    var pad = speccyTouchPad();
    var reserve = pad ? pad.offsetHeight + 10 : 0;
    var width = screenWrap && screenWrap.clientWidth
      ? screenWrap.clientWidth : screenBox().width;
    var height;
    if (shortLandscape() && screenWrap && screenWrap.clientHeight > 0) {
      height = screenWrap.clientHeight;
    } else {
      height = window.innerHeight * 0.72;
      if (screenWrap && screenWrap.clientHeight > 0)
        height = Math.min(height, screenWrap.clientHeight);
    }
    height -= reserve;
    if (width <= 0 || height <= 0) return 1;
    return Math.min(width / 256, height / 192);
  }

  function fitSpeccy() {
    if (!speccy) return;
    var zoom = speccyZoom();
    if (!zoom) return;
    try { speccy.setZoom(zoom); } catch (error) { /* ignore */ }
    applySpeccyCrop(zoom);
  }

  function nativeQuery(system, base) {
    var url = new URL(base, window.location.href);
    var file = new URL(system.file, window.location.href).href;
    if (system.emulator === "webmsx") {
      url.searchParams.set("ROM", file);
      url.searchParams.set("MACHINE", system.machine || "MSX2");
      url.searchParams.set("CARTRIDGE1_FORMAT", "ASCII16");
      url.searchParams.set("FAST_BOOT", "1");
      url.searchParams.set("SCREEN_CONTROL_BAR", "0");
      url.searchParams.set("AUTO_START", "1");
      url.searchParams.set("SCREEN_FULLSCREEN_MODE", "2");
    } else {
      url.searchParams.set("rom", file);
      url.searchParams.set("name", D.slug || "game");
      if (system.emulator === "cpcjs" || system.emulator === "cpc464") {
        url.searchParams.set("run", system.run || "GAME");
        if (system.emulator === "cpc464") url.searchParams.set("model", "464");
      }
    }
    return url.href;
  }

  function bootFrame(system, seq) {
    var frame = document.createElement("iframe");
    frame.title = (D.title || "Game") + " — " + system.label;
    frame.setAttribute("allow", "autoplay; gamepad; fullscreen");
    frame.src = system.kind === "web"
      ? new URL(currentVariant.src, window.location.href).href + "?embed=1"
      : nativeQuery(system, "emulator/" + system.page + "/index.html");
    frame.addEventListener("load", function () {
      if (seq === bootSeq) hideBoot();
    });
    screenEl.appendChild(frame);
  }

  async function bootSpeccy(system, seq) {
    var JSSpeccy = await ensureSpeccy();
    if (seq !== bootSeq) return;
    var zoom = speccyZoom() || 1;
    speccy = JSSpeccy(screenEl, {
      machine: parseInt(system.machine, 10) === 48 ? 48 : 128,
      zoom: zoom,
      openUrl: new URL(system.file, window.location.href).href,
      autoLoadTapes: true,
      autoStart: true,
      uiEnabled: false
    });
    emulator = {
      exit: function () { try { speccy.exit(); } catch (error) { /* gone */ } }
    };
    applySpeccyCrop(zoom);
    buildSpeccyTouchPad();
    speccy.onReady(function () {
      if (seq === bootSeq) hideBoot();
    });
    window.setTimeout(function () {
      if (seq === bootSeq && speccy) {
        fitSpeccy();
        hideBoot();
      }
    }, 500);
    window.requestAnimationFrame(function () {
      if (seq === bootSeq && speccy) fitSpeccy();
    });
  }

  async function boot(id) {
    var system = byId[id];
    if (!system) return;
    current = id;
    setActive(id);
    updatePanel(system);
    setStatus("", false);
    try { window.localStorage.setItem(storageKey(), id); } catch (error) { /* ignore */ }
    var seq = ++bootSeq;
    stop();
    setAspect(system);
    if (system.kind === "web") {
      showBoot("Loading web version…", "HTML5 · no install, no plugins");
      bootFrame(system, seq);
      return;
    }
    showBoot("Loading " + system.label + "…", "Starting the web emulator");
    try {
      if (system.emulator === "jsspeccy") {
        await bootSpeccy(system, seq);
      } else {
        bootFrame(system, seq);
      }
    } catch (error) {
      if (seq === bootSeq) {
        showBoot("Could not start the player", error.message || String(error));
      }
    }
  }

  reloadEl.addEventListener("click", function () { boot(current); });
  fullscreenEl.addEventListener("click", function () {
    if (!screenWrap) return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(function () { /* ignore */ });
    } else if (screenWrap.requestFullscreen) {
      screenWrap.requestFullscreen().catch(function () { /* ignore */ });
    }
  });
  window.addEventListener("resize", function () {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(fitSpeccy, 120);
  });

  if (menuToggle) {
    menuToggle.addEventListener("click", function () {
      setMenu(!menuIsOpen());
    });
  }
  if (menuClose) {
    menuClose.addEventListener("click", function () { setMenu(false); });
  }
  if (menuScrim) {
    menuScrim.addEventListener("click", function () { setMenu(false); });
  }
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && menuIsOpen()) setMenu(false);
  });
  if (mobileQuery) {
    var onMenuQuery = function () {
      if (!mobileQuery.matches) setMenu(false);
    };
    if (mobileQuery.addEventListener) {
      mobileQuery.addEventListener("change", onMenuQuery);
    } else if (mobileQuery.addListener) {
      mobileQuery.addListener(onMenuQuery);
    }
  }

  if (D.title) titleEl.textContent = D.title;
  var requestedVariant = new URLSearchParams(window.location.search)
    .get("variant");
  applyVariant(requestedVariant && findVariant(requestedVariant)
    ? requestedVariant : storedVariant());
  renderVariants();
  renderSystems();
  if (variantPick) {
    variantPick.addEventListener("change", function () {
      changeVariant(variantPick.value);
    });
  }
  var requested = new URLSearchParams(window.location.search).get("system");
  boot(requested && byId[requested] ? requested : storedSystem());
})();
