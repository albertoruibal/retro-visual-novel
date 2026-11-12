# AGENTS.md

Guidance for coding agents working in this repository.

## What this is

Retro Visual Novel is an 8-bit visual novel authoring + build system for the **ZX Spectrum 128K**, **ZX Spectrum
48K**, **ZX Spectrum Next** and six portable targets. The story engine is shared by every target
(`src/portable/core/`); each platform
supplies a thin layer (`src/zx/plat_zx.c`, `src/next/plat_next.c`, `src/sms/`, `src/cpc/`, `src/msx1/`, `src/msx2/`, `src/gb/`,
`src/c64/`, `src/nes/`, `src/oric/`). The three 6502 targets share `src/6502/zx0.c`.
NIRVANA+ is vendored under `vendor/`. A game
is a self-contained folder whose story lives in `game.md`; this repository ships a single demo game in `demo-game/`.
A stdlib-only Python editor (`tools/editor/server.py`) serves a browser UI to author games, generate art with local
models, and run the build.

Read `README.md` first for the overview, authoring format, editor and model setup; the ZX memory map and NIRVANA+
constraints live in `docs/systems/zx128.md`.

## Layout

    src/zx/                  ZX platform layer (plat_zx.c, engine.h)
                             + paging/loader asm (loader48.asm for the flat 48K build)
    src/next/                ZX Next platform layer (Layer 2, Next MMU paging, IM1 AY)
    src/portable/core/       shared story engine + music player for every target
    src/portable/plat.h      platform surface implemented by each src/<target>/
    src/z80/zx0_wrap.asm     shared Z80 C wrapper for the vendored ZX0 decoder
    src/6502/zx0.c           shared 6502 C ZX0 decoder (C64 + NES + Oric)
    src/sms/ src/cpc/        platform layers and paging/vram asm
    src/msx1/ src/msx2/      MSX platform layers (MSX1 TMS9918A, MSX2 V9938)
    src/gb/                  platform layer (GB APU player in src/gb/gb_music.c)
    src/c64/ src/nes/        6502 platform layers (VIC-II MCM / NES PPU, MMC1 asm)
    src/oric/                Oric Atmos HIRES platform layer + atmos.cfg
    vendor/zx0/              pinned ZX0 decoder (69-byte standard, BSD-3)
    vendor/pixeloperator8/   pinned CC0 8x8 font for GBC/SMS/MSX2 text
    demo-game/assets/music/  per-game PT3 modules (assets/music/<id>.pt3)
    demo-game/assets/art/<id>/ per-art candidate images (image: picks one)
    demo-game/assets/refs/<id>/ per-reference images (## <id> under # References; refs: picks them)
    NIRVANAP_ENGINE.asm      built/generated engine listing (ignored by git)
    vendor/nirvanap/         pinned NIRVANA+ engine (TOTAL_ROWS=art_rows, @0xDC03)
    tools/scenefile.py       the ONE parser/serializer for game.md (shared)
    tools/gamestore.py       open/create/duplicate/rename game folders (demo-game/)
    tools/gen_scenes.py      game.md -> build/scene_data.h + port_data.h
                             + bankN.bin + *.asm
    tools/targets/           pluggable build targets (zx128, zx48, next, sms, cpc, cpc464, msx2, gb, c64, nes, oric, web)
    tools/smsart.py          SMS art preview/build conversion
    tools/pt3frames.py       shared spectrumizer PT3 replay/envelope front-end
    tools/smsmusic.py        PT3 -> SN76489 PSG stream for the SMS runtime
    tools/gbmusic.py         PT3 -> Game Boy APU register stream for the GBC runtime
    tools/cpcart.py          CPC Mode 0/1/2 art preview/build conversion
    tools/c64art.py          C64 VIC-II multicolor art preview/build conversion
    tools/nesart.py          NES 4-colour tile art preview/CHR bank conversion
    tools/oricart.py         Oric HIRES monochrome band preview/conversion
    tools/cc65path.py        locate the cc65 6502 toolchain (C64/NES/Oric)
    tools/msx1art.py         MSX1 TMS9918A Screen 2 art preview/build conversion
    tools/msx2art.py         MSX2 V9938 Screen 7 art preview/build conversion
    tools/gbart.py           Game Boy Color art preview/build conversion
    tools/gen_images.py      game.md art sections -> PNG via Qwen/SD server
    tools/zxart.py           PNG -> 48-byte Spectrum btiles (needs Pillow)
    tools/build.py           build/run driver (z88dk + appmake), sh-free/portable
    tools/z88dkpath.py       z88dk location helper (Snap detection) shared by server/build
    tools/adventure.sh       compatibility wrapper -> tools/build.py
    tools/requirements.txt   editor/build Python deps (Pillow, numpy, spectrumizer)
    docs/systems/            one page per target (particularities, memory, emulator)
    tools/make_tap.py        append raw bank blocks to the appmake TAP
    tools/make_tap48.py      append the flat 48K lower-RAM block to the TAP
    tools/make_sna.py        pack a 128K SNA with every bank resident
    tools/editor/server.py   entry/state + HTTP API + static SPA
    tools/editor/editor_*.py feature modules (games, validation, images, music,
                             build, static)
    tools/editor/static/     index.html + topic-split JS/CSS (the SPA)
    tools/editor/static/monaco/  vendored Monaco 0.52.2 (Source tab editor)
    electron/main.js         desktop shell: spawns server.py + BrowserWindow
    electron/preload.js      the window.rvn native bridge (open folder, recents)
    electron/build/icon.svg  icon source; icon.png (1024) + icons/ are rasterised
    electron/scripts/prepare-python.js  stage .venv from tools/requirements.txt
    electron/scripts/bundle.js          assemble dist-resources/ for packaging
    demo-game/               the demo game (the only game in this repo)
    demo-game/game.md        story (game / art / ref / scene sections)
    demo-game/assets/        art/<id>/, refs/<id>/ and music/<id>.pt3 sources
    demo-game/build/         generated intermediates/banks (gitignored)

Generated per-game files live in `<game-folder>/build/` (`scene_data.h`, `scene_banks.asm`, `scene_bankN.asm`,
`scene_flags.txt`, the `.bin`/`port_*` intermediates and `scene_banks/bankN.bin`) and are gitignored. Only the playable
outputs (`<slug>.tap`, `.sna`, `.sms`, `.dsk`, `.rom`, `.gbc`, `.prg`, `.nes`) and the editor's `game.md.bak` stay at
the game root
(for the demo, `demo-game/`). Do not hand-edit generated files; edit `game.md` and rebuild.

## Build / run

Native build needs z88dk (`Z88DK`, default: a detected Snap install, else `/tmp/z88dk`) and Pillow for `zxart.py`.
The Commodore 64, NES and Oric Atmos targets use **cc65** (`CC65`/`RVN_CC65` or the saved `cc65_path`), not z88dk. This dev box does
**not** have zcc installed, so builds normally run inside the editor Docker image (which now also contains cc65):

    docker compose up -d --build          # editor on http://localhost:8765

If the editor container is already up, the reliable build recipe is (zcc is at `/opt/z88dk`, the project is live-mounted
at `/src`, and `PATH` does not include `zcc`, so pass `Z88DK` and `sh -lc`):

    docker exec retro-visual-novel-editor-1 sh -lc \
        'Z88DK=/opt/z88dk python3 tools/build.py build demo-game'

Useful commands:

    python3 tools/build.py list-targets
    python3 tools/build.py build demo-game    # every system selected in game.md
    python3 tools/build.py build demo-game sms cpc cpc464 gb
    python3 tools/build.py build demo-game c64 nes   # cc65 targets
    python3 tools/build.py list-targets              # shows cc65 availability
    python3 tools/build.py run   demo-game    # build then launch the ZX emulator
    python3 tools/editor/server.py        # editor without Docker (port 8765)
    python3 tools/gen_scenes.py demo-game     # regenerate tables/banks only
    python3 tools/gen_images.py --game demo-game [art]   # needs the SD server

Desktop app (Electron): `electron/main.js` spawns the same `server.py` on a free loopback port, waits for `/api/health`,
and loads it in a `BrowserWindow`; `electron/preload.js` exposes `window.rvn` (native folder pickers + "remember last
game" in `app.getPath("userData")`). The renderer/SPA is unchanged. The server's Python deps (Pillow/numpy/spectrumizer,
listed in `tools/requirements.txt`) come from a local `.venv` staged by `electron/scripts/prepare-python.js`, so the app
does not need them on system Python. Dev-run:

    cd electron && npm install && npm run venv && npm start   # add RVN_NO_SANDBOX=1 on Linux if needed

`prepare-python.js` uses `uv` when present (relocatable venv), else `python3 -m venv`; `--stage <dir>` copies the venv
to `<dir>/python` for packaging. cc65 is **not bundled** either: the desktop app uses `CC65`/`RVN_CC65` or the saved
`cc65_path` from the same **Build toolchain** card; users install cc65 for their host (`bin/cl65` etc.).
`pythonExe()` prefers `<resources>/python` (packaged) then `<root>/.venv` (dev) then
system `python3`. z88dk is **not bundled**: `z88dkDir()` returns an explicit `Z88DK`/`RVN_Z88DK`, else the editor's
saved `z88dk_path`, else a detected Snap install (`/snap/z88dk/current`), else `""`, and the build then reports the
missing toolchain. Users point the Settings **Build
toolchain (z88dk)** card at a tree built for the **target OS/CPU** (a nightly download from `http://nightly.z88dk.org`,
the Docker image, or a source build) — the editor Docker image's `/opt/z88dk` is musl/Alpine and will not run on a glibc
host. `npm run bundle` assembles `electron/dist-resources/{engine,python}` into the `extraResources` layout
electron-builder copies to `<resources>`. `RVN_SMOKE=1` opens the window, prints `window.rvn` keys and quits (headless
CI check). Set `RVN_GAME` to open a folder at startup.

Packaging: `npm run pack` builds an unpacked app to `electron/dist/linux-unpacked`; `npm run dist` builds the per-OS
artifacts (Linux AppImage + deb, Windows nsis, macOS dmg) into `electron/dist/`. The output is **gitignored and not
committed** — it is regenerated on demand, so there is nothing to fetch. A full Linux build is:

    cd electron && npm install && npm run venv && npm run dist
    # -> electron/dist/Retro Visual Novel-<version>-linux-x86_64.AppImage  (+ .deb)

(The AppImage is ~120 MB and is simply deleted by any `rm -rf electron/dist` cleanup.) z88dk is no longer staged or
bundled, so a packaged app always needs a toolchain chosen at runtime (Settings, `$Z88DK`/`$RVN_Z88DK`, or a detected
Snap install on Linux). Only the
Linux targets build off-Linux (Windows/macOS need wine/a mac). Artifacts are unsigned by default; signing/notarization
use the usual electron-builder env (`CSC_LINK`/`CSC_KEY_PASSWORD` for win/mac,
`APPLE_ID`/`APPLE_APP_SPECIFIC_PASSWORD`/`APPLE_TEAM_ID` for notarization). A packaged run resolves `engineRoot()` and
`pythonExe()` under `<resources>` and `z88dkDir()` from the environment/settings (verified by launching the built
AppImage with `RVN_SMOKE`).

The icon source is `electron/build/icon.svg`; `icon.png` (1024) and `build/icons/` (16..512) are rasterised from it.
`electron/main.js` sets the window icon (resized to 192 px so X11 accepts it), calls `app.setDesktopName()`, and
registers a Wayland `.desktop` entry for dev and AppImage runs. Windows/macOS derive their ICO/ICNS from `icon.png`;
there is no committed `.ico`.

Env (editor): `EDITOR_HOST`, `EDITOR_PORT`, `STABLE_DIFFUSION_URL`, `Z88DK`, `RVN_SETTINGS`.
`STABLE_DIFFUSION_URL` points at the image server on the **host** (use
`http://host.docker.internal:<port>`; compose maps it via `extra_hosts`). An unset variable disables image generation
and the UI hides its controls. The endpoint can instead be set at runtime in the top-bar **Settings** modal's
**Image server** card: `GET/POST /api/settings` read/validate/persist it to `RVN_SETTINGS` (a JSON file; Electron
passes its userData `settings.json`) and `apply_settings()` mutates the `STABLE_DIFFUSION_URL` + `IMAGE_ENABLED` globals
in place — a stored value wins over the env var, a blank value disables the feature. The old `ZXAD_*` environment names
and the old `zx-novel`/`zxadventure` config directories are still accepted as fallbacks, and the settings file is
migrated to `retro-visual-novel` on first run.

The same modal's **Build toolchain (z88dk)** card sets `z88dk_path` (a directory; blank falls back to `$Z88DK`, then a
detected Snap install (`/snap/z88dk/current`), then `/tmp/z88dk`). `settings_payload()` also reports `z88dk_valid` (a
`bin/zcc[.exe]` hint; an invalid path is still saved),
`z88dk_default`, and `z88dk_effective`/`z88dk_available`/`z88dk_missing` (the host tools the build needs: `zcc`,
`z88dk-z80asm`, `z88dk-appmake`, `z88dk-zx0`). A folder picked with **Browse…** is saved immediately. Clicking **Build**
with an incomplete toolchain opens the toolchain card instead of starting; `POST /api/build` and `tools/build.py` also
refuse with the missing tool names. `_run_build()` injects `env["Z88DK"]` from the effective path before spawning
`tools/build.py` (which derives `ZCCCFG` + the `bin/` `PATH` entry), and `tools/build.py` reads the same settings file
when `$Z88DK` is unset, so CLI builds honour the UI choice. Shared detection lives in `tools/z88dkpath.py`
(`SNAP_ROOTS` + `detected()`/`default_root()`); `z88dk_valid` still only decides whether a configured tree looks usable.
In Electron `electron/main.js:z88dkDir()` prefers
`$Z88DK`/`$RVN_Z88DK`, then the stored `z88dk_path`, then a detected Snap install (nothing is bundled; the card's hint
explains that nightly tarballs are source-only and lists the Linux routes: build the tarball, the Snap, or the
musl/Alpine Docker image). The folder picker is the generic `window.rvn.pickDir()` bridge (`rvn:pick-dir`).

