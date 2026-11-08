# Web runtime

The web runtime plays a game in any modern browser as a standalone single-page app. It is the browser counterpart of the
8-bit targets: the same scenes, flags, items, selectable words, passwords and conditions, but rendered with the game's
source artwork instead of a converted platform band.

There are two ways to run it:

- **Editor Web tab** — the SPA saves pending edits, exports the game to `<game-folder>/web/` and previews that static
  folder in an iframe. The preview reloads automatically when the exported content changed; **Reload** forces it.
- **Exported folder** — a self-contained `<game-folder>/web/` tree that can be opened directly, copied to a static host,
  or downloaded as a zip. It does not need Python or a web server.

The **runtime implementation is frontend-only**: all story playback lives in `tools/webgame_runtime/app.js`. Python
only parses `game.md` to produce the data file at export time and copies the static files; the server merely serves the
exported folder during editing.

The runtime is mobile-first: the base layout is a single fluid column with touch-sized controls, and a wider layout is
layered on at `min-width: 720px`.

## Files

| Path | Purpose |
|---|---|
| `tools/webgame.py` | Game data extraction, `game.js`, folder export, zip, CLI |
| `tools/webgame_runtime/index.html` | Runtime shell |
| `tools/webgame_runtime/app.js` | Scene/flag/item engine and DOM rendering |
| `tools/webgame_runtime/style.css` | Mobile-first layout and theme |
| `tools/editor/editor_web.py` | Static export serving, export and zip routes |
| `tools/editor/static/web.js` | Editor Web tab (iframe, reload, open, export, zip) |
| `tools/editor/static/web.css` | Web tab toolbar/host styles |

The runtime is plain classic JavaScript, not ES modules and not a bundle. `index.html` loads `game.js` and then
`app.js`; there is no `fetch` and no API call, so an exported folder works from `file://`.

## Editor tab

The **Web** tab sits between **Build** and **Emulator**. Its toolbar has:

- **Reload** — force a re-export and a fresh iframe, resuming the saved scene and flags.
- **Open in new tab** — save, then open `/play/<slug>/` in a separate browser tab.
- **Export web** — save, then write `<game-folder>/web/` and report the path.
- **Download zip** — save, re-export, and download the folder as `<slug>-web.zip`.

Entering the tab saves pending Source/structured edits first (a failed Source validation keeps you on that tab), then
exports the game and compares the export revision with the preview. If the story, art selection/image or runtime files
changed, the iframe reloads and resumes the saved progress; otherwise the current scene and progress are kept.
**Reload** always forces a re-export and reload. Switching games rebuilds the preview for the new game.

## Routes

The editor server adds these routes (the runtime files are served separately from `/static/` because `index.html`,
`game.js` and the art assets must stay together):

| Route | Purpose |
|---|---|
| `GET /play/<slug>/` | The exported `index.html` |
| `GET /play/<slug>/<file>` | Static runtime file or art from `<game-folder>/web/` |
| `GET /play/<slug>` | Redirect to the trailing-slash form |
| `POST /api/web_export` | Write `<game-folder>/web/` |
| `GET /api/webzip/<slug>` | Re-export and download the zip |

`/play/` never generates story data: it serves the build artifacts in the exported folder, and path containment prevents
walking outside it. The editor calls `POST /api/web_export` before showing the tab.

## Data model

`game.js` assigns one global:

```js
window.RVN_GAME = {
  format: 1,
  slug: "demo",
  title: "The Lighthouse Keeper",
  artRows: 12,                  // selected system's art_rows (even, 4..16)
  startScene: "start",
  startItems: ["seed"],
  carry: 0,
  password: "",
  passwordLabel: "Enter the password:",
  popupHint: "",
  inventory: { drop: "Discard", back: "Close" },
  textColors: { ink: "#c0c0c0", highlight: "#ffff00", bg: "#000000" },
  itemOrder: ["key", "seed", "lamp"],   // display-name order
  items: {
    key: {
      name: "Brass Key",
      desc: [{ text: "A heavy key from the hall.", cond: [] }],
      opts: [{ label: "Unlock the oak door", target: "hall", inscene: "hall",
               cond: [["unless", "door_open"]], set: "door_open", unset: "",
               pick: "", leave: "", clear: false, popup: "" }]
    }
  },
  arts: {
    title: { src: "assets/art/title.png", crop: null }
  },
  scenes: [{
    id: "start",
    title: "The Lighthouse Keeper",
    art: "title",
    ending: "",
    text: [{
      segments: [{ text: "A brass ", flag: null },
                 { text: "plaque", flag: "read_plaque" }],
      cond: []
    }],
    opts: [{ label: "Enter the tower", target: "hall", cond: [],
             set: "", unset: "", pick: "", leave: "", clear: false,
             popup: "" }]
  }]
};
```

Text lines are stored as rendered `segments` plus conditions. A segment with a `flag` is a selectable word. Option
conditions are `[kind, name]` pairs where `kind` is `if` or `unless`; every pair must hold. Option targets are scene
ids, or `-` for the current scene. `popup` is an empty string or the option's `msg` text; `popupHint` is the
optional dismiss label (the runtime falls back to **Continue** when it is blank). Music fields are intentionally
absent.

The native `system_*` build-time flags (`system_zx`, `system_zx128`, `system_zx48`, `system_sms`, `system_cpc`,
`system_msx2`, `system_gb`) are
folded during export with the web target, so all of them are false: lines/options gated with `if system_zx` are
omitted, and `unless system_zx` lines remain. No `system_*` condition reaches `game.js`; use a generic line for the
web build when a native target needs extra text.

