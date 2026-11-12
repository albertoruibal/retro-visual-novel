# Nintendo Game Boy Color (CGB)

The `# Systems` id remains `gb` for compatibility with existing games.

- **Black and white:** `mono: on` dithers the picture to white-on-black and forces white text.
- **Display:** 160x144, 20x18 tiles. `art_rows` is 8: rows 1..`art_rows` are the picture, row 0
  the scene title and rows `art_rows+1`..17 the text pane. The body uses the whole pane (9 rows) and
  scrolls up/down when it overflows; left/right moves between highlighted words (or scrolls when a scene has none).
  B opens an overlay dialog listing the scene options and held items (items are prefixed `*`); the D-pad scrolls it,
  A/Start confirms and B closes it. A long item description also scrolls with up/down. There is no permanent
  inventory row.
- **Colour:** the CGB background has eight four-colour palettes, selected per tile by an attribute byte in VRAM bank
  1. Palettes 6 and 7 are the configured body and highlight text palettes; the picture uses palettes 0..5, so it has
  up to 24 adaptive colours. A cartridge is built as CGB-enhanced (`0x80`), so the same `.gbc` also boots on an
  original monochrome Game Boy, where the palette and attribute writes are skipped and the built-in `BGP=0xE4`
  mapping shows four shades. Selection still carries the `>` marker, so it remains visible on a DMG.
- **Tiles:** 96 font tiles, two scroll-arrow tiles, and up to 158 art tiles in the 256-tile VRAM pattern table. The font
  is the CC0 8x8 Pixel Operator Mono 8 (see `vendor/pixeloperator8/`), expanded to 2bpp tiles at build time; the
  accented slots used by the shared text encoding come from the same font. Art is 160 x `8 * art_rows` 2bpp:
  `[u8 ntiles][u8 npalettes][u16 palettes[npalettes][4]][tiles: ntiles x 16][map: 20 * art_rows][attrs: 20 *
  art_rows]`, with map entries offset by 96 and attribute bytes holding the palette index. Tiles are deduplicated;
  excess cells reuse the nearest kept tile and its palette. Palettes are ordered light-to-dark for the DMG fallback.
- **Conversion:** `tools/gbart.py` crops/fits to the 160px band, adjusts the source, quantises each 8x8 tile to four
  colours and clusters those tile palettes into at most six shared art palettes. The `## gb` system block accepts
  the full `dither:` list and dithers between each tile's four colours; the tile palettes are still chosen from the
  undithered image. An explicit `crop:` keeps its full width and
  re-centres the vertical window to the band aspect, so the picture is not stretched. `margin:` adds N 8x8-cell
  borders on the left and right, filled with `text_bg`; the picture is scaled to the inner width with its aspect
  preserved. The editor preview and the ROM use the same converter.
- **Text colours:** `text_ink:`, `highlight_ink:` and `text_bg:` are resolved to GBC RGB555 values and loaded into
  palettes 6/7. The art converter reserves those two palettes, so the authored text colours never depend on the
  picture's colours.
- **Sound:** PT3 songs are converted at build time by `tools/gbmusic.py` to a Game Boy APU register stream. AY tone
  channels A/B/C map to pulse 1, pulse 2 and the wave channel; AY noise uses the noise channel; the AY hardware
  envelope is approximated per frame and low notes are folded up to fit the 11-bit divider. Each stream starts at a
  bank boundary after the art and is read directly from banked ROM by `src/gb/gb_music.c`, so it uses no work RAM. The
  vblank handler divides the ~59.7 Hz frame rate down to the stream's 50 Hz. `Select` toggles music. The converter uses
  the pinned spectrumizer PT3 decoder, so a module with unsupported PT3 commands fails the build with a clear message
  instead of playing incorrectly.
- **Storage:** the CGB has no SM83 ZX0 decoder, so blobs are **uncompressed**. `build/port_data.c` (names, start flags,
  tables and the text palettes) stays in bank 0. Scene and inventory blobs are packed with `[u16 length]` prefixes into
  MBC1 banks from bank 1; art follows in the next banks, then the converted song streams. `plat_set_bank` writes the
  MBC1 bank register at 0x2000, `gb_copy.asm` copies a blob from 0x4000, and `gb_vram.asm` writes VRAM while waiting
  for a safe LCD mode. appmake supplies banks through `0x1F`, so the whole cartridge is capped at 32 banks (512K).
- **Build:** `zcc +gb -compiler=sdcc -create-app` with `PLAT_ROWS=18`; appmake emits an MBC1 cartridge. The target
  then patches byte `0x143` to `0x80` and recomputes the header complement and global checksums. Output `<slug>.gbc`.
- **Emulator:** EmulatorJS with the Gambatte core (`emulator/gb`).

Limitations: no boot-password screen on the Game Boy Color. Keep the fixed-bank code below 0x4000 and BSS below the
stack at 0xE000; the target checks the link map.

Key files: `tools/gbart.py`, `tools/gbmusic.py`, `src/gb/plat_gb.c`, `src/gb/gb_music.c`, `src/gb/gb_copy.asm`,
`src/gb/gb_vram.asm`, `tools/targets/gb.py`.