## Verifying changes

There is no test suite and no configured linter. Verify by:

1. `python3 -m py_compile tools/*.py tools/editor/server.py` for Python edits.
2. A full build (`python3 tools/build.py build demo-game` or the editor **Build** button) for anything touching
   `game.md` format, `gen_scenes.py`, the engine, or the editor's save path. The Game Boy Color target needs
   `z88dk-zsdcc`, so build it in the editor container
   (`Z88DK=/opt/z88dk python3 tools/build.py build demo-game gb`) and check the `.gbc` header/ROM banks. The C64/NES/Oric
   targets need cc65 in the container (`cl65 -t c64` / `cl65 -t nes` / `cl65 -t atmos`); check the `.prg` load
   address/size, the `.nes` iNES header (PRG=2, mapper=1, CHR count) and CHR bank file, and the Oric `.tap` map/BSS
   bounds.
4. **Headless screen check** for engine/art changes: `tools/spectrum.py` drives ZEsarUX-13.0 (in the repo) over ZRCP, no
   X server.
3. For editor UI edits, start the server and exercise the affected tab; the UI is plain ES modules-free JS split by
   topic under `tools/editor/static/` (classic `<script src="/static/<topic>.js">` tags sharing one global scope), no
   bundler. For C64/NES screen checks run VICE
   (`x64sc -autostartprgmode 1 -autostart ... -limitcycles ... -exitscreenshot`) or FCEUX under `xvfb-run`; those
   desktop emulators are not vendored (the editor bundles the VICE/FCEUmm web cores for in-browser play).
4. **Headless screen check** for engine/art changes: `tools/spectrum.py` drives ZEsarUX-13.0 (in the repo) over ZRCP, no
   X server. On a fresh box it needs `libsdl1.2-compat` (provides `libSDL-1.2.so.0`) and `libncurses6`, or it dies with
   `fuse did not start`:

       sudo apt-get install -y libsdl1.2-compat libncurses6
       python3 tools/spectrum.py run <game-folder>/<slug>.tap    # start on 10001+
       python3 tools/spectrum.py cli "smartload /abs/path/<slug>.tap"
       python3 tools/spectrum.py shot NAME                      # tools/out/NAME.scr
       docker exec retro-visual-novel-editor-1 sh -lc \
           'python3 tools/render_zx_screen.py tools/out/NAME.scr tools/out/NAME.png'
       python3 tools/spectrum.py off

   `shot` also wants Pillow (absent on the host), so render inside the container as above. `smartload` needs an
   **absolute** `.tap` path; the harness only finds running instances on ports 10001–10019.

## Invariants and gotchas

- **`game.md` has exactly one reader/writer: `tools/scenefile.py`.** The build (`gen_scenes.py`) and the editor both
  import it. Any format change goes there first; never parse the format ad hoc elsewhere.
- Every save re-serialises canonically via `scenefile.serialize()`, which re-emits the single `# game.md — ...` banner
  (`scenefile.HEADER`) at the top; the author-facing format documentation lives in `docs/authoring.md` (so
  `bundle.js` copies `docs/` into the packaged app). Raw text edits do not pass through the serializer; the banner is
  optional on read (prose is ignored).
- **NIRVANA+ never touches rows 0 and 23** and races attribute rows `1..art_rows` (the art band). Row 0 sits above the
  art and carries the scene title (`show_scene` clears it with `clr_row(0, 0x00)` and draws `title_off` there); row 23
  is the single-line inventory band. The title uses the `## zx128 title_ink` system option (`text` inherits `text_ink`,
  emitted as `TITLE_INK`/`TITLE_BRIGHT` in `port_data.h`; it also colours the item screen and boot-screen title).
  `clr_inventory_bg` clears only row 23 so the title survives band redraws while the
  cursor is on the band (the item/Drop screen also clears it while its details show; the scene redraw on return restores
  it). **`## zx128 art_rows` (even 8..16, default 10) sets the band height in character rows**: the engine is built with
  `TOTAL_ROWS = art_rows`, `TEXT_TOP = 1 + ART_LINES`, `TEXT_BOT = 22`, so the text band is rows `art_rows+1..22` and
  the budget is `22 - art_rows`. **`## zx48 art_rows` is an independent per-system option** (default 10), so lowering
  the 48K band frees text rows without changing the 128K band; a legacy shared `# Game art_lines` value is copied
  into `zx48_art_rows` on load when the 48K block has no `art_rows`. Scene text and item descriptions may be any
  length and word-wrap at 62 columns; options/labels are <= 62 columns. Keep <= 8 logical text lines and <= 6
  options. On the pinned layout the server validates the worst-case wrapped text rows + options over all flag/item
  combinations against each selected layout's `22 - art_rows` (and the item screen's description + entries against
  `21 - art_rows`); with `menu: popup` the text and item descriptions scroll and there is no fit limit. Scene text
  is top-aligned and the options are pinned to the bottom of the band (last option on `TEXT_BOT`); the item/drop
  (`ITEM_DESC_TOP`/`ITEM_DESC_ROWS`/`TEXT_BOT`) and
  boot-password screens are band-relative so they fit any height, and on the pinned layouts the item screen's
  options/Drop/Back entries are pinned to the bottom the same way. The description is clamped so the entries fit
  (`21 - art_rows - entries` description lines). On the dialog layouts (`PORT_OVERLAY_MENU`) the entries instead start
  immediately below the description, which is clamped to the rows the entries leave free. On pinned ZX item-entry
  labels are truncated rather than wrapped (`PORT_NO_ENTRY_WRAP`), and scroll markers use `PORT_SCROLL_COL` 61:
  printing the last cell makes the ZX ROM scroll the whole screen and shift the NIRVANA+ band.
- **The NIRVANA+ engine is rebuilt per game** with `TOTAL_ROWS = art_rows`: `tools/build.py` writes a temp
  `config_private.inc` (patching the `defc` and the m4 `define` line) and passes `-m4=-I<tmpdir>` **before** the
  vendored include, so only bytes inside the engine's padded hole change — `org_nirvanap` stays `0xDC03`.
  `tools/build.py` also regenerates `build/adventure_NIRVANAP.bin` from that same linked engine on every build (9064 B, or
  9073 B when the password screen adds the fillT wrapper) and checks it against the link map, so the TAP/SNA can never
  merge the previous TOTAL_ROWS. `adventure.c` derives `ART_ROWS = ART_LINES/2` and `TEXT_TOP`.
- **Art tile row `r` uses `lin = r*16 + 16`** (`ART_LIN` in `adventure.c`). NIRVANA+ maps `lin` to pixel row `lin-8`, so
  image row `r` covers pixel rows `16r+8..16r+23` = raced attribute rows `2r+1..2r+2`; image row 0 lands in row 1 and
  the last row in `art_rows-1`. The band is 16 x `art_rows/2` tiles (map `8*art_rows` bytes). `drawT` and `fillT`
  must share this mapping. An off-by-8 here shifts the whole picture up one row (row 0 lost, the bottom row blank) — see
  commit `c27452a`.
