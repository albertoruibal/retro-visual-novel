# MSX1 (TMS9918A)

- **Display:** TMS9918A Graphics II (SCREEN 2), 256 x 192 pixels as 32 x 24 tiles. Row 0 is the scene title, rows
  1..`art_rows` the picture, and the text pane starts at `1 + art_rows`. Each 8x8 art cell has two TMS9918 colours
  per 8x1 pixel row (foreground high nibble, background low nibble), so the picture is a tile mosaic rather than a
  full bitmap. The 15-colour TMS palette is used; colour 0 (transparent) is avoided.
- **Text:** 32 columns using the shared CC0 Pixel Operator Mono 8 font. The build bit-reverses each font byte (the
  font is stored LSB-left, Graphics II reads MSB-left) and copies the 768-byte font into all three 2 KB pattern
  banks. Scene text scrolls with UP/DOWN; with `menu: popup` the options/items live in the `SPACE`/fire dialog.
- **Black and white:** `mono: on` renders the picture as a dithered white-on-black 1-bit band and forces white text
  on the black background, instead of the 15-colour palette. Colour art uses the full `dither:` list between each
  8x1 row's ink and paper; in mono, `off` becomes a 2x2 Bayer dither, like the 48K Spectrum.
- **Text colours:** Graphics II attaches colour to a pattern, not a cell. Selected text therefore uses cached
  duplicate glyph patterns in the screen third's spare pattern slots, with the highlight ink in their colour-table
  entries; ordinary text keeps the shared font patterns. This keeps the highlighted row from recolouring every other
  occurrence of the same letters.
- **Conversion:** `tools/msx1art.py` fits the source to the 256 x `8*art_rows` band. For colour it quantises to the
  TMS palette, picks the best two colours for each 8x1 row and deduplicates by both the 8x8 pattern and its colours
  (at most 160 art tiles), because the TMS9918A colour table is indexed by pattern number rather than by screen cell.
  When the cap is reached the closest existing pattern and its established colours are reused. A compiled art blob is
  `[u8 ntiles][cell[32*art_rows][1 pnt + 8 colour bytes]][u8 patterns[ntiles*8]]`; the name-table byte is the real
  Graphics II pattern number (96..255 for art, 0..95 for the font).
- **Storage:** scene/inventory data lives in ASCII16 ROM bank 1. Each art gets one 16K bank from bank 2, and the
  font gets the next bank. Art and story blobs are ZX0-compressed (`[u16 length][ZX0 stream]`). The fixed linked
  binary must stay below 0x8000; the target checks the link map and fails the build instead of writing a ROM whose
  scene bank was silently dropped.
- **Sound:** the MSX1 target currently builds with no songs (the PSG player is not wired up yet). Use the MSX2
  target for music.
- **Options:** `art_rows` (8, 10 or 12, default 10), `margin` (N 8x8-cell side borders filled with the background),
  `mono` (Black and white), `dither` (colour and mono) and `menu: popup` for the action dialog.
- **Build:** `zcc +msx -subtype=rom` with `-pragma-define:MAPPER_ASCII16`, output `<slug>-msx1.rom`. The game needs an
  ASCII16-capable cartridge/slot.
- **Emulator:** WebMSX with C-BIOS in MSX1 mode (`emulator/msx`, `MACHINE=MSX1`).

Key files: `tools/msx1art.py`, `src/msx1/plat_msx1.c`, `src/msx1/msx1_vram.asm`, `tools/targets/msx1.py`,
`vendor/pixeloperator8/`, `vendor/zx0/`.
