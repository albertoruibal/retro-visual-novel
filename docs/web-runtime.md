# Web player

The web player plays a game in any modern browser. It contains the mobile-first story runtime and, for each system
ticked in the Systems tab, the matching web emulator and the built file it plays. Systems that are not selected are
never included.

There are two ways to run it:

- **Editor Emulator tab** — choose **Web player** as the system. The editor saves pending edits, exports the player
  and previews the exported folder in an iframe. The same tab can export the folder, open it in a new tab, or download
  the itch.io-ready zip.
- **Exported folder** — a self-contained `<game-folder>/web/` tree that can be copied to any static host, uploaded to
  itch.io, or opened directly (the Web novel works from `file://`; the native emulators need an HTTP host).

The runtime is **frontend-only**: story playback lives in `tools/webgame_runtime/app.js`; the player shell and system
selector live in `tools/webplayer_runtime/`. Python only exports data and copies static files at build time. The
editor server never generates story data per request.

## Layout

```
<game-folder>/web/
  index.html              player shell
  player.js               system selector, native emulator embedding
  player-data.js          generated window.RVN_PLAYER data
  style.css
  novel/                  mobile-first story runtime
    index.html
    app.js
    style.css
    game.js               generated window.RVN_GAME data
    assets/art/<id>.png
    assets/music/<id>.wav
  emulator/               only the emulator bundles the selected systems need
  files/<artifact>        the exact file each native system plays
```

All URLs are relative, so the folder works at a host root, under a project path (for example a GitHub Pages
subpath), or inside an itch.io embed.

## Files

| Path | Purpose |
|---|---|
| `tools/webgame.py` | Player export, data files, music rendering, folder export and zip |
| `tools/webplayer_runtime/index.html` | Player shell |
| `tools/webplayer_runtime/player.js` | System selector, JSSpeccy and iframe emulator boot |
| `tools/webplayer_runtime/style.css` | Player layout |
| `tools/webgame_runtime/index.html` | Novel shell |
| `tools/webgame_runtime/app.js` | Scene/flag/item engine, music playback and DOM rendering |
| `tools/webgame_runtime/style.css` | Mobile-first novel layout and theme |
| `tools/editor/static/player.js` | Editor Emulator-tab export/preview actions |
| `tools/editor/editor_web.py` | Static export serving, export and zip routes |

The runtime is plain classic JavaScript: no modules and no bundler. `index.html` loads `player-data.js` and `player.js`
in the player shell, and `game.js` then `app.js` in the novel.

## Selected systems

The player always offers the **Web version** novel. Native entries come from `targets.selected_targets(doc)`, in the
system display order:

- A selected system with a bundled web emulator becomes a playable entry: ZX 128K/48K (JSSpeccy), SMS and Game Boy
  Color (EmulatorJS), MSX2 (WebMSX), CPC 6128/464 (CPCJS/Caprice32), C64 (EmulatorJS VICE), NES (EmulatorJS FCEUmm)
  and Oric Atmos (Oricutron).
- The ZX Spectrum Next has no bundled browser emulator, so it appears as a download-only entry.
- A selected system whose built artifact is missing is skipped with an export warning. Build it first for it to appear.
- Unselected systems are never copied or listed.

Native entries show **Download `<filename>`** for the exact file the emulator plays (`.tap`, `.sms`, `.dsk`, `.rom`,
`.prg`, `.nes`, `.gbc`, etc.). The Web version has no download button.

## Routes

| Route | Purpose |
|---|---|
| `GET /play/<slug>/` | The exported player shell |
| `GET /play/<slug>/<file>` | Any file from `<game-folder>/web/` (novel, emulator, files) |
| `GET /play/<slug>` | Redirect to the trailing-slash form |
| `POST /api/web_export` | Write `<game-folder>/web/` and return its info |
| `GET /api/webzip/<slug>` | Re-export and download the itch.io-ready zip |

`/play/` never generates story data: it serves the exported folder, and path containment prevents walking outside it.

## Data model

`novel/game.js` assigns one global:

```js
window.RVN_GAME = {
  format: 1,
  slug: "demo-game",
  title: "The Lighthouse Keeper",
  artRows: 12,                  // selected system's art_rows (even, 8..16)
  startScene: "start",
  startItems: [],
  carry: 0,
  password: "",
  passwordLabel: "Enter the password:",
  popupHint: "Continue",
  inventory: { drop: "Discard", back: "Close" },
  textColors: { ink: "#c0c0c0", highlight: "#ffff00", bg: "#000000" },
  itemOrder: ["key", "seed", "lamp"],
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
  songs: {
    theme: { src: "assets/music/theme.wav" }
  },
  scenes: [{
    id: "start",
    title: "The Lighthouse Keeper",
    art: "title",
    ending: "",
    music: "theme",
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

Text lines are rendered `segments` plus conditions. A segment with a `flag` is a selectable word. Option conditions are
`[kind, name]` pairs where `kind` is `if` or `unless`; every pair must hold. Option targets are scene ids, or `-` for
the current scene. `popup` is an empty string or the option's `msg` text. A scene's `music` is a song id or `null`;
songs that could not be rendered are removed and the scene becomes silent.

The native `system_*` build-time flags are folded during export with the web target, so all of them are false:
lines/options gated with `if system_zx` are omitted, and `unless system_zx` lines remain.

`player-data.js` assigns `window.RVN_PLAYER`:

```js
window.RVN_PLAYER = {
  format: 1,
  slug: "demo-game",
  title: "The Lighthouse Keeper",
  web: { label: "Web version", src: "novel/index.html", machine: "HTML5" },
  systems: [
    { id: "zx128", label: "ZX Spectrum 128K", kind: "native",
      emulator: "jsspeccy", machine: "128", page: "",
      file: "files/demo-game.tap", filename: "demo-game.tap", aspect: 1.333333 }
  ]
};
```

## Music

`# Game songs:` declares PT3 modules. Each scene's `music:` (or the game default) is resolved by
`scenefile.resolve_song`. The exporter renders each used module with `spectrumizer.play` to a 22050 Hz mono WAV in
`novel/assets/music/`, reusing the `assets/gen/song_<id>.wav` cache. If `spectrumizer` is unavailable the export still
succeeds with a warning and no music.

The novel creates a looping `<audio>` element, switches tracks when the scene's song changes, pauses for `music: off`,
and restarts the current track on **Restart**. Browsers block autoplay until the player interacts, so the first click or
key press starts playback. A **Sound: on/off** button is shown only when the game has songs; its state is persisted
under `rvn.web.<slug>.sound`.

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

## Player layout

- The system selector lists the Web version first, then only the selected native systems.
- The Web version uses the full mobile-first novel in an iframe.
- Native systems use JSSpeccy inline or the pinned emulator page in an iframe. The screen keeps the system's display
  aspect ratio.
- The panel shows the selected system, a hint, **Download `<filename>`** for native systems only, **Reload** and
  **Fullscreen**.
- `?system=<id>` selects a system directly (useful for links and testing); otherwise the last system is restored from
  `localStorage`, defaulting to the Web version.

## Export

```bash
python3 tools/webgame.py <slug>           # write <game-folder>/web/
python3 tools/webgame.py <slug> --json    # inspect the novel data
```

The folder is replaced atomically. The zip produced by `GET /api/webzip/<slug>` has `index.html` at the archive root and
is ready to upload to itch.io as an HTML game. The folder is gitignored (`<game-folder>/web/`; in this repo
`/demo-game/web/`).

## Limits and notes

- The Web novel has music, but no save slots; progress (current scene + flags) is saved automatically in `localStorage`
  under `rvn.web.<slug>.state` and restored on reload. **Restart** is the only state reset.
- The password is checked in the browser; the value is present in `game.js`.
- The runtime does not convert art, so changing a platform palette or dither mode does not change the web picture.
- The web band height is a framing choice only; the story has no screen-budget limits, so long text and many options
  simply scroll.
- Native emulator entries need a web server (or a host such as itch.io/GitHub Pages); opening the player from
  `file://` only guarantees the Web novel.
- Missing native artifacts and unrenderable songs are reported as export warnings.

## Troubleshooting

- **Web player entry is missing pieces**: build the selected systems first; the export lists the missing filenames.
- **Blank scene**: check that `game.md` has at least one scene and the first scene has valid `art:` and options.
- **Missing art**: the art needs a selected image; generation-only references are not exported.
- **Old art in the player**: click **Export player** or **Reload**; the iframe only reloads when the export revision
  changes.
- **No music**: check that the game declares `songs:` and `assets/music/<id>.pt3` exists, and that the export reported
  no song warning.

## Verification

1. `python3 -m py_compile tools/webgame.py tools/editor/editor_web.py tools/editor/server.py`
2. Build the selected systems, then open the editor **Emulator** tab and choose **Web player**.
3. Exercise the novel, including sound on/off, a scene music change and **Restart**.
4. Switch to a native system, confirm it boots and its download link matches the played file.
5. `python3 tools/webgame.py <slug>`, serve the folder over HTTP and repeat; verify only selected systems appear and
   the zip has `index.html` at its root.