- **Art source crop is per art.** `crop: <x> <y> <w> <h>` on an art (`scenefile.art_crop`, mirroring `zxart.crop_rect`)
  is the source rectangle, in percent of the source, that maps to the art band (256x(8*art_rows); aspect
  `32/art_rows`). Absent (the default) is the centred band-aspect window: the whole frame for a source that already
  matches, else a full-width or full-height strip. `zxart._fit_band` (plus `nirvana_band`, `classic_band`,
  `bifrost_band`, `band_to_art`, `render_band_png` — all take an optional `rows` of 16px tile rows) crops that rectangle
  and scales it to the band once at conversion (the build and the editor previews share it), so the engine carries no
  crop state. The non-ZX targets use `zxart.band_crop_rect`: an explicit crop keeps its full width and re-centres its
  vertical window to the target band aspect (clamped to the source), so it is never stretched or cropped sideways.
  The Art tab overlays a box on the Original image that is dragged to move and whose corners are dragged to
  resize (the aspect stays the band's, so nothing distorts); only the box moves during the drag, and the Spectrum
  previews (`?crop=x,y,w,h` on `/api/preview`) plus the saved value refresh on pointer release. A stored crop whose
  aspect no longer matches the band (after `## zx128 art_rows` changes) is re-fitted to the band aspect and re-saved when
  the art is shown, and the previews carry the current band height as `?lines=` so they track the unsaved control. The
  value is persisted while `PARAM_KEYS` overrides are still dropped by `_drop_art_overrides`.
- Every scene's `art:` must reference an existing `## <art-id>` under `# Art`; every scene must be reachable from the
  first. `save_project`/`_write_game_md` reject writes that fail validation and return the problems.
- **Scene order is the story order and scene 0 is the start.** The editor sidebar reorders scenes, arts and references
  by drag or the per-row up/down buttons; this rewrites the `## <id>` entry order under `# Scenes`/`# Art`/
  `# References` in `game.md`, and the first scene row carries a `start` badge. Reordering scenes renumbers generated
  scene ids and flag first-appearance ids but all references are by name, so behaviour is unchanged; art order only
  affects list/default-art order, and reference order only affects list order and the order references are rendered in.
- **The home bank is nearly full: the main image must fit below `0xDC03`** (the NIRVANA+ engine's `ORG`), or
  `adventure.bin` overlaps the engine and the game will not boot — the linker does not know about the reservation. Check
  `<game-folder>/build/adventure.bin` size (must be < `0xDC03 - 0x8000` = 23555 bytes). To keep room,
  `gen_scenes.py` emits exact-length `art_bank`/`art_off`/`scene_bank`/`scene_off`/`item_name_off` arrays (the engine
  only indexes them with ids it bounds against `N_ART`/`N_SCENES`/`N_ITEMS`), sizes `_scene_ws` per game
  (`SCENE_WS_SIZE`, the largest raw scene blob; there is no fixed per-scene cap, so the main-image check is what limits
  a long scene/popup) and, when the game uses an accented letter, ships only the accent
  slot offsets/glyphs and patches the CRT's own `CRT_FONT_64` table in place at startup (`NEED_ACCENT_FONT`); an
  ASCII game does nothing.
- **The paging routines must be linked below `0xC000`.** `paged_unpack`/`load_banks` page data banks in at `0xC000`, and
  the ZX0 decoder and `_scene_bank_list` execute from there, so if the fixed region overflows and the linker places any
  of them in bank 0 the game pages over its own running code and crashes before `main`. `tools/build.py` links
  `src/zx/loader.asm`, `vendor/zx0/zx0.asm` and `build/scene_banks.asm` **first** so they stay low, and verifies their map
  addresses are `< 0xC000` after the build (the `.bin`-size check cannot see this — these routines are in the fixed
  region, not bank 0). The `_scene_ws`/`_art_ws` workspaces may spill into bank 0, but must not reach the NIRVANA+
  engine at `0xDC03`; the main-image size check covers that because they are part of `adventure.bin`.
- **ZX Spectrum 48K (`## zx48`) is a non-paged, monochrome target with no NIRVANA+ engine.** The canonical 128K
  target id is `zx128` (the old `zx` spelling is an alias; a save rewrites `## zx` to `## zx128`). The 48K build stores
  compressed **scene** blobs in the flat resident block at `0x6000-0x7BFF` (`FLAT_DATA_SIZE` = 7168 B, loaded by
  `src/zx/loader48.asm`); the top 1 KB of lower RAM is the stack (`REGISTER_SP=0x7FFE`). Compressed **art** (1bpp) and
  the **inventory** blob are emitted as `const art_data`/`inv_data` arrays in `build/scene_data.c` and linked into the
  main image, which may use `0x8000-0xFFFF` (32,768 B) because there is no engine at `0xDC03`.
  `tools/gen_scenes.py` runs with `SCENE_FLAT=1`, writes `build/scene_flat.bin` (scenes only, padded), and converts art
  with `zxart.mono_band`; `off` dither becomes `bayer2` (see `zxart.mono_dither`). The band height is the independent
  `## zx48 art_rows` option (`ART_LINES`), not the 128K `# Game art_lines`. An explicit `crop:` authored for the
  primary ZX band is re-fitted to the 48K aspect with `zxart.crop_for_band`, so a different band height never
  stretches the picture. `plat_load` decodes scenes from
  `FLAT_DATA_ADDR+off+2` and inventory from `inv_data+off+2` with `port_unpack` (no paging); `plat_draw_art` decodes
  `art_data+art_off+2` into `_art_ws` and copies rows into the bitmap under `ZX48`, with no tile map/attribute race. The
  build fails with a `48K build does not fit: ...` message when either budget is exceeded. The 48K has no AY, so songs
  are ignored with a warning (the Systems card says so), and the target outputs only `<slug>-48k.tap`.
- **Selectable words** (`{{word}}` / `{{word|flag}}` in a `text:` line) are parsed only by `tools/scenefile.py`
  (`word_segments`/`parse_words`/`word_flag`); the generator emits a per-scene word table (`WordHdr`: line, col, len,
  flag) after the scene strings and sets `HAVE_WORDS`. The engine highlights each word, folds it into the option cursor
  above the menu (`word_nvis` + `mark_sel`) — the cursor does not wrap, so UP off the first word (or the first option in
  a word-less scene) stays put — and on ENTER `flag_set`s its flag then re-renders the scene in place. It is
  **one-shot** (a set word renders as plain text and leaves the cursor) and up to `WORD_MAX` (8) per scene. Word flags
  are ordinary flags; `assign_flags` notes them. `text_ink`/`highlight_ink` colour the body and every selection;
  selectable words always use `highlight_ink`, while inventory items use `text_ink` until selected; the cursor-selected
  word or item also gets a `>` marker. `text_ink`/`highlight_ink`/`text_bg` resolve via `scenefile.text_colours` to the
  engine's `TEXT_`/`HIGHLIGHT_`/`TEXT_BG` + bright macros; the legacy `word_sel_ink` writes into `highlight_ink`.
  `item_ink` is no longer used: a legacy line is parsed and dropped on save. The whole word feature compiles out for a
  game with no markers, so word-less games are unchanged.
- **A `prompt:` value keeps the line breaks the author types.** `_prompt_lines` writes the first line after `prompt:`
  and every later line with `_PROMPT_BREAK_INDENT` (4 spaces; an empty line is the bare indent), which `parse` reads
  back as `\n`; a 2-space-indented continuation is a soft wrap that rejoins with a space (a save uses those at
  `PROMPT_WRAP`=120 columns), so layout wrapping never changes the value sent to the image model.
- **Image quality settings are generation-only.** `# Game` may set `negative_prompt:` (sent as the SD API negative
  prompt), `hires: off|2x|3x|4x` with `hires_steps:`/`hires_denoise:` (a second txt2img pass; the saved PNG is
  `width*scale` x `height*scale`), and `refine_denoise:`. The Art/Reference panes' **Refine 2x** (`POST /api/refine_art`
  / `/api/refine_ref`, or `gen_images.py --refine`/`--refine-refs`) runs img2img on the selected image at 2x, preserving
  its composition. Both paths send the game's negative prompt and use the shared seed/steps/cfg. The current game uses a
  bright detailed pixel-art prompt and `hires: 2x`; keep dark gradients out of the prompt because the NIRVANA+ band
  only has two colours per 8x2 cell.
- **Reference images are separate `# References` entries, not art.** Each `## <ref-id>` has its own `prompt:` (and
  optional `image:`/`seed`/`steps`/`cfg`/`width`/`height`) and renders into `<game>/assets/refs/<id>/` exactly like art
  candidates. An `# Art` entry names them in `refs: <id>...`; the generator sends their selected images to the SD API as
  `extra_images` (stable-diffusion.cpp `ref_images`), which is what keeps a boat/van/character consistent across scenes.
  `scenefile.compose_prompt(..., refs)` also appends the Qwen pointer (`keep the same design as in the reference image`,
  or `... as in image 1, image 2` for several, in `refs:` order) so the text and the conditioning images agree.
  References are generation-only: `gen_scenes.py` ignores them and they are never packed into the game. Regenerating an
  art (single art or `gen_images.py`) re-renders its `refs:` first, then conditions the art on the fresh images. A full
  **Regenerate images** / **Generate missing** run (and `gen_images.py` with no art ids) re-renders every declared
  reference first, then the arts, so each reference is rendered once per run and the art conditions on the fresh images.
  The editor's Art sidebar has a **References** list (above the Art list; prompt, regenerate, upload, candidate picker)
  and each art has a toggle row; `scenefile.parse`/`serialize` own the format. `_validate` reports unknown refs or refs
  with no image. The candidate picker's confirmed × deletes a reference image; deleting the selected file repoints
  `image:` to the newest remaining candidate, or clears it when none remain (`server.delete_ref_image`). A renamed
  reference moves its folder and repoints every art (`_migrate_ref_files`).
- **Art source images are per-art folders with a chosen candidate.** Each `## <art-id>` under `# Art` owns
  `<game-folder>/assets/art/<id>/` holding one PNG per generation/upload, named `<action>-<epoch>.png`
  (`gen-`/`up-`); nothing is overwritten, and the per-art `image:` line (basename, validated by
  `scenefile.valid_art_image`) picks the one the build and previews use. Absent `image:` uses the newest PNG in the
  folder; a flat legacy `assets/gen/art_<id>.png` / `<id>.png` is still read as a fallback
  (`scenefile.resolve_art_image`, used by `gen_scenes.load_art_blob`, `server._art_image_path` and `art_preview_bytes`).
  `server._set_art_image` persists the pointer after a generate/upload (the SPA is forced clean before a job, so it
  cannot clobber edits); the Art tab's thumbnail picker (`drawArtPicker`/`selectArtImage`) sets `P.arts[i].image` and
  the ordinary save writes it; its confirmed × deletes a candidate, repointing `image:` to the newest remaining file or
  clearing it when none remain (`server.delete_art_image`). `gen_images.py` writes `gen-<epoch>.png` and updates game.md
  too. `assets/gen` still holds the songs' `song_<id>.wav` previews, so the two roots are distinct.
- **NIRVANA+ art conversion is dithered** (`zxart.nirvana_band`, used by both the build and the editor preview): after
  each 8x2 cell's ink/paper are chosen, pixels are assigned to them by a dither scheme, not a hard nearest test. The
  `dither:` setting is **per build system** (`## <id>` under `# Systems`, resolved by `scenefile.system_dither` and
  passed through `scenefile.conversion_options(..., target_id)`); it is no longer a `# Game` or per-art option. A
  legacy global `dither:` migrates to each selected system on parse; per-art dithers are dropped. It selects `off`
  (hard snap), the pointwise `bayer2`/`bayer4`/`bayer8`/`noise` (threshold schemes in
  `zxart.DITHER_MODES`) or an
  error-diffusion kernel listed in `zxart._DIFFUSE` — `floyd`, `atkinson`, `jarvis`, `stucki`, `sierra` (floyd keeps its
  original tap order, so existing art is unchanged). `bayer2` is the coarsest/roughest; `bayer8` the finest. Measured to
  keep the unique-tile count at or near the 64-tile cap, so the paged-bank budget is unaffected. Keep the numpy and
  pure-Python paths (`_nirvana_band_numpy`, `_nirvana_band_python`) byte-for-byte identical for every mode — the
  pointwise modes share `zxart._threshold_grid`, and error diffusion runs the shared `_DIFFUSE` tap order in the fixed
  raster order in both. **Monochrome targets force dithering**: `zxart.mono_dither()` maps `off` to
  `zxart.DEFAULT_MONO_DITHER` (`bayer2`) for the 1-bit Oric HIRES converter (`tools/oricart.py`), because a hard
  threshold would leave only black and white; CPC Mode 1 uses the same full dither list in `cpcart.py`, substituting
  its historical `bayer4` for `off` so a hard threshold never throws away the grey ramp.
- **Art margins are per build system.** `margin: <n>` in a `## <id>` block (`scenefile.system_margin`, surfaced through
  `scenefile.conversion_options`) adds `n` 8x8-cell borders on the left and right of the converted picture.
  `zxart.inset_band` scales the fitted band uniformly to the narrower inner width (preserving its aspect), centres it
  vertically and fills the side border (and any small vertical remainder) with the target's resolved `text_bg` (Oric
  always black; CPC Mode 1 uses its black pen). It is applied after `_fit`/`preprocess` and before palette reduction or quantisation, so `margin: 0` is
  byte-identical to the old output and a positive margin can only reduce the tile count. It is not a per-art override;
  the Art tab previews pass the live value as `?margin=` and crop the blank border off with
  `zxart.preview_margin_crop`, showing the scaled picture that sits inside the margins. Every art target registers the
  same option via `targets.base.art_margin_option()`.
