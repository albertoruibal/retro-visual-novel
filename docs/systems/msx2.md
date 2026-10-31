# MSX2 (V9938)

- **Display:** Screen 7 (512 x 212, 4 bits per pixel, 16 colours from the V9938's RGB333 palette). The full-width 512 x
  `8 * art_rows` picture sits above a 64- or 80-column text pane. Title row 0, art rows 1..`art_rows`, text rows
  `1+art_rows`..22 and the inventory on row 23.
- **Text:** 64 columns (the default) use 8 x 8 glyphs, 8 pixels per cell, so the text spans the full 512-pixel width; 80
  columns use 6-pixel cells (a 4-pixel glyph plus a 2-pixel gap), starting at x=16. Both are drawn directly into the
  4bpp bitmap. Palette entry 0 is the game's `text_bg:` (default black), entry 14 `highlight_ink:` and entry 15
  `text_ink:` (all snapped to RGB333), so selected options/words use the chosen highlight colour and cleared rows use
  the chosen background. The remaining 13 entries come from the art, though the picture may also use the reserved
  ones. Changing any of the three rebakes every art blob, so rebuild the `.rom`. The text pane is fixed: it never
  scrolls, so scene text and options must fit the rows left below the art band. With `## msx2 menu: popup` the
  options and held items move to the `SPACE`/joystick-button-2 dialog, the text may use row 23, and only the text
  lines must fit (`23 - art_rows` rows).
  A long item description scrolls with up/down while the cursor is on the first entry.
  Text is emitted by an assembly loop from a glyph-cell table built at startup in RAM from the raw 768-byte font
  (`port_font8_raw.h` for 64 columns or `port_font4.h` for 80), using the shared CC0 8x8 Pixel Operator Mono 8 or the
  4x8 CRT font; scene clears use the V9938 HMMV command, and a scene redraw only clears the title/text pane, never the
  art band it is about to overwrite. The runtime expansion keeps up to 2.3 KB out of the tight 16 KB fixed ROM bank.
- **Conversion:** `tools/msx2art.py` shares one converter between the editor preview and the build. Each art is a 512 x
  `8*art_rows` 4bpp bitmap with a per-art 16-colour palette. Screen 7's pixels are half-width (512 pixels span the same
  physical width as Screen 5's 256), so the source is fitted to the band's `256 x 8*art_rows` physical aspect and
  stretched into the pixel grid. An explicit `crop:` keeps its full width: the vertical window is re-centred to that
  aspect (clamped to the source), so it is neither stretched nor cropped sideways. The editor preview is doubled
  vertically so it shows the physical proportions. Palette bytes are `red:3 << 4 | blue:3` followed
  by `green:3`.
- **Storage:** scene/inventory data lives in ASCII16 ROM bank 1. Each art gets its own 16K bank starting at bank 2: the
  blob is `[u8 palette[16*2]][u16 comp_len][ZX0 2048-byte strip] * art_rows`, so the runtime decompresses one 8-line
  strip at a time and writes it straight into VRAM. Songs are ZX0-compressed into ROM banks after the art banks
  (`build/port_song.asm`); the mapper is selected with `-pragma-define:MAPPER_ASCII16`.
- **Sound:** `# Game songs:` / per-scene `music:` PT3 modules play through z88dk's VT2 player from the VDP IM1
  interrupt. The module is ZX0-decoded from its ROM bank into a `SONG_WS_SIZE` BSS buffer; `build/port_song.asm` packs
  the songs after the art banks. Press `P` to toggle music.
- **Options:** `art_rows` (8, 10 or 12, default 12), `columns` (64 or 80, default 64) and `menu: popup` for the
  action dialog.
- **Build:** `zcc +msx -subtype=rom2`, then `build/port_art.asm`; output `<slug>.rom`. The scene/inventory and per-strip art
  blobs are ZX0-compressed.
- **Emulator:** WebMSX with C-BIOS in MSX2 mode (`emulator/msx`).

Key files: `tools/msx2art.py`, `src/msx2/plat_msx2.c`, `build/port_font8_raw.h`/`build/port_font4.h` (generated raw
fonts expanded into RAM at startup), `build/port_song.asm`, `src/portable/core/music.c`, `vendor/pixeloperator8/`,
`vendor/zx0/`.
