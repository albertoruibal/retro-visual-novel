# Vendored web emulator runtimes

These files are served by the editor's **Emulator** tab. They are pinned and loaded locally so the editor keeps working
offline.

- **Sega Master System:** EmulatorJS + smsplus
  (`https://emulatorjs.org`, `https://github.com/EmulatorJS/smsplus-gx`); GPL-3.0 (EmulatorJS); retain the smsplus core
  notices.
- **Nintendo Game Boy Color:** EmulatorJS + gambatte
  (`https://emulatorjs.org`, `https://github.com/EmulatorJS/gambatte-libretro`); GPL-3.0 (EmulatorJS); Gambatte is
  GPL-2.0.
- **Commodore 64:** EmulatorJS + VICE x64sc
  (`https://emulatorjs.org`, `https://github.com/EmulatorJS/vice-libretro`, `https://vice-emu.sourceforge.io`);
  GPL-3.0 (EmulatorJS); VICE is GPL-2.0 (core notices in `c64/NOTICE`). The core build embeds the C64 ROMs.
- **NES:** EmulatorJS + FCEUmm
  (`https://emulatorjs.org`, `https://github.com/EmulatorJS/libretro-fceumm`); GPL-3.0 (EmulatorJS); FCEUmm is
  GPL-2.0 (core notices in `nes/NOTICE`).
- **MSX:** WebMSX C-BIOS embedded (`https://github.com/ppeccin/WebMSX`); C-BIOS is 2-clause BSD; WebMSX has no root
  license file, see `msx/NOTICE`.
- **Amstrad CPC 6128 / 464:** CPCJS / Caprice32 WASM
  (`https://github.com/smichea/cpcjs`, `https://github.com/ColinPitrat/caprice32`); GPL-2.0; Caprice32 ROM packaging
  notices in `cpc/NOTICE`.
- **Oric Atmos:** Oricutron WASM (`https://github.com/jumpjack/oricutronJS`,
  upstream `https://github.com/pete-gordon/oricutron`); GPL-2.0. The asset bundle embeds the Atmos ROM; see
  `oric/NOTICE`. The page feeds the built `.tap` through Oricutron's `ENV.FILE` loader, which types `CLOAD""` and
  starts the auto-run tape.
- **ZX Spectrum 128K:** JSSpeccy 3 (`jsspeccy/jsspeccy.js.LICENSE.txt`); GPL-3.0 / upstream notices.
- **ZX Spectrum Next:** no web emulator is bundled. Run the `.nex` with an external ZEsarUX (TBBlue); the editor's
  Emulator tab intentionally does not list Next.

The EmulatorJS data (`emulatorjs/data`), including the smsplus, gambatte, vice_x64sc and fceumm cores, is shared by
the SMS, Game Boy Color, Commodore 64 and NES pages; the Oric page uses its own `oric/` bundle. The editor's server
serves these files through `/emulator/<path>`; the game artifacts are fetched from
`/api/artifact/<slug>/<name>`.