- **More source-conversion options keep colour** (all baked at conversion time, so the engine carries no state):
  `match:` (`rgb` or the `perceptual` redmean distance, `zxart._dist_py`/`_dist_rgb`), `palette:` (`none`/`spectrum`/
  `adaptive`, `zxart._apply_palette`) and the `saturation`/`contrast`/`brightness`/`gamma` source adjustments
  (`zxart.preprocess`), applied after `_fit_band` and before quantisation. They resolve per art over the `# Game`
  default via `scenefile.conversion_options` (shared by `gen_scenes.load_art_blob`, the editor preview and the Art tab's
  live `?match=`/`?palette=` overrides in `server.art_preview_bytes`). `match`/`palette` use the same arithmetic in both.
- **`system_zx` (legacy, any Spectrum) / `system_zx128` / `system_zx48` / `system_sms` / `system_cpc` /
  `system_cpc464` / `system_msx1` / `system_msx2` / `system_msx` / `system_gb` / `system_c64` / `system_nes` /
  `system_oric` / `system_web` are reserved build-time pseudo-flags**
  (`scenefile.SYSTEM_FLAGS`): valid only in `if`/`unless`, folded per target by `gen_scenes.py`/`gen_port.py` (and by
  the web export, where only `system_web` is true), never assigned a flag id or runtime state. Using one as a
  declaration, `start:`, `ending:`, effect or selectable-word flag is an error.
- Flags are ids 0..127; inventory items are ids 128..191 and are also flags, so `if` tests either. Use `set`/`unset` for
  flags, `pick`/`leave` for items. Scene and item options may carry up to 8 `if`/`unless` tokens; every condition must
  hold (AND) and they may be mixed. A condition only tests a name: it must be declared (`flags:`/`items:`/`## <item-id>`
  under `# Items`) or assigned elsewhere (`set`/`unset`/`pick`/`leave`/`start:`/`ending:`/selectable word).
  `scenefile.assign_flags` does not create names from conditions, so a condition-only name is a build error and
  `server._validate` reports it as an error. Each option stores an absolute `cond_off` to a table of `(flag id,
  negated)` pairs (`OptHdr`/`ItemOptHdr` also carry `ncond`); `OptHdr.clear` bit0 is the `clear` reset. An option may
  end with `msg <text>` (`scenefile.split_option_msg`), stored as a `u16 msg_off` (0 = none) in both headers; choosing it
  shows the text in a modal text-pane popup (`show_message`, gated by `HAVE_MESSAGES`) before its effects and target run.
  The popup wraps at `PORT_TEXT_WIDTH` and scrolls with UP/DOWN (`^`/`v` at `PORT_SCROLL_COL`) when it exceeds the
  pane; any other key dismisses, as do UP at the top / DOWN at the bottom. `msg` consumes the rest of the line, so
  conditions/effects must precede it. The popup's dismiss line comes from
  `# Game popup_hint:` (`scenefile.popup_hint`, default "Press a key"), emitted as `port_game_popup_hint`.
  `# Game carry: <n>` caps held items; a full pack hides `pick` options, and the global **inventory** screen clears an
  item's flag, so the cap can never soft-lock. Both are parsed/serialized by `scenefile.py`, emitted by `gen_scenes.py`,
  validated by `server.py`.
- `## <item-id>` blocks under `# Items` (optional, `name:` display name <= 58 cols, `desc:` up to 4 logical lines
  that word-wrap at 62 on ZX, and up to 6 `opt:` lines) give inventory items a display name, description
  and options. The `id` is an ASCII token (its `pick`/`leave` name); the `name` defaults to the id and may be
  multi-word. Both are parsed/serialized by
  `scenefile.py` (`item_display_names`), emitted by `gen_scenes.py` into the home-bank `item_names[]` table, and
  validated by `server.py`. An id joins the item list like a `pick`/`leave` name (`scenefile.declared_items`). A `desc:`
  line may append postfix conditions (`text -> if <flag> unless <flag>`, up to 8, all must hold); an item option is
  `label -> <target> [if/unless.../inscene <scene>/set/unset/pick/leave/clear] [msg <text>]` — choosing it applies its effects then
  goes to `<target>` (`-` redraws the current scene, a scene id navigates there), and `inscene` gates it on the
  scene the item screen was opened from. Descriptions, options and
  the screen's own UI strings are one ZX0-compressed paged blob (`inv_blob_bank/off`) decoded on demand into `_art_ws`
  by `load_inv_blob()` — never resident, so the tight home bank is unaffected; the picture already drawn stays in the
  bitmap (its tiles in `_art_ws` are overwritten, so `drop_screen()` invalidates `cur_art` and the art is reloaded on
  return). Blob layout is `u16 ui_off[2]` (drop/back) then `u16 item_desc_off[N_ITEMS]` + `u8 item_nlines[N_ITEMS]` (+
  `u16 item_opt_off[N_ITEMS]` + `u8 item_nopt[N_ITEMS]` when any item has options) + strings + 14-byte `ItemOptHdr[]` +
  the item options' `(flag id, negated)` condition pairs; each stored description line is `[u8 ncond][(flag id,
  negated) * ncond]text\0` and each option header is `{label_off, cond_off, msg_off, scene, target, ncond, set, unset,
  pick, leave, clear}`. Scene text lines use the same `[u8 ncond][(flag id, negated) * ncond]text\0` prefix in `text_off[]`. The
  `inventory_drop:`/`inventory_back:` `# Game` settings are resolved by `scenefile.inventory_strings()` (blank =
  built-in default, which reflects `carry:`); the blob is bounded by `_art_ws` sizing / `_stage_ws`. The screen compiles
  when `HAVE_INV_BLOB` (`GAME_CARRY > 0`, any item desc or any item option); the description code is gated on
  `HAVE_ITEM_DESC`, the option code on `HAVE_ITEM_OPTS`.
- **A scene option may target `-` to re-enter its own scene.** `gen_scenes.py` resolves the sentinel to the scene's own
  index, so choosing it applies the option's effects and redraws the scene (no navigation). The editor's target picker
  offers `— same scene —`, the Story graph treats it as a self-transition (no edge), and Ctrl/Cmd+click in the Source
  tab jumps to the scene heading.
