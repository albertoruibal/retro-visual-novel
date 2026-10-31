# System particularities

One page per build system. The shared runtime (`src/portable/core/`) handles scenes, flags, items, selectable words
and the inventory on **every** target, including the Spectrum; each page records the display, art conversion, storage
and emulator details that differ. The platform layers are `src/zx/plat_zx.c`, `src/sms/plat_sms.c`,
`src/cpc/plat_cpc.c`, `src/msx2/plat_msx2.c` and `src/gb/plat_gb.c`.

| System | Page | Output |
|---|---|---|
| ZX Spectrum 128K | [zx.md](zx.md) | `.tap`, `.sna` |
| Sega Master System | [sms.md](sms.md) | `.sms` |
| Amstrad CPC 6128 | [cpc.md](cpc.md) | `.dsk` |
| MSX2 (V9938) | [msx2.md](msx2.md) | `.rom` |
| Nintendo Game Boy Color | [gb.md](gb.md) | `.gbc` |

Targets are discovered from `tools/targets/` and selected under `## Systems` in `game.md`:

    ## Systems
    ## zx
    art_rows: 12
    ## gb
    art_rows: 6

The build driver, editor previews and Emulator tab all read the same registry, so adding a system does not require a
central switch.

The browser runtime is not a `## Systems` build target; it always plays the saved story with the selected system's
`art_rows` framing. See [the web runtime](../web-runtime.md).
