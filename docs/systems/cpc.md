# Amstrad CPC 6128

- **Display:** Mode 1 by default (320x200, four monochrome shades); Mode 0 (160px, 16 inks) and Mode 2 (640px, two
  inks) are selectable. Text uses 32, 40 or 62 columns on 25 rows; Mode 0 fits at most 40 (4px font for 32/40), while
  Modes 1/2 use the 8px font for 32/40 and the compact 4px font for 62. Mode 0 gives the text every row below the art
  and shows the options/items in a `SPACE`-key overlay dialog (the list scrolls with the cursor, Enter/fire confirms
  and `SPACE` closes; a long item description scrolls with up/down); Modes 1/2 keep the text pane with pinned options
  unless the system sets `menu: popup`, which gives them the same `SPACE`-key dialog.
- **Art:** `mode_width` x `8 * art_rows` (160/320/640 wide); Mode 1 is 320 x `8 * art_rows`. Mode 1 is monochrome:
  the source is reduced to luminance and ordered-dithered (4x4 Bayer) onto a black/grey/white Gate Array ramp,
  using all four Mode 1 pens; the regular pattern keeps the packed art small enough for the four extra banks.
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
  `BANK_2` free for the resident song workspace, so art + music must fit 64K. The runtime pages through port 0x7F,
  decodes to 0xC000 and scatters the band to rows 1..`art_rows`. The art is cached by id (`PORT_KEEP_ART`): a scene
  that reuses the picture only clears the title/text pane, while an art change blanks every pen before decoding so the
  temporary bytes written into video RAM are not visible; the palette is restored after the band and pane have been
  cleared.
- **Sound:** `# Game songs:` / per-scene `music:` PT3 modules play through z88dk's VT2 player from the firmware
  frame-flyback ISR. The module is ZX0-decoded into a fixed `0x9600` base-RAM workspace (`SONG_WS_SIZE` bytes after
  decompression); music builds cap the CRT heap at `0x9600`, keep `BANK_2` free, and check the linked BSS stays below
  the workspace. Press `P` to toggle music.
- **Options:** `mode`, `columns`, `art_rows`, and `menu: popup` (Modes 1/2; Mode 0 always uses the dialog).
  The dialog key is `SPACE`; `ENTER`/fire confirms.
- **Controls:** arrow keys or W/A/S/D move the cursor; Enter or the joystick fire button chooses (Space also chooses
  on the pinned Modes 1/2 layout). `P` toggles music. In Mode 0 up/down scrolls long scene text (left/right moves
  between highlighted words) and `SPACE` opens/closes the action dialog. Modes 1/2 use the same dialog when
  `menu: popup` is set.
  Both CPC joystick ports work; the web emulator maps its arrow keys to port 0.
- **Build:** `zcc +cpc -subtype=dsk`; the internal file name is the fixed 8.3 `GAME` so emulators can auto-run it.
  Output `<slug>.dsk`.
- **Emulator:** CPCJS/Caprice32 WASM (`emulator/cpc`), auto-running `GAME`.

Key files: `tools/cpcart.py`, `src/cpc/plat_cpc.c`, `src/cpc/cpc_paging.asm`, `src/cpc/cpc_ink.asm`,
`src/cpc/font8_4bpp.h`, `src/portable/core/music.c`.