- **The inventory is the interactive band, not a key or a menu option.** `draw_inventory` renders the held items white
  on black on row 23 (the selected one green) into a single scroll window: `inv_vis[]` is every held item in display
  name order (`scenefile.assign_flags` sorts items by `item_names`), `inv_first`/`inv_win` are the visible slice (sized
  by `inv_fit`), with `<` in the first column when earlier items are hidden and `>` at the right edge when later ones
  are. `inv_cur` is the selected index into `inv_vis[]` (0xFF when the cursor is on the options). `choose_option` keeps
  a focus flag: DOWN off the last option enters the band (with no items held it stays put, since the cursor does not
  wrap); when a scene has no visible options but the player holds items, the band starts focused so the item screen is
  still reachable. Then DOWN/UP (`CURSOR_DOWN`/`CURSOR_UP` = 6/7, or S/W) step `inv_cur` with wraparound and LEFT/RIGHT
  (`CURSOR_LEFT`/`CURSOR_RIGHT` = 5/8, or A/D) are aliases; `inv_step` recolours only the two changed names (no
  full-line clear, so the band does not blink) and redraws row 23 only when the scroll window shifts so the `<`/`>`
  markers follow the selection. UP off the first item returns to the options; ENTER calls
  `drop_screen(inv_vis[inv_cur])`. `drop_screen(id)` draws its static text once, repaints only the old and new entry as
  the cursor moves, and shows the item's name/description plus a **Drop** entry (only with `GAME_CARRY > 0`) and a
  **Back** entry; there is no SPACE shortcut. Dropping
  `flag_set`s the item off, then the scene is redrawn. `opt_idx`/`opt_row`/`NOPT_MAX`/`SceneHdr.opts` stay 6 (items are
  not options).
- Music: `# Game songs:` declares song ids backed by `<game-folder>/assets/music/<id>.pt3`. `music: <id>|off|on` on `#
  Game` (default) and a scene's `music:` (override) is resolved by `scenefile.resolve_song()` into generated
  `scene_song[]` (index or 255). The shared player `src/portable/core/music.c` is linked by every target and
  dispatches to the VT2, PSGlib or APU player; `gen_scenes.song_setup()`/`scene_song_array()` are shared with
  `gen_port.py`, so the targets validate and resolve music identically. Songs are ZX0-compressed paged blobs on the AY, SMS and Next
  targets and share the art/scene bank budget; the Game Boy Color stream is raw in banked ROM. The workspace is
  platform-owned via `plat_song_ws()`: ZX uses lower RAM at `0x6000 + STAGE_WS_SIZE`
  (directly after `_stage_ws`, sized per game to the largest module after decompression, capped at 4158 B; the two
  buffers must fit the 8K window to 0x8000); CPC uses a fixed
  base-RAM workspace at 0x9600 (music builds keep art out of `BANK_2` and cap the CRT heap at 0x9600); MSX2 uses a
  `SONG_WS_SIZE` BSS buffer and packs songs into ROM banks after the art banks. `music_apply()` decompresses into that
  workspace (the VT2 player is stopped first) and starts playback; it is driven by `set_music()`/`music_on`, the **P**
  toggle handled in `plat_read_key()` (music is not a movement key; `plat_wait_release()` includes P).
  `plat_music_hook()` attaches/detaches the `NIRVANAP_ISR_HOOK` on ZX and is a no-op on CPC/MSX2, whose frame ISR
  is installed once in `plat_init()`. SMS converts each PT3 to an SN76489 PSG stream at build time (`tools/smsmusic.py`)
  and plays it with z88dk's PSGlib from a replaced IM1 vector (`src/sms/sms_music.asm`), paced to 50 Hz on NTSC (5 of 6
  vblanks) and every vblank on PAL; its `SONG_WS_SIZE` buffer holds the decompressed PSG stream. Game Boy Color
  converts each PT3 to an APU register stream (`tools/gbmusic.py`) and reads it directly from banked ROM with
  `src/gb/gb_music.c`; each stream starts at a bank boundary after the art, so no song workspace is used, and the
  vblank handler divides 59.7 Hz down to the stream's 50 Hz. Both converters share `tools/pt3frames.py` and use the
  pinned spectrumizer PT3 decoder, rejecting modules with unsupported commands. Playback on the AY targets uses
  z88dk's VT2/PT3 player (NIRVANA+ hook on
  ZX, firmware frame flyback on CPC, VDP IM1 on MSX2); the ZX song buffer now lives in lower RAM, so only the player
  code remains in home bank 0. The Music tab's
  **Convert MIDI → PT3** posts to
  `/api/convert_song`, which spawns the `spectrumizer` CLI (pinned in `tools/editor/Dockerfile`, not imported) on a
  temp `.mid` and validates the result with `_validate_song_module`; the source is kept as `assets/music/<id>.mid`.
  `_convert_opts()` allowlists the editor's options onto spectrumizer flags (style, bass, transpose, rows/beat, author,
  speed, loop position, `--no-dynamics`, and the mutually exclusive
  channel-C voices `--arps`+`--arp-speed` / `--echo`), omitting anything left at spectrumizer's
  default so a malformed request cannot smuggle arguments. Because spectrumizer has no trim option, long MIDIs can be
  cut to a `trim_start`/`trim_end` (seconds) window in the Music tab: the pure-stdlib `slice_midi()` rewrites the
  timeline (re-triggering notes held across the cut and re-emitting the tempo/time-sig at the cut point) in memory, and
  the stored `.mid` stays the full original. `POST /api/reconvert_song` re-runs the converter on that stored source
  (with a new cut/style) without re-uploading; `GET /api/songsource/<slug>/<id>` reports the source length. The inline
  player streams `/api/songpreview/<slug>/<id>`, which renders the module to `assets/gen/song_<id>.wav` (gitignored) via
  `spectrumizer.play`, caching by the `.pt3` mtime. `server.py` stays stdlib-only.
- **Art, scene and song blobs are ZX0-compressed** at build time (`gen_scenes.py` spawns the z88dk host tool
  `z88dk-zx0`; it must be on `$Z88DK/bin` or `PATH`). Each blob in a bank is `[u16 compressed length][zx0 stream]`. The
  69-byte standard decoder is vendored in `vendor/zx0/zx0.asm` (`_zx0_unpack`, BSD-3) and linked into the fixed region.
  `paged_unpack(bank, src, dst)` (its one paging primitive) `halt`s to sync to the frame interrupt, then copies the
  compressed bytes into the always-resident lower-RAM `_stage_ws` (0x6000) at most `STAGE_CHUNK` (1024) bytes per `di`,
  `ei`ing between chunks, and finally runs the decoder with interrupts enabled from `_stage_ws` into the workspace. The
  copy is chunked and frame-aligned because the NIRVANA+ ISR rewrites each bicolor attribute 4x per frame; a copy that
  held `di` across a frame boundary would miss a race frame and flash the band for one frame. The NIRVANA+ ISR preserves
  all registers and SP, so an interrupt mid-decode is safe. **`_art_ws` is a single per-game-sized buffer**
  (`ART_WS_SIZE` = the largest art or inventory blob, emitted by `gen_scenes.py` and reserved by
  `src/zx/paging.asm`): once drawn the picture lives in the screen bitmap/raced attributes, so the ZX
  `plat_draw_art()` decodes the next one straight over it and draws over the old picture, with deliberately **no
  `clear_art()`/black flash** between scenes. The only live reader is the ISR's 8 sprite slots via
  `NIRVANAP_TILE_IMAGES`, so `plat_load()` (inventory) and `plat_draw_art()` point that at `blank_tile` while a decode
  is in flight.
  Keep the `draw_art()` halt batch at 6 tiles (fits even at `art_rows=16`) — a wider batch overruns the frame on
  real hardware. `_stage_ws` (0x6000, lower RAM up to 0x8000) must hold the largest compressed blob; `gen_scenes.py`
  checks it (`STAGE_WS_MAX`). The `u16` prefix is what lets the runtime copy the exact compressed length, so **no
  `*_len` arrays exist** (`art_len`/`scene_len`/ `song_len` are gone). A compressed
  blob must fit `_stage_ws` (4096 B); `gen_scenes.py` asserts it. Compression roughly doubles art capacity (raw blobs
  shrink to 50-68%); the bank budget is unchanged, so packing is over compressed sizes.
- `clear` on an option wipes all state then re-grants `# Game start:` names. The engine does **not** auto-clear on
  entering the first scene.
- **`# Game password:`** (`scenefile.parse`/`serialize`, `gen_scenes.py` emits `game_title`/`game_password` into
  `build/scene_data.h`) makes the engine show a boot screen once before the first scene: `src/zx/plat_zx.c:password_screen()`
  fills the raced art band black (`fill_art_band_black`, same 6-tile `NIRVANAP_halt` batching as `draw_art`), prints the
  centered `title:`, and reads a line with `in_Inkey()`/`in_WaitForNoKey()` (one char per press, ENTER submits, DELETE
  backspaces). Correct entry runs scene 0; wrong entry prints an error and loops. Matching is case-insensitive and
  length must be equal. Password is ASCII, <= 16 chars, no spaces (enforced by `_validate`); `_validate` also warns when
  a password is set without a title. `password_label:` overrides the prompt line (`game_password_label`, emitted only
  when a password is set and guarded by `NEED_PASSWORD`; default "Enter the password:"). It is a `# Game` (Game tab)
  field, not per-scene.
- Banks are raw data loaded at runtime (TAP via `loader.asm`, SNA already resident); they are not linked in.
  `CRT_DISABLELOADER=1` prevents the CRT's own loader from running.
- Editor API is selected per game via `?game=<slug>`; request bodies may legitimately contain a `game` key (the `# Game`
  settings), so the server only reads the query string (`_game_arg`, `server.py`). Keep it that way.
