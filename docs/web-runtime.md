# Web player

The web player plays a game in any modern browser. It bundles the browser emulator and built file for each system
ticked in the Systems tab. **Every full build writes `<game-folder>/web/`** through the hidden **Web player** step so
the native emulator player is always available. Web is itself a system: ticking `## web` swaps that step for the **Web
game**, which adds the mobile-first novel (the **Web version** entry) to the same player. The two steps are separate,
so a build can produce the player without the web game. Systems that are not selected are never included.

There are two ways to run it:

- **Editor Emulator tab** — the tab saves pending edits, exports the player and auto-starts the exported folder in an
  iframe. It has no selector or toolbar of its own; the editor's top-bar **Export player** button re-exports and
  reloads the preview.
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
  novel/<variant>/        mobile-first story runtime, one per variant
    index.html
    app.js
    style.css
    game.js               generated window.RVN_GAME data
    assets/art/<id>.png
    assets/music/<id>.wav
  emulator/               only the emulator bundles the selected systems need
  files/<variant>/<artifact>  the exact file each variant's native system plays
```

All URLs are relative, so the folder works at a host root, under a project path (for example a GitHub Pages
subpath), or inside an itch.io embed.

## Files

| Path | Purpose |
|---|---|
| `tools/webgame.py` | Player/game export, data files, music rendering, folder export and zip |
| `tools/targets/webplayer.py` | Hidden automatic Web player build (no novel) |
| `tools/targets/web.py` | Web game build (player plus the novel) |
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

The **Web** system (`## web`) owns the **Web version** novel: it is written by the `web` target, which runs when Web
is ticked or when `web` is requested explicitly. The hidden `webplayer` target refreshes the same folder without the
novel. Native entries come from `targets.selected_targets(doc)` (Web itself is not a native entry), in the system
display order:

- A selected system with a bundled web emulator becomes a playable entry: ZX 128K/48K (JSSpeccy), SMS and Game Boy
  Color (EmulatorJS), MSX2 (WebMSX), CPC 6128/464 (CPCJS/Caprice32), C64 (EmulatorJS VICE), NES (EmulatorJS FCEUmm)
  and Oric Atmos (Oricutron).
- The ZX Spectrum Next has no bundled browser emulator, so it is not included in the player.
- A selected system whose built artifact is missing is skipped with an export warning. Build it first for it to appear.
- Unselected native systems are never copied or listed. With Web unticked the automatic `webplayer` step writes no
  `novel/` folders and the player offers only the selected native systems; if nothing is selected it reports that
  there is no game data.

The player itself has no download button. The editor's top-bar **Export player** button re-exports the combined player
and reloads the preview.

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

`novel/<variant>/game.js` assigns one global:

```js
window.RVN_GAME = {
  format: 1,
  slug: "demo-game",
  variant: "en",                 // game-<variant>.md id
  storageKey: "demo-game.en",    // localStorage namespace for progress/sound
  title: "The Lighthouse Keeper",
  artRows: 12,                  // Web art_rows (even, 8..16)
  mono: false,                  // baked mono art + white text when true
  dither: "off",                // mono dither scheme
  popupMenu: false,             // SPACE opens the options menu (see below)
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

`popupMenu` is true when a selected native system uses the portable pop-up options dialog: SMS, Game Boy Color, C64
and NES always do, and ZX, CPC, MSX1, MSX2, Next and Oric do when their `menu: popup` option is set. The novel then
hides the pinned options and inventory band and keeps them behind an **Options** button and the SPACE key, matching
the native build: SPACE opens the options menu. The menu lists the visible scene options first, then held items
prefixed `*`; SPACE (or Escape, the close button or the backdrop) closes it. With no such system selected the options
and inventory stay pinned on screen.

The native `system_*` build-time flags are folded during export with the web target, so all of them are false:
lines/options gated with `if system_zx` are omitted, and `unless system_zx` lines remain.

`player-data.js` assigns `window.RVN_PLAYER`. Each variant carries its own story path and native systems; the player
shows a variant selector at the top when more than one entry is present (`web`/`systems` are kept as an alias for the
primary variant):

```js
window.RVN_PLAYER = {
  format: 1,
  slug: "demo-game",
  title: "Demo Game",
  variants: [
    { id: "en", label: "en", title: "Demo Game",
      src: "novel/en/index.html", popupMenu: false,
      systems: [
        { id: "zx128", label: "ZX Spectrum 128K", kind: "native",
          variant: "en", emulator: "jsspeccy", machine: "128", page: "",
          file: "files/en/demo-game-en.tap", filename: "demo-game-en.tap",
          aspect: 1.333333, media: "tape", mediaLabel: "Tape" }
      ] },
    { id: "es", label: "es", title: "Juego de demostración",
      src: "novel/es/index.html", popupMenu: false, systems: [/* ... */] }
  ],
  web: { label: "Web version", src: "novel/en/index.html", machine: "HTML5",
         popupMenu: false },
  systems: [/* the primary variant's systems */]
};
```

Switching the variant stops the current emulator or iframe, rebuilds the system list for that variant and starts the
same system id when present (otherwise the variant's Web novel). The selection is saved in
`localStorage["rvn.player.<slug>.variant"]`; scenes/flags and sound use the novel's `storageKey`, so each variant has
its own progress.

## Music

`# Game songs:` declares PT3 modules. Each scene's `music:` (or the game default) is resolved by
`scenefile.resolve_song`. The exporter renders each used module with `spectrumizer.play` to a 22050 Hz mono WAV in
`novel/<variant>/assets/music/`, reusing the `assets/gen/song_<id>.wav` cache. If `spectrumizer` is unavailable the export still
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
8-bit build. By default no palette conversion, dithering or NIRVANA+ processing is applied: the web wants the full
source image.

