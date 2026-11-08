# Oric Atmos

- **Display:** the 240 x 200 HIRES bitmap at `$A000`. The title is on character row 0, the art band occupies rows
  1..`art_rows`, and the text pane runs from row `art_rows + 1` through row 24. `art_rows` is 4, 6, 8, 10 or 12
  (default 8). Text is drawn in software with a 6x8 glyph table: 40 columns of 8-pixel rows, so a scene has
  `24 - art_rows` text rows. The three text rows below the bitmap are kept blank, and `plat_init` clears the ROM
  status cursor bit so its flashing text cursor does not blink there.
- **Options and items:** the portable action dialog. `SPACE` opens and closes it, the cursor keys or `W`/`A`/`S`/`D`
  move and scroll the list, and `RETURN` confirms. A long scene body scrolls with `UP`/`DOWN`; there is no pinned
  menu or inventory row. The dialog lists scene options first and then held items (prefixed `*`).
- **Colours:** monochrome. HIRES is one ink and one paper colour for the whole screen, and the Oric's serial
  attributes cost a screen cell each time they change a colour, so the target uses white ink on black paper for the
  picture and text. Selection and highlighted words use inverse video; the `>` marker is still drawn.
- **Art:** `tools/oricart.py` fits the source to 240 x `8 * art_rows`, applies the `## oric dither:` scheme and source
  adjustments, and packs 40 bytes per row (bit 6 set, bit 5 the leftmost pixel). Because HIRES is 1-bit,
  `dither: off` is forced to a 2x2 Bayer dither (an explicit scheme is honoured); a hard threshold would throw away
  every mid-tone, and the coarse matrix keeps the resident blobs small enough to fit. Each art blob is
  `[u8 ink][u8 paper][ZX0 pixel stream]`; `src/oric/plat_oric.c` decodes it straight into the bitmap band. The blob is
  compressed in the `.tap`, so changing the conversion settings requires a rebuild.
- **Text:** `tools/gen_port.py --oric` emits `build/port_font6.h` from the shared Pixel Operator 8 font, fitting the
  8x8 glyphs to the Oric's 6-pixel cell and reversing the bits for the ULA. Columns 6 and 7 are folded into the sixth
  pixel rather than cropped, so wide glyphs (M, W, #, %, @, ...) keep their right edge. Text is drawn into the bitmap;
  a selected row is the inverse of the glyph's six pixels.
- **Storage/memory:** there is no banking. Scene, inventory and art blobs are resident and ZX0-compressed, decoded by
  the shared `src/6502/zx0.c`. The cc65 `atmos` layout loads at `$0501`, keeps the image and BSS below the 2K C stack
  at `$97FF`, and reserves `$A000-$BF3F` for HIRES. `tools/targets/oric.py` checks the linker map and reports a clear
  overflow message; lower `oric art_rows`, remove arts or shorten the story if it does not fit.
- **Controls:** cursor keys or `W` `A` `S` `D` move; `RETURN` confirms; `SPACE` opens/closes the action dialog.
- **Sound:** not implemented yet. The Atmos has an AY-3-8912, but there is no 6502 PT3 player in the repository, so the
  build ignores the game's `songs:`/`music:` settings.
- **Build:** `cl65 -t atmos -C atmos.cfg -Oirs ...`, output `<slug>-oric.tap`. cc65 is required (z88dk has no Oric
  target). The editor Docker image contains cc65; on a desktop install cc65 and point the **Build toolchain** settings
  card at it. The tape is marked `__AUTORUN__ = $C7`, so `CLOAD""` starts the BASIC stub and then the game.
- **Emulator:** the editor's Emulator tab runs the `.tap` in a pinned Oricutron WASM build. The page feeds the artifact
  through Oricutron's `ENV.FILE` loader; Oricutron types `CLOAD""` and the auto-run header starts the game. Click the
  picture first so the canvas takes keyboard focus. You can also run the tape in desktop Oricutron or another
  Oric-1/Atmos emulator.
- **Limitations:** no boot-password screen; no music; the picture and text are monochrome; the 37 KB resident budget is
  the main size limit.

Key files: `tools/targets/oric.py`, `tools/oricart.py`, `src/oric/plat_oric.c`, `src/oric/atmos.cfg`, `src/6502/zx0.c`,
`tools/gen_port.py`, `tools/editor/static/emulator/oric/`.