## Story semantics

The runtime mirrors `src/portable/core/game.c` and `src/portable/core/scene.c`:

- Entering a scene sets its `ending:` flag before its text and options are evaluated.
- A text line or option is visible only when all its `if`/`unless` conditions hold.
- Selecting an option with a non-empty `popup:` first shows that text in a modal; after it is dismissed, the option
  applies `clear` first (reset all flags and re-grant `start:` items), then `set`/`unset`/`pick`/`leave`, then
  navigates. `-` re-renders the current scene.
- A `pick` option is hidden while its item is held, and while `carry:` is full when a cap is set.
- A selectable word is one-shot: tapping it sets its flag and re-renders the scene. Once set, it renders as ordinary
  text and is no longer a button.
- Held items are listed in display-name order. Opening one shows its description, its item options, **Drop** (only
  when `carry > 0`, matching the engine) and **Back**.
- An item option is shown only when its `inscene:` matches the current scene (or is absent), its conditions hold, and
  its `pick`/carry rules allow it. Selecting one shows its `popup:` first when set, then applies its effects, closes
  the item sheet and navigates to its target (`-` re-renders the current scene, like a scene option).
- The password screen appears before the first scene when `password:` is set. Matching is case-insensitive and the
  length must be equal, like the engine. This is a client-side story gate, not security.
- **Restart** clears the saved progress, resets flags to `start:` and returns to the first scene.

## Art

Each art uses its selected source PNG, either the per-art `image:` candidate or the same fallback resolution as the
8-bit build. No palette conversion, dithering or NIRVANA+ processing is applied: the web wants the full source image.

`crop: x y w h` is the same percentage rectangle as the editor's Art tab. An art without an explicit crop uses the
centred band-aspect window, where the aspect is `256 / (8 * artRows)` — the same framing the selected platform uses.
`artRows` comes from the first selected system that has an `art_rows` option (ZX first), so the web band follows the
target being authored; it falls back to the ZX/default `art_lines`. A missing art shows a neutral placeholder.

The art frame is capped at `45dvh` and keeps its aspect ratio, so the picture does not swallow a phone screen in
landscape. `image-rendering` is left at the browser default because the source is high resolution.

## Mobile-first layout

- `viewport-fit=cover` plus safe-area padding on `#app`, the item sheet and the inventory bar.
- Base layout: one column (title, art, scene title, text, options, inventory); desktop only widens and centres.
- Fluid `clamp()` type and spacing; no fixed pixel widths.
- Options and inventory entries are at least 44px tall and full-width where appropriate.
- The inventory bar is sticky to the bottom and scrolls horizontally when it has many items.
- The item screen is a bottom sheet on phones and a centred dialog at `min-width: 720px`.
- Focus rings are visible; hover styling is behind `@media (hover: hover)`, and reduced-motion preferences are
  respected.
- Keyboard support: `Up`/`Down` move focus through options and inventory entries, `Enter`/`Space` activate the focused
  control, `Escape` closes the item sheet, and `Enter`/`Space`/`Escape` dismiss a popup message.

## Export

Export writes this tree (and replaces the previous contents, so stale art files cannot survive):

```
<game-folder>/web/
  index.html
  app.js
  style.css
  game.js
  assets/art/<art-id>.png
```

All asset URLs in the exported `game.js` are relative, and the data is a plain script, so opening `index.html`
directly works in every current browser. The folder is gitignored (`<game-folder>/web/`; in this repo
`/demo-game/web/`). The zip contains the same tree
under a top-level `<slug>/` directory.

A headless export is available:

```bash
python3 tools/webgame.py <slug>           # write <game-folder>/web/
python3 tools/webgame.py <slug> --json    # inspect the generated data
```

## Limits and notes

- There is **no music** in the web runtime or the export, even when the game declares PT3 songs for the 8-bit builds.
- There are no save slots; progress (current scene + flags) is saved automatically in `localStorage` under
  `rvn.web.<slug>.state` and restored on reload, so **Restart** is the only state reset.
- The password is checked in the browser; the value is present in `game.js`.
- The runtime does not convert art, so changing a platform palette or dither mode does not change the web picture.
- The web band height is a framing choice only; the story has no screen-budget limits, so long text and many options
  simply scroll.

## Troubleshooting

- **Blank scene**: check that `game.md` has at least one scene and the first scene has valid `art:` and options.
- **Missing art**: the art needs a selected image; generation-only references are not exported.
- **Old art in the Web tab**: entering the tab re-exports when the selected image or its file changed; if the browser
  still shows the old file, click **Reload**, then hard-reload the iframe.
- **Stale export/zip**: **Export web** and **Download zip** both save first and re-run the export.
- **No sound**: expected; music is not part of this runtime.

## Verification

1. `python3 -m py_compile tools/webgame.py tools/editor/editor_web.py tools/editor/server.py`
2. Open the editor **Web** tab (it exports, then previews the folder) and exercise a path through the story, including a
   condition, a selectable word, an item option, Drop/Back and the password.
3. Check a narrow viewport (about 390x844) for tap targets, safe areas, the capped art and the bottom item sheet.
4. `python3 tools/webgame.py <slug>` then open `web/index.html` from `file://`; verify the scene and art load without
   the server.
5. Download the zip, extract it and repeat step 4.
6. Re-export after removing an art and confirm its PNG is gone from `web/assets/art/`.
