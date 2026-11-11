# Retro Visual Novel

**Retro Visual Novel** is an 8-bit visual novel creator for the ZX Spectrum 128K
and other 8-bit targets, with a shared engine and authoring UI.

## Supported targets

- [ZX Spectrum 128K](docs/systems/zx128.md)
- [ZX Spectrum 48K](docs/systems/zx48.md)
- [ZX Spectrum Next](docs/systems/next.md)
- [Amstrad CPC 6128](docs/systems/cpc.md) (alpha)
- [Amstrad CPC 464](docs/systems/cpc464.md) (alpha)
- [MSX2](docs/systems/msx2.md) (alpha)
- [Sega Master System](docs/systems/sms.md)  (alpha)
- [Nintendo Game Boy Color](docs/systems/gb.md) (alpha)
- [Commodore 64](docs/systems/c64.md) (alpha)
- [Nintendo Entertainment System](docs/systems/nes.md) (alpha)
- [Oric Atmos](docs/systems/oric.md) (alpha)
- [Web player](docs/web-runtime.md) (mobile-first novel plus the selected systems' emulators)

See [playing the games](docs/playing.md) for the controls on each target.

## Games

The game is defined in a folder with a `game.md` in its root,
see the example in [demo-game/game.md](demo-game/game.md).

It is defined in markdown, it can be manually edit or with the UI.

See [authoring games](docs/authoring.md) for information about the Markdown format.


## Editor desktop app

It is an electron app that allows to edit and build games. The engine and tools ship with the app.

It has tabs to edit the game sections:

* Game: Global game settings.
* Systems: Chooses the systems to build the game for and their specific options; each platform has its own sub-tab.
* Art: Allows to generate and upload images and previews them for every selected system.
* Music: Imports PT3, converts from MIDI with spectrumizer, and plays on the AY targets (ZX Spectrum, CPC 6128/464 and
  MSX2); the Master System build converts PT3 to SN76489 PSG data and the Game Boy Color build to Game Boy APU
  register data, so songs play there too. The Commodore 64, NES and Oric Atmos builds currently ignore
  songs.
* Scenes: Defines the text and logic for each scene.
* Flags: Flags are game-wide and can be enabled/disabled, some scene lines and options ara available when a certain flag is set.
* Items: Carried by the player, each item can be selected, and it has options that can be enabled only for certain scenes. 
* Graph: Draws a graph of the scene relationship.
* Source: Allows to directly edit the Markdown of the game with syntax validation and navigation via CTRL + click.
* Build: Builds the game for the selected systems. The Build log separates each system with a
  `==== name [id] ====` banner.
* Emulator: Plays the selected system with offline, vendored web emulators: JSSpeccy for ZX,
  EmulatorJS/smsplus for SMS, WebMSX C-BIOS for MSX2, CPCJS/Caprice32 for the CPC 6128 and CPC 464,
  EmulatorJS/Gambatte for Game Boy Color, EmulatorJS/VICE x64sc for Commodore 64,
  EmulatorJS/FCEUmm for NES and Oricutron for Oric Atmos. The **Web player** entry previews the exported player:
  the mobile-first novel plus only the selected systems, with a download link for each native file. The same toolbar
  exports `<game-folder>/web/`, opens it in a new tab, or downloads an itch.io-ready zip. ZX Next is not bundled in
  the browser; use `python3 tools/build.py run <game> next` with ZEsarUX.

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

Outputs: `<slug>.tap` / `.sna` (ZX), `.nex` (ZX Next), `.sms`, `.dsk` (CPC 6128), `.dsk` with the
`-cpc464` suffix (CPC 464), `.rom` (MSX2), `.gbc` (Game Boy Color), `.prg` (Commodore 64), `.nes` (NES) and
`<slug>-oric.tap` (Oric Atmos).

The web player is separate from the 8-bit build: `python3 tools/webgame.py <slug>` writes a standalone
`<game-folder>/web/` folder containing the novel, the selected systems' web emulators and their playable files. The
editor's **Emulator → Web player** entry does the same plus an itch.io-ready zip download. See
[the web player](docs/web-runtime.md).

## Licenses

Retro Visual Novel is released under the MIT License; see [LICENSE](LICENSE).

Vendored components keep their own upstream licenses: see
`tools/editor/static/emulator/THIRD_PARTY.md` for the web emulators, and the
`README`/`LICENSE` files under `vendor/` (NIRVANA+, ZX0 and Pixel Operator).

## Notes for developers and agents

See **`AGENTS.md`** for project conventions, build/verify recipes and invariants.