- **Games open as folders, several at once.** `gamestore.open_folder(path)` appends a game folder anywhere on disk to
  the open set (`set_opened` replaces it, and `RVN_GAMES`/`RVN_GAME` envs seed it at import); `close_folder` removes
  one. `resolve`/`game_dir`/`list_games` refer to those folders, addressed by slug (a folder's basename) or by path;
  with nothing open they fall back to the legacy `games/<slug>/` workspace; the repo's demo game is not there, so
  open `demo-game/` explicitly (e.g. `RVN_GAME=demo-game` or the top-bar folder picker). The top-bar game label is a
  dropdown listing every open game (switch / close), and the desktop app remembers the whole set
  (`openGames`/`activeGame` in settings.json, passed as `RVN_GAMES`; the SPA's `rememberGames()` bridge). Two folders
  with the same basename cannot both be open — the basename is the slug (and names the build outputs).
  `POST /api/open {"path"}` adds (empty clears), `POST /api/close {"game"}` removes, and
  `POST /api/new {"parent","name","title"}` creates + adds; `duplicate`/`rename` are
  workspace-only. The engine/tools live at the app/repo root, so a game folder is just `game.md` + `assets/`. The build
  passes each game's `RVN_GAME` down so `build.py`, `gen_scenes.py`, `make_tap.py` and `make_sna.py` all resolve the
  same folder; `resolve` also accepts a directory path. Folder names are arbitrary (spaces/unicode are common on
  Windows/macOS): the server `unquote`s the request path and the game-scoped routes match `[^/\\]+` segments (no
  traversal — `/`/`\` are excluded and containment is re-checked).
- **Cross-platform build.** `build.py` normalises path separators to forward slashes for the z88dk tools (they accept
  them on Windows) and `gen_scenes._zx0_tool` finds `z88dk-zx0.exe` via `$Z88DK/bin` or `PATHEXT`. The desktop shell
  kills the server process tree with `taskkill /T` on Windows and picks `python`/`Scripts/python.exe`/`zcc.exe` there.
  For the desktop app the user supplies a z88dk built for the target OS/CPU (see the desktop notes).
- **Build systems live in a `# Systems` section.** Each `## <id>` block selects that system and holds its options
  (`zx`/`sms`/`cpc`/`cpc464`/`msx2`/`gb` `art_rows:`, MSX2/CPC `columns:`, CPC `mode:`); selected systems build in the
  system-list display order (128K, 48K, Next, CPC 6128, CPC 464, MSX2, C64, Oric, SMS, NES, GBC, Web), and each
  system's log
  is separated by a `==== name [id] ====` banner; the legacy
  `targets:` list and `<target>_<option>` keys are still read and rewrite into blocks on save. The editor's **Systems**
  tab edits the selection with one second-level sub-tab per platform; the Game tab keeps the shared settings
  (including Text colours).
- Editor writes are atomic and keep `game.md.bak`; art files are migrated when an art id is renamed
  (`_migrate_art_files`). Saves are conflict-checked: `/api/project` and `/api/raw` carry a `revision` (sha256 of
  game.md), and a stale one returns 409 so a concurrent edit by another user/process is not silently overwritten;
  the SPA offers to overwrite (`force`) or keep its buffer. Background writers (`_set_art_image`/jobs) refresh
  `P.revision` after they update game.md.
- `compose.yml` live-mounts an **absolute daemon-host path**, not `./`; update it if the checkout moves.
- UI is vanilla JS/CSS in `tools/editor/static/`; match the existing dark theme, inline-SVG mask icons per tab, and the
  `VIEWS` / `EDIT_MODES` split in `core.js`. Structured tabs share the `#view-edit` shell; `graph`/`emu` are their
  own flex views. The SPA is split **by topic, not bundled**: `index.html` loads `core.js`, `load.js`, `sidebar.js`,
  `flags.js`, `panes.js`, `pane-glue.js`, `art.js`, `refs.js`, `jobs.js`, `graph.js`, `actions.js`,
  `player.js`, `emulator.js`, `raw.js`, then `app.js` (the entry: event wiring + `load()`), all classic scripts
  sharing one global scope,
  so top-level `let`/`const`/`function` names must stay **unique across files** and each file needs its own `"use
  strict";`. CSS is likewise split (`base.css`…`responsive.css`, linked in that order; the cascade is the same as one
  file). Keep a new topic in a new file and add it to `index.html` in dependency order; the entry stays last.
- **Emulator tab:** a player-only preview. Opening it saves pending edits, exports the combined web player
  (`POST /api/web_export`) and mounts it in `#emu` (the top-bar **Export player** button re-exports and reloads it).
  There is no per-tab system picker, Play/Stop, download or fullscreen control. The exported player shell
  (`tools/webplayer_runtime/player.js`) supplies the right-hand system selector and embeds each selected system's
  offline vendored emulator: JSSpeccy inline for ZX; local iframe pages for SMS (`emulator/sms`, EmulatorJS smsplus),
  MSX2 (`emulator/msx`, WebMSX C-BIOS), CPC 6128/464 (`emulator/cpc`, CPCJS/Caprice32), Game Boy Color
  (`emulator/gb`, EmulatorJS Gambatte), Commodore 64 (`emulator/c64`, EmulatorJS VICE x64sc, direct keyboard input),
  NES (`emulator/nes`, EmulatorJS FCEUmm) and Oric Atmos (`emulator/oric`, Oricutron WASM). The SMS, GBC, C64 and
  NES pages share the pinned EmulatorJS data in `emulator/emulatorjs/data`; Oricutron has its own `emulator/oric/`
  bundle. Built artifacts are served by `/api/artifact/<slug>/<file>`; `tools/editor/static/emulator/THIRD_PARTY.md`
  records licenses. Keep emulator assets offline and pinned. CPC auto-runs via Caprice32 `-a "RUN"GAME"`, matching
  the CPC build's fixed 8.3 internal `GAME` name. On a coarse-pointer device the player draws `#speccy-touch` below
  `.screen` (`tools/webplayer_runtime/player.js`): a D-pad plus ENTER/SPACE/P that dispatches synthetic key
  events at the canvas parent, using bare `5`/`6`/`7`/`8` for the directions, and reserves its height when scaling
  the picture.
- **Web player:** the frontend is split into the story runtime (`tools/webgame_runtime/`, classic
  `index.html` + `game.js` + `app.js` + `style.css`, data assigned to `window.RVN_GAME`, never fetched) and the player
  shell (`tools/webplayer_runtime/`, data assigned to `window.RVN_PLAYER`). `tools/webgame.py` is the export/build
  step: it parses `game.md` through `scenefile.py`, writes both data files, copies source art, renders used PT3 songs to
  22050 Hz mono WAVs in `novel/assets/music/` with `spectrumizer.play` (cache in `assets/gen/`), copies only the
  selected systems' emulator bundles and artifacts, and writes `<game-folder>/web/`. `POST /api/web_export` writes that
  folder, `GET /play/<slug>/...` serves it statically, and `GET /api/webzip/<slug>` re-exports then streams an
  itch.io-ready zip with `index.html` at the root; the folder is gitignored. The player always lists the Web novel, then
  only `targets.selected_targets(doc)` that have a browser emulator (Next and missing artifacts are skipped with
  warnings). The player has no download button. The editor's Emulator tab saves pending edits, exports and previews
  the folder when it opens; the top-bar **Export player** button re-exports and reloads the preview.
  There is no separate Web tab. The runtime persists progress (current scene + flags) in `localStorage` under
  `rvn.web.<slug>.state` and sound state under `rvn.web.<slug>.sound`; **Restart** clears the story state. It must never
  grow request-time story generation or rendering. **Web is a `# Systems` target** (`tools/targets/web.py`): ticking it
  in the Systems tab makes the Build button run `tools/webgame.py` after the native builds (`## web` selects it,
  `system_web` is its pseudo-flag); the Emulator tab previews the export regardless. The art band aspect
  follows the first selected *native* target's `art_rows` (ZX first, default 10). Keep the novel **mobile-first** (fluid
  single column, 44px taps, safe areas, bottom item sheet), mirror the shared engine's condition/clear/pick/word/carry
  semantics, and update `docs/web-runtime.md` with any data/route/export change.
- **ZX Next runtime:** `tools/targets/next.py` builds a native `+zxn` `.nex` with `tools/gen_port.py --next`.
  The shared portable core draws text/title/inventory on the ULA and the picture on a Layer 2 256-colour band clipped
  to rows 1..`## next art_rows` (even 8..16, default 10). `tools/nextart.py` converts art (median-cut 256 colours or a
  fixed 16-colour palette) to pixels plus a 256-entry RGB333 palette. Each art occupies three 16K banks (the band starts
  at Layer 2 row 8); palettes live in banks 8..15 and scene/inventory/song blobs are ZX0-compressed in banks after the
  art. `src/next/paging_next.asm` maps a source bank over `0xC000`, copies the length-prefixed stream to `_stage_ws`
  at `0x6000`, restores bank 0, then decodes into `scene_ws`/`inv_ws` in `BANK_0_H` at `0xE000` (the lower half of bank
  0 is used by the CRT and AY player). `src/next/next_isr.asm` installs an IM1 handler that calls `ay_vt2_play`
  through a switchable hook. The target uses `REGISTER_SP=0xc000`, a `__CODE_END_tail < 0xC000` guard, and requires
  `_stage_ws` + the song workspace to fit the 8K window at `0x6000`. ZEsarUX is **not bundled**: `tools/build.py run
  <game> next` and `tools/spectrum.py run <game>.nex` use an installed ZEsarUX (`$ZESARUX`/`$RVN_ZESARUX`, the
  checkout symlink, or `PATH`) with the TBBlue machine. The editor Emulator tab does not list Next; the `.nex` is still
  served by `/api/artifact/...`. `system_next` is a build-time pseudo-flag, and `## next` supports `art_rows`, `menu`,
  and `title_ink`.
- **CPC runtime:** `tools/gen_port.py --cpc` converts each art band to CPC screen bytes (`[u8 ninks][u8 hardware inks][8
  scanline chunks]`) and packs the ZX0-compressed blobs into `BANK_4..BANK_7`, with `BANK_2` (0x8000, capped at 8K so it
  cannot reach the stack) holding overflow. A music build packs art+song blobs into the four extra banks only (no
  `BANK_2`), because the base-RAM page holds the fixed workspaces. The scene and inventory workspaces share one buffer
  at `CPC_WS_BASE` (`build/port_ws.asm`, sized to the larger; the item screen reloads the scene on return, so
  `PORT_INV_OVERWRITES_ART` forces that redraw) and the AY VT2 song workspace follows it, all packed below the
  firmware event blocks at 0xA600. The target caps `CRT_MAX_HEAP_ADDRESS` at `CPC_WS_BASE` and guards
  `__BSS_END_tail < CPC_WS_BASE` plus the music code below 0x8000. Songs load through `cpc_unpack_banked()` (`off+2`,
  skipping the packed length prefix) into `SONG_WS_ADDR` and play from the firmware frame-flyback ISR. `plat_cpc.c`
  renders text directly into screen memory (8x8 doubled glyphs, or 4x8 for 62 columns) and `cpc_paging.asm` pages a
  bank through port 0x7F with interrupts off, decodes to 0xC000, restores the base mapping, then scatters the band to
  rows 1..`cpc_art_rows`. The paging routine and ZX0 decoder must stay below 0x4000; they are assembled into `code_l`
  (the paging/ink asm directly, the vendored decoder via `-Ca-DZX0_LOW`), which links before the compiler code, so the
  game's C size cannot push them into the paged window.
  CPC also builds with `PORT_KEEP_ART=1`: the portable `show_scene` caches the art id and only decodes when it changes,
  so same-art scene changes, word clicks and item screens clear just the title/text pane
  (`plat_clear_text`/`plat_clear_pane`, one memset per scanline block) instead of the whole screen. Because the decoder
  writes into visible video RAM, `plat_draw_art` first sets every pen black, scatters the band, clears the title/text
  pane, and only then restores the picture palette; the transient blob bytes are never visible. Mode 1 is
  monochrome: its four pens are a dithered black/grey/white luminance ramp shared by the picture and text, and
  `text_bg:`/`highlight_ink:`/`text_ink:` do not apply. In Modes 0/2 palette entry 0 is the game's `text_bg:` and the
  top two the `highlight_ink:`/`text_ink:` (`cpcart.text_colours`), forced in before quantising so cleared rows and
  text keep the author's colours while the picture still uses every ink (Mode 0: 13 image + background + 2 text); the
  editor's CPC target preview receives the same game colours. Changing them rebakes every Mode 0/2 art blob, so
  rebuild.
  `tools/targets/cpc.py`
  checks the link map, and checks `__BSS_END_tail < 0x8000` only when `port_art.asm` actually emits `SECTION BANK_2` (a
  stale `port_art_bank2.bin` from an earlier build must not trip the guard). Any mode builds with
  `PORT_OVERLAY_MENU=1` when the system sets `menu: popup`: the text uses every row below the art, the `SPACE` key
  opens/closes an options/items dialog over that pane, and the old pinned-option/inventory paths compile out. By
  default every mode keeps the pinned options. `cpc_mode`, `cpc_columns` and `cpc_art_rows` are emitted into
  `port_data.h`.
- **CPC 464 runtime:** `tools/targets/cpc464.py` builds the same 6128-style disk but with the CRT loader disabled
  (`CRT_DISABLELOADER=1`), because the 464 has 64K and no paging. `gen_port.py --cpc464` still packs the compressed
  art/song blobs into the `BANK_4..BANK_7` (and optional `BANK_2`) files, but `appmake` writes them to the `.dsk`
  instead of the runtime paging them in. `PORT_ART_FROM_DISK=1` makes `plat_cpc.c` decode art through
  `cpc_disk.asm`: art uses `CAS_IN_DIRECT` to read the bank into the blank screen, copies the `[u16 length][ZX0]`
  blob at `art_off` into `cpc_art_buf[CPC_ART_LOAD_SIZE]`, then decodes it over the screen. Songs use
  `CAS_IN_CHAR` (with the song workspace as the 2K stream buffer) so a music toggle never disturbs the picture, and
  the song workspace is reserved at least 2048 bytes. The resident image (including the load buffer) must end below
  `CPC_WS_BASE`; the target checks `__BSS_END_tail`. Output is
  `<slug>-cpc464.dsk` (`artifact_suffix="-cpc464"`), and the Emulator tab lists the 464 model only when that target is
  selected (like every other system).
- **MSX1 runtime:** `tools/targets/msx1.py` builds a `zcc +msx -subtype=rom` ASCII16 ROM (`<slug>-msx1.rom`)
  with `tools/gen_port.py --msx1`. `tools/msx1art.py` fits the band to 256 x `8*art_rows` pixels and converts each
  8x1 row to two TMS9918A colours; art blobs are `[u8 ntiles][cell[32*art_rows][1 pnt + 8 colour bytes]][patterns]`
  in banks 2+, with scene/inventory data in bank 1 and a bit-reversed Pixel Operator font bank after the art. The
  platform layer (`src/msx1/plat_msx1.c`, `msx1_vram.asm`) uses Graphics II (32x24 tiles), copies the font into all
  three pattern banks, and writes art name/colour entries and 8x8 patterns into banks 0/1. `mono: on` builds a
  dithered white-on-black picture and forces white text; `dither:` selects the mono scheme; `menu: popup` selects the
  overlay dialog. The target has no music yet. ZEsarUX is not bundled; use WebMSX (`MACHINE=MSX1`) or openMSX.
- **MSX2 runtime:** `tools/gen_port.py --msx2` converts each band with `tools/msx2art.py` and stores the
  scenes/inventory blob in ASCII16 ROM bank 1; each art gets one 16K bank from 2 up and `port_art.asm` maps them with
  `SECTION BANK_NN`. `plat_msx2.c` uses V9938 Screen 7 (512x212, 4bpp): the full-width 512-pixel art band starts at x=0,
  title row 0, art rows 1..`msx2_art_rows`, text rows `1+msx2_art_rows`..22 and the inventory on row 23. Screen 7 pixels
  are half-width, so `msx2art._fit` fits the source to the `256 x 8*msx2_art_rows` physical aspect before scaling it
  into the 512-pixel grid. An explicit `crop:` keeps its full width and re-centres its vertical window to that aspect
  (clamped to the source), so it is neither stretched nor cropped sideways; the editor preview doubles the height to
  match. `columns` is 64 (default) or 80. 64 columns use 8x8 glyphs at 8 pixels per cell, filling the full 512-pixel
  width; 80 columns use 6-pixel cells (4-pixel glyphs plus a 2-pixel gap) starting at x=16. The 64-column 8x8 glyphs
  are the shared CC0 Pixel Operator Mono 8 (`vendor/pixeloperator8/`); the 80-column cells use the 4x8 CRT font.
  `gen_port.py` writes the raw 768-byte font to its own ASCII16 bank after the song banks (`build/port_font.asm`,
  `MSX2_FONT_BANK`); `plat_msx2.c` selects that bank and expands the font into the Screen 7 cell table in RAM at
  startup, then selects `PORT_DATA_BANK`. Palette entry 0 is the game's
  `text_bg:` and entries 14/15 its `highlight_ink:`/`text_ink:` (snapped to RGB333), so cleared rows and selection use
  the chosen colours; `msx2art.text_colours` bakes them into every art palette and the editor preview, so changing them
  rebakes the art. The MSX2 text pane is fixed (`PORT_NO_TEXT_SCROLL`), so scene text and options must fit the rows
  below the art band. An art blob is
  `[u8 palette[16*2]][u16 comp_len][ZX0 strip] * art_rows`, where each strip is
  2048 bytes (8 full-width lines); the runtime decodes a strip into a 2K RAM buffer and writes it to VRAM, so a 24K
  full-width bitmap fits one 16K bank. Palette bytes are `red:3 << 4 | blue:3` then `green:3`. The target builds with
  `+msx -subtype=rom2`, passes `-pragma-define:MAPPER_ASCII16`, uses `plat_set_bank()` for the 0x8000 window, and guards
  the link map so resident code stays below 0x8000. That limit is not optional: when the fixed binary is over 16 KB,
  z88dk-appmake starts at bank 2 and silently drops `_BANK_01.bin` (the scene/inventory data), producing a ROM that
  boots without its story. The guard reads the z88dk map, whose labels are uppercase. Songs are packed into ROM banks
  after the art banks
  (`build/port_song.asm`); `plat_load(PLAT_LOAD_SONG)` maps the song bank, decodes `0x8000+off+2` into the BSS
  workspace, restores bank 1, and the VDP IM1 ISR drives the VT2 player at 50 Hz (five of six frames on a 60 Hz NTSC
  VDP, detected from the `NT` bit of the BIOS `REG9SAV` shadow at `0xFFE8`, every frame on 50 Hz PAL). Screen 7 and
  the V9938 palette are set through the BIOS/CHGMOD path; `plat_msx2.c` writes VRAM with R#14 page handling.
- **Game Boy Color runtime:** `tools/gen_port.py --gb` stores scene/inventory blobs raw (no SM83 ZX0 decoder) in MBC1
  banks: `port_data.c` metadata stays in bank 0, scenes/inventory start at bank 1 and art follows. `plat_gb.c` draws a
  20x18 screen (title row 0, art rows 1..`gb_art_rows`, text from `1+art_rows` through row 17). The CGB background has
  eight four-colour palettes selected per tile by an attribute byte in VRAM bank 1: palettes 6/7 are the body and
  highlight text palettes (`gb_text_palette` in `port_data.c`) and the picture uses 0..5. It builds with
  `PORT_OVERLAY_MENU=1`, so B/Start selects highlighted words and dialog entries while A opens/closes the
  options/items dialog; `plat_clear_pane` clears only the rows below the art. `gb_copy.asm` copies a banked blob from
  0x4000 and `gb_vram.asm` waits for a safe LCD mode before each VRAM write. Text uses the shared CC0 Pixel Operator
  Mono 8 (`vendor/pixeloperator8/`), expanded to 2bpp tiles by `gbart.font_tiles`. The target uses SDCC
  (`-compiler=sdcc`) and guards the link map: fixed-bank code must stay below 0x4000 and BSS below the stack at 0xE000.
  The cartridge is CGB-enhanced (`0x143 = 0x80`, with the header and global checksums recomputed after appmake), so
  the same `.gbc` also boots on a DMG; there the palette/attribute writes are skipped and `BGP=0xE4` shows four
  shades. Art conversion is `tools/gbart.py`: 160 x `8*art_rows` 2bpp tiles, at most 158 art tiles, map entries offset
  by 96, and an art blob of `[u8 ntiles][u8 npalettes][u16 palettes[npalettes][4]][tiles][map][attrs]`. Each tile is
  quantised to four colours and the tile palettes are clustered into at most six shared palettes, ordered light-to-
  dark for the DMG fallback; `art_rows` is 8. Selection uses the configured highlight palette on CGB
  and keeps the `>` marker so it also works on a monochrome Game Boy.
- **Commodore 64 runtime:** `tools/targets/c64.py` builds a `cl65 -t c64` `.prg` (cc65, not z88dk).
  `tools/gen_port.py --c64` emits `build/port_data.c/h`, the bit-reversed `build/port_font8.h` and the compressed
  scene/inventory/art arrays; `src/6502/zx0.c` decodes them and `src/c64/plat_c64.c` renders through the VIC-II. The
  display is 40x25 in multicolor character mode: row 0 title, rows 1..`c64_art_rows` the picture, the text pane below,
  and the `SPACE` action dialog (`PORT_OVERLAY_MENU=1`). The charset at `$A000` holds 96 hi-res text glyphs (indices
  0..95) and up to 160 multicolor 4x8 art tiles (96..255); `$D021` is `text_bg:`, `$D022`/`$D023` are chosen per art and
  each cell adds a colour-RAM colour from 0..7. Text ink/highlight are limited to the first eight C64 colours. Screen
  RAM is `$A800`, colour RAM `$D800`, VIC bank 2 is selected through CIA2, and `src/c64/c64.cfg` reserves `$A000-$ABFF`
  with BSS at `$AC00-$C7FF` and the stack at `$C800-$CFFF`. The loaded `.prg` must end below `$A000`; the target checks
  its size. Art is `tools/c64art.py`: a 160 x `8*art_rows` logical band (previewed at 320 physical pixels),
  4-colour cells with at most 160 deduplicated tiles, and a `[u8 ntiles][u8 c22][u8 c23][tiles][map][colors]` blob.
  `art_rows` is 8/10/12 (default 8). `c64_any_key_down` in `src/c64/c64_hw.s` is the release scan; `kbhit`/`cgetc`
  read keys. There is no boot password and no music yet (`N_SONGS=0` for this target).
- **NES runtime:** `tools/targets/nes.py` links with `cl65 -t nes`, patches the iNES/NES2.0 header to mapper 1 (MMC1),
  installs the custom NMI vector and appends the generated CHR banks. `tools/gen_port.py --nes` emits the compressed
  scene/inventory arrays plus the uncompressed art maps/attributes/palettes in `port_data.c/h` and
  `build/port_nes_chr.bin`. The cartridge is 32KB PRG with 8KB battery WRAM at `$6000`; BSS and the C stack live there.
  The PPU screen is 32x30: row 0 blank, row 1 title, rows 2..`nes_art_rows+1` the picture, and text from
  `nes_art_rows+2` through 29 (`PORT_OVERLAY_MENU=1`; A confirms, B/Select opens/closes the dialog). Each 8KB CHR bank
  has two 4KB pattern tables: table 0 (title/art) holds the normal 96-glyph font (0..95) plus up to 160 art tiles
  (96..255); table 1 (text) holds the normal font plus a highlight copy at 96..191. Text attributes always select
  palette 0 (entry 1 = text ink, entry 2 = highlight ink), and `plat_text_at` draws `PLAT_COLOR_SEL` glyphs with the
  highlight tiles, so a selected word/entry cannot tint the adjacent row. Palettes 1/2/3 are the art palettes (three
  colours plus the shared background each, up to ten colours). A custom NMI (`src/nes/nes_ppu.s`, vector
  patched from the link map) flushes the ppubuf, keeps table 0 through the art band and switches to table 1 in the last
  art scanline's HBlank after a generated delay (`port_nes_split_xy`, adjusted by the queued-byte count). A locked
  cursor update defers the ppubuf flush to the next frame so both selection rows change atomically. Each art gets one
  8KB CHR bank after bank 0 (font + highlight + blanks); MMC1 8KB CHR mode addresses 16 banks, so a game may have at
  most 15 arts. `nesart` emits the full 64-byte attribute table per art. `src/nes/nes_mmc1.s` writes the MMC1 registers
  serially; note the 8KB CHR bank register ignores bit 0 (`bank << 1`). Large redraws (art, pane clears) write VRAM
  directly with the NMI/rendering off; text and attribute updates go through the cc65 ppubuf ring buffer and its NMI
  flush, which also resets the scroll. That wrapper targets the cc65 2.18/2.19 ppubuf API (the version in the editor
  Docker image). `art_rows` is 8/10/12 (default 10); the 32KB PRG is the main size limit. There is no boot password and
  no music yet.
- **Oric Atmos runtime:** `tools/targets/oric.py` builds a cc65 `atmos` `.tap` (the Oric is the third 6502 target).
  The HIRES bitmap is 240x200 at `$A000`; text is software-rendered with a generated 6x8 font, the title is row 0,
  the art band rows 1..`art_rows`, and the text pane is below. `art_rows` is 8/10/12 (default 8), `PLAT_ROWS=25`,
  `PORT_COLS=40`, `PORT_KEEP_ART=1` and `N_SONGS=0`; `PORT_OVERLAY_MENU` follows `## oric menu:` (default inline:
  pinned options plus the row-24 inventory; `popup` uses the action dialog). The build is non-banked: scene,
  inventory and art blobs are resident ZX0-compressed data decoded by `src/6502/zx0.c`. Art is decoded directly
  into the bitmap band; `tools/oricart.py` emits `[u8 ink][u8 paper][ZX0 pixels]` so no art workspace is needed.
  `src/oric/plat_oric.c` switches to HIRES via the `$BB80` mode attribute (the boot wait must cover the ULA's
  latched line), clears the screen, blanks the three text rows at `$BF68` with ink attributes, and reads the Oric
  ROM keyboard buffer (`cgetc`/`kbhit`). Output is `<slug>-oric.tap`; the tape is marked `__AUTORUN__=$C7`. There is no
  music or boot-password screen. The editor's Emulator tab uses the vendored Oricutron WASM build
  (`tools/editor/static/emulator/oric/`), which loads the tape through `ENV.FILE` and types `CLOAD""`.
- **SMS runtime:** `tools/gen_port.py --sms` converts each art band to planar 4bpp tiles and writes one uncompressed
  blob per `BANK_02`.. ROM bank plus `port_banks.asm` (both gitignored). Songs are converted to a compressed
  SN76489 PSG stream and packed into the remaining data banks (`port_song.asm`); `plat_load(PLAT_LOAD_SONG)` maps the
  bank, ZX0-decodes into the `SONG_WS_SIZE` BSS buffer, and restores the mapper. `src/sms/sms_music.asm` installs the
  0x38 IM1 handler only for music builds (`CRT_ENABLE_RST=128`), enabling VDP frame interrupts in `plat_init()`. The 96 converted font tiles occupy VRAM
  patterns 0..95; they are the shared CC0 Pixel Operator Mono 8, emitted as `port_font8.h` by `gen_port.py`, and art
  starts at 96 and is capped at 352 unique tiles (extra cells reuse the nearest tile). The display is 24 rows: title
  row 0, art rows 1..`# Systems` `## sms art_rows:`, and the text on every row below through 23.
  `PORT_OVERLAY_MENU=1` makes button 1 open/close the options/items dialog and button 2 confirm; `plat_clear_pane`
  clears only the rows below the art. Background palette entry 0 is the game's `text_bg:` and entry 1 its `text_ink:`;
  sprite-palette entry 0 is the same background and entry 1 its `highlight_ink:` (all snapped to CRAM);
  `smsart.text_colours` bakes them into every art palette and the editor preview, so changing them rebakes the art.
  The text layer uses z88dk's newlib `arch/sms.h` helpers, not SMSlib.
- **Portable under-art dialog:** `PORT_OVERLAY_MENU` makes `show_scene` give the text every row from `PORT_TEXT_TOP`
  to `PLAT_ROWS-1` and skip the pinned options and inventory band. It is mandatory on SMS, Game Boy Color, Commodore
  64 and NES;
  ZX, MSX2, Oric, the CPC (any mode) and Next opt in with the system's `menu: popup` target option (ZX/CPC/Oric
  `SPACE`, MSX2 `SPACE` or joystick button 2). The ZX `port_data.h` emits the define, and the ZX `plat_clear_text`
  also clears row 23 when it is set. `A`/button 1 (CPC: `SPACE`) opens and closes `menu_screen()`, a modal list drawn over that pane:
  visible scene options first, then held items prefixed `*`, labels wrapped, `>` marker on the selection and `^`/`v`
  when the list scrolls. Moving the cursor repaints only the old and new entry, falling back to a full pane redraw
  when the scroll window shifts. `B`/Enter/button 2 (CPC: Enter/Space/fire) activates an entry (or sets a highlighted
  word when the dialog is closed); selecting an item opens `drop_screen`, where A also closes. On these targets a long
  scene body scrolls with UP/DOWN (LEFT/RIGHT moves between highlighted words, or scrolls when the scene has none), and
  `drop_screen` scrolls an overlong item description with UP/DOWN while the cursor is on the first entry.
  `collect_options`/`collect_items` rebuild the list on each open, so item effects and flag changes are reflected; the
  old pinned-option/inventory code is compiled out on these targets. `PORT_SIMPLE_OPTIONS` affects the CPC pinned
  layout in every mode. On ZX the inventory blob shares `_art_ws`, so returning from `drop_screen` with
  `cur_art == 0xFF` returns to `main` for a full `show_scene` redraw; `menu_entry_rows` is one row per entry under
  `PORT_NO_WRAP` (no `count_rows`).
- The Source tab is a **vendored Monaco 0.52.2** (offline; `static/monaco/`, classic AMD `min/vs`), served through
  `/monaco/<file>` like JSSpeccy's `/emulator/`. Only `editor.main.js/.css`, `loader.js`, the markdown language and the
  worker/font are committed; `raw.js` loads it lazily on first opening the tab, so no other tab pays for it. Keep the
  editor wired to `saveRaw`/`loadRaw`/`rawDirty`, not a textarea.
- Source-tab validation: `_validate` issues carry a 1-based `line` (added by `_annotate_lines`, which maps a scene/art
  issue to its `art:`/`prompt:` field, an option/text issue to its own line via the internal `need` locator, and a
  flag/item/song issue to its declaration). `PUT /api/raw` returns those issues in the 400 body; `POST /api/validate`
  lints without writing. The client draws them as Monaco markers plus `raw-err-line` decorations. Keep the two paths
  (parse-time and `/api/validate`) going through the same `_validate`/`_annotate_lines`.
- Ctrl/Cmd+click a reference in the Source tab to jump to its definition: `POST /api/validate` also returns
  `{"outline"}`, `scenefile.outline_links(text)` — 1-based source/destination ranges for scene option targets (`-> id`),
  `art:`/`music:`/`ending:` values, `pick`/`leave`/`set`/`unset`/`if`/`unless`/text-conditional/`{{word|flag}}` tokens,
  and `flags:`/`items:`/`songs:`/`start:` list entries. `raw.js` registers one Monaco
  `registerDefinitionProvider("markdown")` that hit-tests the cached `rawOutline` (refreshed by the same debounce as the
  lint, and on tab load) and returns the definition `Range`. Definitions prefer the `## <id>`/legacy `# scene`/`#
  art`/`# song`/`# item` heading, then the `flags:`/`items:`/`songs:`/`start:` entry, else the first use; a name is an
  item vs flag via `declared_items`/`assign_flags`, so a scene and a flag may share a name without mislinking.

## Conventions

- Python: stdlib-only in `tools/editor/` (minimal image; Pillow only in `zxart.py`/build tooling), 4-space indent, 120
  col soft limit, module docstrings that list endpoints/behavior. No added comments unless they explain non-obvious
  intent. All Markdown docs (`README.md`, `AGENTS.md`, `docs/**/*.md`) wrap at 120 columns.
- JS: `"use strict"`, 2-space indent, 120 col soft limit, `const`/`let`, arrow callbacks; keep the `$("id")` helper
  and `api(method, path, body)` fetch wrapper.
- Do not commit build outputs, models, or `.bak` files (see `.gitignore`).
- Only commit when the user explicitly asks.
