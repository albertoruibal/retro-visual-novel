# Retro Visual Novel

**Retro Visual Novel** is an 8-bit visual novel creator for the ZX Spectrum 128K
and other 8-bit targets, with a shared engine and authoring editor.

[**Play the demo game in your browser**](https://albertoruibal.github.io/retro-visual-novel/)

## Supported targets

- [ZX Spectrum 128K](docs/systems/zx128.md): With Nirvana+ art scenes
- [ZX Spectrum 48K](docs/systems/zx48.md): No sound
- [ZX Spectrum Next](docs/systems/next.md)
- [Amstrad CPC 6128](docs/systems/cpc.md): Beta
- [Amstrad CPC 464](docs/systems/cpc464.md): beta
- [MSX1](docs/systems/msx1.md)
- [MSX2](docs/systems/msx2.md)
- [Commodore 64](docs/systems/c64.md): Alpha, no sound
- [Oric Atmos](docs/systems/oric.md): Alpha, no sound
- [Sega Master System](docs/systems/sms.md): Beta
- [Nintendo Entertainment System](docs/systems/nes.md): Beta
- [Nintendo Game Boy Color](docs/systems/gb.md): Beta
- [HTML5](docs/web-player.md): Browser story runtime, played in the Web Player

See [playing the games](docs/playing.md) for the controls on each target.

## Games

The game is defined in a folder with a `game.md` in its root. A folder may instead hold one or more
`game-<variant>.md` files (for example a language or a story part); variants share the `assets/` tree, including the
art and reference folders. See the demo's [English](demo-game/game-en.md) and [Spanish](demo-game/game-es.md) files.

It is defined in markdown, it can be manually edit or with the UI.

See [authoring games](docs/authoring.md) for information about the Markdown format.

### Variants

A folder can hold several story variants side by side: `game.md` (optional, the primary variant) plus
`game-<variant>.md` files such as `game-en.md` and `game-es.md`. They share the same `assets/art/`, `assets/refs/` and
`assets/music/` folders. The editor adds a variant picker when more than one file exists, native builds are suffixed
(`<slug>-es.tap`), and the exported Web Player gets a variant selector at the top.

## Editor desktop app

It is an electron app that allows to edit and build games. The engine and tools ship with the app.

It has tabs to edit the game sections:

* Game: Global game settings.
* Systems: Chooses the systems to build the game for and their specific options; each platform has its own sub-tab.
* Art: Allows to generate and upload images and previews them for every selected system.
* Music: Imports PT3, converts from MIDI with spectrumizer, and plays on the AY targets (ZX Spectrum, CPC 6128/464 and
  MSX2); the Master System build converts PT3 to SN76489 PSG data, and the Game Boy Color and NES builds convert it to
  their APU register formats, so songs play there too. The MSX1, Commodore 64 and Oric Atmos builds currently ignore
  songs.
* Scenes: Defines the text and logic for each scene.
* Flags: Flags are game-wide and can be enabled/disabled, some scene lines and options ara available when a certain flag is set.
* Items: Carried by the player, each item can be selected, and it has options that can be enabled only for certain scenes. 
* Graph: Draws a graph of the scene relationship.
* Source: Allows to directly edit the Markdown of the game with syntax validation and navigation via CTRL + click.
* Build: Builds the game for the selected systems. Every build also refreshes the Web Player
  (`<game-folder>/web/`) with the selected systems' emulators through a separate **Web Player** step; ticking
  **HTML5** builds the **HTML5 game** instead, adding the mobile-first story. The Build log separates each system with
  a `==== name [id] ====` banner.
* Emulator: Auto-exports and starts the combined Web Player: the mobile-first story (when **HTML5** is ticked) plus
  a browser emulator for every selected system that has one (JSSpeccy for ZX, CPCJS/Caprice32 for the CPC 6128 and
  CPC 464, WebMSX C-BIOS for MSX1/MSX2, EmulatorJS/VICE x64sc for Commodore 64, Oricutron for Oric Atmos,
  EmulatorJS/smsplus for SMS, EmulatorJS/FCEUmm for NES and EmulatorJS/Gambatte for Game Boy Color). Use the top-bar
  **Export player** button to re-export and reload the preview. ZX Next is not bundled in the browser; use
  `python3 tools/build.py run <game> next` with ZEsarUX.

The engine and tools ship with the app.

To make the build work, the editor needs a complete z88dk toolchain (a folder containing `bin/zcc` and
the `z88dk-zx0` host compressor) configured in the top-bar **Settings**.
On Linux a z88dk Snap install (`snap install z88dk --beta`, the tree at`/snap/z88dk/current`) is detected automatically.
For Windows and Mac, download a nightly build from `http://nightly.z88dk.org`.
The Commodore 64, NES and Oric Atmos targets use **cc65** instead (z88dk has no target for them); install cc65 for
your host (`bin/cl65`, `bin/ca65`, `bin/ld65`, `bin/cc65`) and point the same **Build toolchain** card at it.
The editor Docker image already contains cc65.

The editor generates images with [local models](docs/models.md).

## Development

For local development:

```bash
docker compose up -d --build     # editor http://localhost:8765
docker compose logs -f
docker compose down
```

Building the desktop app (Electron):

```bash
cd electron
npm install
npm run venv
npm run dist
```

Desktop releases are built by `.github/workflows/release.yml`. Pushing a `v*` tag (or running the workflow manually
with the tag) builds the Linux AppImage/deb, Windows installer and macOS DMGs, then attaches them to the GitHub
Release. The tag must match the `version` in `electron/package.json`.

## Game building toolchain

It uses python tools and z88dk (https://z88dk.org/site/), sccz80 with the classic lib.

Every colour system has a **Black and white** option in its `## <system>` block (and the Systems tab). It converts
the art to a dithered black-and-white band and forces white text on the black background. On the 48K, turning it off
uses classic 8x8 attribute-colour art; its mono mode keeps the Game-tab text colours and `title_ink:` for the title,
text and menu options, like the 128K. The Oric Atmos is always monochrome and has no such option. The HTML5
runtime also bakes its art this way and has its own `art_rows` and `dither` settings.

The build driver is a pluggable target registry (`tools/targets/`). Each target module exports a `TARGET` with its
output names, per-game options and build, validation and preview hooks. The selected systems and their options live
under a `# Systems` section in `game.md`.
Building:

```bash
python3 tools/build.py list-targets
python3 tools/build.py build <game>              # all selected
python3 tools/build.py build <game> zx sms       # explicit
python3 tools/build.py build <game> --all
python3 tools/build.py build <game> zx128 --variant es   # one variant
```

Outputs: `<slug>.tap` / `.sna` (ZX 128K), `<slug>-48k.tap` (ZX 48K), `.nex` (ZX Next), `.dsk` (CPC 6128),
`-cpc464.dsk` (CPC 464), `<slug>-msx1.rom` (MSX1), `.rom` (MSX2), `.prg` (Commodore 64), `<slug>-oric.tap`
(Oric Atmos), `.sms` (Sega Master System), `.nes` (NES), `.gbc` (Game Boy Color) and `<game-folder>/web/` (HTML5).

Every build writes the standalone Web Player to `<game-folder>/web/`. The automatic **Web Player** step contains
the selected systems' browser emulators and playable files; ticking **HTML5** builds the **HTML5 game**, which adds
the mobile-first story, framed by its own `art_rows` and optionally baked as dithered black-and-white art. Build the
player alone with `python3 tools/build.py build <game> webplayer`, or the game with `... build <game> web`;
`python3 tools/webgame.py <slug> --player|--game` does the same export directly. The Emulator tab auto-exports and
previews the combined player; the top-bar **Export player** button re-exports and reloads it.
See [the Web Player](docs/web-player.md).

## Licenses

Retro Visual Novel is released under the MIT License; see [LICENSE](LICENSE).

Vendored components keep their own upstream licenses: see
`tools/editor/static/emulator/THIRD_PARTY.md` for the browser emulators, and the
`README`/`LICENSE` files under `vendor/` (NIRVANA+, ZX0 and Pixel Operator).

## Notes for developers and agents

See **`AGENTS.md`** for project conventions, build/verify recipes and invariants.