The Web system has its own options under `## web`:

- `art_rows:` (even 8..16, default 10) sets the novel band height to 256 x `8 * art_rows` pixels, independent of the
  native systems.
- `mono: on` (the Systems tab's **Black and white**) bakes each art to a dithered 1-bit black-and-white PNG at the Web
  band size, forces white text on black, and re-fits an explicit crop to the Web band aspect before conversion.
- `dither:` chooses the mono scheme (`bayer2`…`sierra`); `off` becomes the 2x2 Bayer dither. It has no effect while
  Black and white is off, when the full-colour source is copied unchanged.

`crop: x y w h` is the same percentage rectangle as the editor's Art tab. An art without an explicit crop uses the
centred band-aspect window, where the aspect is `256 / (8 * artRows)`. An explicit crop keeps its full width and
re-centres its vertical window to that aspect (clamped to the source), so a crop authored for another band height is
never stretched; the colour runtime does this in CSS while mono bakes it at export. A missing art shows a neutral
placeholder. The Art tab lists a **Web** preview alongside the selected native previews, using the Web options above
(including unsaved control changes).

The art frame is capped at `45dvh` and keeps its aspect ratio, so the picture does not swallow a phone screen in
landscape. Colour art keeps the browser's default image scaling; baked mono art uses `image-rendering: pixelated` so
the dither stays crisp.

## Player layout

- The system selector is a retro right-hand sidebar of rocker keys: the Web version (when Web is ticked) first, then
  only the selected native systems. A media bay above it shows the matching tape, disk, cartridge or web icon for the
  current system.
- The Web version uses the full mobile-first novel in an iframe.
- Native systems use JSSpeccy inline or the pinned emulator page in an iframe. The screen keeps the system's display
  aspect ratio.
- On a coarse-pointer (touch) device the native ZX Spectrum entry also draws a `.speccy-touch` pad below the screen:
  a D-pad plus `ENTER`, `SPACE` and `P`. The buttons synthesize the key events JSSpeccy expects (bare `5`/`6`/`7`/`8`
  for the directions, `SPACE` for the pop-up action dialog), because JSSpeccy has no soft keyboard. It shares the
  `screenwrap.has-touch` layout and reserves its height when scaling the picture.
- The panel shows the selected system, a hint, **Reload** and **Fullscreen**.
- `?system=<id>` selects a system directly (useful for links and testing); otherwise the last system is restored from
  `localStorage`, defaulting to the Web version (or the first native system when Web is unticked).

## Export

```bash
python3 tools/build.py build <game>             # native systems + automatic Web player
python3 tools/build.py build <game> zx128       # zx128 + Web player (no novel)
python3 tools/build.py build <game> web         # Web game (player + novel)
python3 tools/build.py build <game> webplayer   # Web player only
python3 tools/webgame.py <slug>                 # selection-based export
python3 tools/webgame.py <slug> --player        # player only
python3 tools/webgame.py <slug> --game          # player plus the novel
python3 tools/webgame.py <slug> --json          # inspect the novel data
```

Every build runs the automatic Web player last, after the native artifacts it bundles, so `<game-folder>/web/` is
always refreshed. A build of one native system therefore refreshes the player without touching the novel. Ticking
`## web` under `# Systems` makes the `web` target replace that player step with the Web game, adding the `novel/`
subtree and the **Web version** entry. The folder is replaced atomically. The zip produced by
`GET /api/webzip/<slug>` has `index.html` at the archive root and is ready to upload to itch.io as an HTML game. The
folder is gitignored (`<game-folder>/web/`; in this repo `/demo-game/web/`).

## Limits and notes

- The Web novel has music, but no save slots; progress (current scene + flags) is saved automatically in `localStorage`
  under `rvn.web.<slug>.state` and restored on reload. **Restart** is the only state reset.
- The password is checked in the browser; the value is present in `game.js`.
- Colour novel art is not converted; the Web `mono`/`dither` options apply to the baked black-and-white band only.
- The web band height is a framing choice only; the story has no screen-budget limits, so long text and many options
  simply scroll.
- Native emulator entries need a web server (or a host such as itch.io/GitHub Pages); opening the player from
  `file://` only guarantees the Web novel.
- Missing native artifacts, unrenderable songs and systems without a browser emulator are reported as export warnings.

## Troubleshooting

- **Web player entry is missing pieces**: build the selected systems first; the export lists the missing filenames.
- **Blank scene**: check that `game.md` has at least one scene and the first scene has valid `art:` and options.
- **Missing art**: the art needs a selected image; generation-only references are not exported.
- **Old art in the player**: click the editor's top-bar **Export player** button (it re-exports and reloads the
  preview) or the player's **Reload**.
- **No music**: check that the game declares `songs:` and `assets/music/<id>.pt3` exists, and that the export reported
  no song warning.

## Verification

1. `python3 -m py_compile tools/webgame.py tools/editor/editor_web.py tools/editor/server.py`
2. Open the editor **Emulator** tab; it saves pending edits, exports and starts the player automatically.
3. Exercise the novel, including sound on/off, a scene music change and **Restart**.
4. Use the top-bar **Export player** button and confirm the preview reloads; switch to a native system and confirm it
   boots.
5. `python3 tools/webgame.py <slug>`, serve the folder over HTTP and repeat; verify only selected systems appear and
   the zip has `index.html` at its root.
