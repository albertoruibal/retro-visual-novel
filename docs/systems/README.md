# System particularities

One page per build system. The shared runtime (`src/portable/core/`) handles scenes, flags, items, selectable words
and the inventory on **every** target, including the Spectrum; each page records the display, art conversion, storage
and emulator details that differ. The platform layers are `src/zx/plat_zx.c`, `src/next/plat_next.c`,
`src/sms/plat_sms.c`, `src/cpc/plat_cpc.c` (shared by the 6128 and 464), `src/msx1/plat_msx1.c`, `src/msx2/plat_msx2.c`,
`src/gb/plat_gb.c`, `src/c64/plat_c64.c`, `src/nes/plat_nes.c` and `src/oric/plat_oric.c`.

| System | Page | Output |
|---|---|---|
| ZX Spectrum 128K | [zx128.md](zx128.md) | `.tap`, `.sna` |
| ZX Spectrum 48K | [zx48.md](zx48.md) | `.tap` |
| ZX Spectrum Next | [next.md](next.md) | `.nex` |
| Sega Master System (alpha) | [sms.md](sms.md) | `.sms` |
| Amstrad CPC 6128 (alpha) | [cpc.md](cpc.md) | `.dsk` |
| Amstrad CPC 464 (alpha) | [cpc464.md](cpc464.md) | `<slug>-cpc464.dsk` |
| MSX1 (TMS9918A) (alpha) | [msx1.md](msx1.md) | `<slug>-msx1.rom` |
| MSX2 (V9938) (alpha) | [msx2.md](msx2.md) | `.rom` |
| Nintendo Game Boy Color (alpha) | [gb.md](gb.md) | `.gbc` |
| Commodore 64 (alpha) | [c64.md](c64.md) | `.prg` |
| Nintendo Entertainment System (alpha) | [nes.md](nes.md) | `.nes` |
| Oric Atmos (alpha) | [oric.md](oric.md) | `<slug>-oric.tap` |
| Web | [web-runtime.md](../web-runtime.md) | `<game-folder>/web/` |

Targets are discovered from `tools/targets/` and selected under `## Systems` in `game.md`:

    ## Systems
    ## zx128
    art_rows: 12
    margin: 1
    ## gb
    art_rows: 8
    ## c64
    art_rows: 8
    ## nes
    art_rows: 10
    ## oric
    art_rows: 8

Every art-capable system also accepts `margin:` (default `0`): the whole picture is scaled down to leave that many 8x8
cells on the left and right, keeps its aspect ratio, and the side border is filled with the system's `text_bg` colour.
Margin `0` is the old full-bleed band; a positive value can only reduce the art tiles. Editor previews show the scaled
picture inside the margins, without the blank border.

Every colour art system also accepts `mono: on` (the **Black and white** option in the Systems tab): it converts the
picture to a dithered black-and-white band and forces white text on the black background. On the 48K, turning it off
uses classic 8x8 attribute-colour art and the Game-tab text colours; the Oric Atmos is always monochrome and has no
such option. The Web target grayscales the novel art.

The build driver, editor previews and Emulator tab all read the same registry, so adding a system does not require a
central switch.

The browser player is a `## Systems` build target (`## web`): selecting it builds `<game-folder>/web/` with the saved
story framed by the first selected native system's `art_rows` and lists only the selected systems' emulators and
files. See [the web player](../web-runtime.md).
