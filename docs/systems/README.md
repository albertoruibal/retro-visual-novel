# System particularities

One page per build system. The shared runtime (`src/portable/core/`) handles scenes, flags, items, selectable words
and the inventory on **every** target, including the Spectrum; each page records the display, art conversion, storage
and emulator details that differ. The platform layers are `src/zx/plat_zx.c`, `src/next/plat_next.c`,
`src/sms/plat_sms.c`, `src/cpc/plat_cpc.c` (shared by the 6128 and 464), `src/msx2/plat_msx2.c`,
`src/gb/plat_gb.c`, `src/c64/plat_c64.c`, `src/nes/plat_nes.c` and `src/oric/plat_oric.c`.

| System | Page | Output |
|---|---|---|
| ZX Spectrum 128K | [zx128.md](zx128.md) | `.tap`, `.sna` |
| ZX Spectrum 48K | [zx48.md](zx48.md) | `.tap` |
| ZX Spectrum Next | [next.md](next.md) | `.nex` |
| Sega Master System | [sms.md](sms.md) | `.sms` |
| Amstrad CPC 6128 | [cpc.md](cpc.md) | `.dsk` |
| Amstrad CPC 464 | [cpc464.md](cpc464.md) | `<slug>-cpc464.dsk` |
| MSX2 (V9938) | [msx2.md](msx2.md) | `.rom` |
| Nintendo Game Boy Color | [gb.md](gb.md) | `.gbc` |
| Commodore 64 | [c64.md](c64.md) | `.prg` |
| Nintendo Entertainment System | [nes.md](nes.md) | `.nes` |
| Oric Atmos | [oric.md](oric.md) | `<slug>-oric.tap` |

Targets are discovered from `tools/targets/` and selected under `## Systems` in `game.md`:

    ## Systems
    ## zx128
    art_rows: 12
    ## gb
    art_rows: 6
    ## c64
    art_rows: 6
    ## nes
    art_rows: 10
    ## oric
    art_rows: 8

The build driver, editor previews and Emulator tab all read the same registry, so adding a system does not require a
central switch.

The browser runtime is not a `## Systems` build target; it always plays the saved story with the selected system's
`art_rows` framing. See [the web runtime](../web-runtime.md).
