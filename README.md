# Retro Visual Novel

**Retro Visual Novel** is an 8-bit visual novel creator for the ZX Spectrum 128K
and other 8-bit targets, with a shared engine and authoring UI.

## Supported targets

- [ZX Spectrum 128K](docs/systems/zx.md)
- [ZX Spectrum Next](docs/systems/next.md)
- [Amstrad CPC 6128](docs/systems/cpc.md) (alpha)
- [MSX2](docs/systems/msx2.md) (alpha)
- [Sega Master System](docs/systems/sms.md)  (alpha)
- [Nintendo Game Boy Color](docs/systems/gb.md) (alpha)
- [Web runtime](docs/web-runtime.md) (mobile-first standalone SPA)

See [playing the games](docs/playing.md) for the controls on each target.

## Games

The game is defined in a folder with a `game.md` in its root,
see the example in [games/demo/game.md](games/demo/game.md).

It is defined in markdown, it can be manually edit or with the UI.

See [authoring games](docs/authoring.md) for information about the Markdown format.


## Editor desktop app

It is an electron app that allows to edit and build games. The engine and tools ship with the app.

It has tabs to edit the game sections:

* Game: Global game settings.
* Systems: Chooses the systems to build the game for and their specific options.
* Art: Allows to generate and upload images and previews them for every selected system.
* Music: Imports PT3, converts from MIDI with spectrumizer, and plays on the AY targets (ZX Spectrum, CPC 6128 and
  MSX2); the Master System build converts PT3 to SN76489 PSG data and the Game Boy Color build to Game Boy APU
  register data, so songs play there too.
* Scenes: Defines the text and logic for each scene.
* Flags: Flags are game-wide and can be enabled/disabled, some scene lines and options ara available when a certain flag is set.
* Items: Carried by the player, each item can be selected, and it has options that can be enabled only for certain scenes. 
* Graph: Draws a graph of the scene relationship.
* Source: Allows to directly edit the Markdown of the game with syntax validation and navigation via CTRL + click.
* Build: Builds the game for the selected systems. The Build log separates each system with a
  `==== name [id] ====` banner.
* Web: Runs the mobile-first web runtime in an iframe; it can open in a new tab, export a self-contained
  `games/<slug>/web/` folder, or download that folder as a zip.
* Emulator: The Emulator tab plays the selected system with offline, vendored web emulators: JSSpeccy for ZX,
  EmulatorJS/smsplus for SMS, WebMSX C-BIOS for MSX2, CPCJS/Caprice32 for CPC and EmulatorJS/Gambatte for
  Game Boy Color. ZX Next is not bundled; use `python3 tools/build.py run <game> next` with ZEsarUX.

The engine and tools ship with the app.

To make the build work, the editor needs a complete z88dk toolchain (a folder containing `bin/zcc` and
the `z88dk-zx0` host compressor) configured in the top-bar **Settings**.
On Linux a z88dk Snap install (`snap install z88dk --beta`, the tree at`/snap/z88dk/current`) is detected automatically.
For Windows and Mac, download a nightly build from `http://nightly.z88dk.org`.

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

## Game building toolchain

It uses python tools and z88dk (https://z88dk.org/site/), sccz80 with the classic lib.

The build driver is a pluggable target registry (`tools/targets/`). Each target module exports a `TARGET` with its
output names, per-game options and build, validation and preview hooks. The selected systems and their options live
under a `# Systems` section in `game.md`.
Building:

```bash
python3 tools/build.py list-targets
python3 tools/build.py build <game>              # all selected
python3 tools/build.py build <game> zx sms       # explicit
python3 tools/build.py build <game> --all
```

Outputs: `<slug>.tap` / `.sna` (ZX), `.nex` (ZX Next), `.sms`, `.dsk` (CPC), `.rom` (MSX2), `.gbc` (Game Boy Color).

The web runtime is separate from the 8-bit build: `python3 tools/webgame.py <slug>` writes a standalone
`games/<slug>/web/` folder (and the editor's Web tab does the same plus a zip download). See
[the web runtime](docs/web-runtime.md).

## Licenses

See `tools/editor/static/emulator/THIRD_PARTY.md` for upstream licenses of the emulators.

## Notes for developers and agents

See **`AGENTS.md`** for project conventions, build/verify recipes and invariants.
