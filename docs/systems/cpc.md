# Amstrad CPC 6128

The 64K [CPC 464](cpc464.md) uses the same runtime and art converter but streams
the compressed art/song blobs from the disk instead of paging the extra banks.

- **Black and white:** `mono: on` dithers the picture to white-on-black and forces white text on black; Mode 1
  already uses its four-pen grey ramp.
- **Display:** Mode 1 by default (320x200, four monochrome shades); Mode 0 (160px, 16 inks) and Mode 2 (640px, two
  inks) are selectable. Text uses 32, 40 or 62 columns on 25 rows; Mode 0 fits at most 40 (4px font for 32/40), while
  Modes 1/2 use the 8px font for 32/40 and the compact 4px font for 62. By default every mode keeps the text pane
  with pinned options and the inventory row; `menu: popup` gives it the `SPACE`-key overlay dialog instead (the text
  then uses every row below the art, the list scrolls with the cursor, Enter/fire confirms and `SPACE` closes, and a
  long item description scrolls with up/down).
- **Art:** `mode_width` x `8 * art_rows` (160/320/640 wide); Mode 1 is 320 x `8 * art_rows`. Mode 1 is monochrome:
  the source is reduced to luminance and dithered onto a black/grey/white Gate Array ramp, using all four Mode 1 pens.
  `dither:` selects the scheme on every mode: `off` snaps to the nearest ink (Mode 1 substitutes a 4x4 Bayer dither
  because a hard threshold would throw the ramp away), `bayer2`/`bayer4`/`bayer8` and `noise` are ordered/noise
  patterns, and `floyd`, `atkinson`, `jarvis`, `stucki` and `sierra` are error-diffusion kernels. The ordered patterns
  keep the packed art smallest; error diffusion is smoother but produces larger blobs, so watch the four extra banks.
  The band uses the CPC screen's 4:3 physical proportions and is fitted to the mode's pixel grid, so the wide
  Mode 0 pixels and narrow Mode 2 pixels neither change the framing nor stretch the picture; the editor previews show
  the same physical aspect for every mode. An explicit `crop:` keeps its full width and re-centres the vertical window
  to that aspect (clamped to the source), so it is neither stretched nor cropped sideways. `art_rows` is 8, 10 or 12
  (default 12); Mode 2 also allows 14 or 16, which leave fewer rows for the text pane. Each band is stored as CPC
  screen bytes `[u8 ninks][u8 hardware inks][8 scanline chunks]`.
- **Text colours:** Mode 1 ignores `text_bg:`, `text_ink:` and `highlight_ink:` because its four pens are the
  monochrome ramp shared by the picture and text (the body and highlight both use white and the `>` cursor marks the
  selection). In Modes 0 and 2 palette entry 0 is the game's `text_bg:` (default black) because the title/text pane
  clears to pen 0; the last entry is `text_ink:` and the one before it `highlight_ink:` (Mode 2 uses the text ink for
  both). `tools/cpcart.py` resolves those tokens to Gate Array inks and forces them into their slots before
  quantising, so the runtime always shows the author's colours instead of the picture's dominant inks. The picture is
  quantised against the full palette and may use those entries too, so Mode 0 keeps 16 inks (13 image-derived +
  background + the two text inks) and Mode 2 keeps 2 (background + text). Changing any of the three rebakes every
  Mode 0/2 art blob, so rebuild the `.dsk`. The editor's target preview passes the same colours so it matches the
  build.
- **Storage:** compressed art blobs are packed into the 6128's extra 16K banks `BANK_4`..`BANK_7`, with `BANK_2`
  (0x8000, capped at 8K) as overflow. A music build packs the song blobs into the same four extra banks but leaves
  `BANK_2` free for the base-RAM workspaces, so art + music must fit 64K. The runtime pages through port 0x7F,
  decodes to 0xC000 and scatters the band to rows 1..`art_rows`. The art is cached by id (`PORT_KEEP_ART`): a scene
  that reuses the picture only clears the title/text pane, while an art change blanks every pen before decoding so the
  temporary bytes written into video RAM are not visible; the palette is restored after the band and pane have been
  cleared. The scene and inventory workspaces (`port_ws.asm`, `CPC_WS_BASE`) share one fixed buffer sized to the
  larger, and the song workspace follows it, all packed just below the firmware event blocks at `0xA600`. Because
  the item screen reuses the scene buffer, returning from it forces a full scene redraw
  (`PORT_INV_OVERWRITES_ART`).
- **Sound:** `# Game songs:` / per-scene `music:` PT3 modules play through z88dk's VT2 player from the firmware
  frame-flyback ISR. The module is ZX0-decoded into `SONG_WS_ADDR` (`SONG_WS_SIZE` bytes after decompression, above
  the scene/inventory buffer and below `0xA600`); the CRT heap is capped at `CPC_WS_BASE`, `BANK_2` stays free, and
  the map guard checks the linked BSS ends before the fixed workspaces. Press `P` to toggle music.
- **Options:** `mode`, `columns`, `art_rows`, `margin` (N 8x8-cell side borders; Mode 1's border is black, Modes 0/2 use
  `text_bg`), `dither`, and `menu: popup` (any mode; the default keeps pinned options). The dialog key is `SPACE`;
  `ENTER`/fire confirms.
- **Controls:** arrow keys or W/A/S/D move the cursor; Enter or the joystick fire button chooses (Space also chooses
  on the pinned layout). `P` toggles music. With `menu: popup`, up/down scrolls long scene text (left/right moves
  between highlighted words) and `SPACE` opens/closes the action dialog in every mode.
  Both CPC joystick ports work; the web emulator maps its arrow keys to port 0.
- **Build:** `zcc +cpc -subtype=dsk`; the internal file name is the fixed 8.3 `GAME` so emulators can auto-run it.
  Output `<slug>.dsk`.
- **Emulator:** CPCJS/Caprice32 WASM (`emulator/cpc`), auto-running `GAME`.

Key files: `tools/cpcart.py`, `src/cpc/plat_cpc.c`, `src/cpc/cpc_paging.asm`, `src/cpc/cpc_ink.asm`,
`src/cpc/font8_4bpp.h`, `build/port_ws.asm` (fixed scene/inventory workspace), `src/portable/core/music.c`.
