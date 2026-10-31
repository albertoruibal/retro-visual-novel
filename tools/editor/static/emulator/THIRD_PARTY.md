# Vendored web emulator runtimes

These files are served by the editor's **Emulator** tab. They are pinned and loaded locally so the editor keeps working
offline.

- **Sega Master System:** EmulatorJS + smsplus
  (`https://emulatorjs.org`, `https://github.com/EmulatorJS/smsplus-gx`); GPL-3.0 (EmulatorJS); retain the smsplus core
  notices.
- **Nintendo Game Boy Color:** EmulatorJS + gambatte
  (`https://emulatorjs.org`, `https://github.com/EmulatorJS/gambatte-libretro`); GPL-3.0 (EmulatorJS); Gambatte is
  GPL-2.0.
- **MSX:** WebMSX C-BIOS embedded (`https://github.com/ppeccin/WebMSX`); C-BIOS is 2-clause BSD; WebMSX has no root
  license file, see `msx/NOTICE`.
- **Amstrad CPC 6128:** CPCJS / Caprice32 WASM
  (`https://github.com/smichea/cpcjs`, `https://github.com/ColinPitrat/caprice32`); GPL-2.0; Caprice32 ROM packaging
  notices in `cpc/NOTICE`.
- **ZX Spectrum 128K:** JSSpeccy 3 (`jsspeccy/jsspeccy.js.LICENSE.txt`); GPL-3.0 / upstream notices.

The EmulatorJS data (`emulatorjs/data`), including the smsplus and gambatte cores, is shared by the SMS and
Game Boy Color pages. The editor's server serves these files through `/emulator/<path>`; the game artifacts are
fetched from `/api/artifact/<slug>/<name>`.
