# Sega Master System

- **Black and white:** `mono: on` dithers the picture to white-on-black and forces white text.
- **Display:** 256 x `8 * art_rows` picture over a 24-row text screen; 16 colours from the VDP background palette.
  `art_rows` is 8, 10 or 12 (default 12). The text uses every row below the art (title row 0, body rows
  `art_rows+1`..23) and scrolls up/down when the wrapped text exceeds that pane; left/right moves between highlighted
  words (or scrolls when a scene has none). Button 1 opens an overlay dialog listing the scene options and the held
  items (items are prefixed `*`); the D-pad scrolls, button 2 confirms and button 1 closes it. A long item description
  also scrolls with up/down. There is no permanent inventory row.
- **Tiles:** the runtime uploads 96 font glyphs plus two scroll-arrow tiles at VRAM patterns 0..97. The font is the
  shared CC0 8x8 Pixel Operator Mono 8 (see `vendor/pixeloperator8/`), emitted as `build/port_font8.h` at build time. Art uses
  planar 4bpp 8x8 tiles and is capped at 352 unique tiles; extra cells reuse the nearest tile.
- **Conversion:** `tools/smsart.py` shares one converter between the editor preview and the build. An explicit `crop:`
  keeps its full width and re-centres the vertical window to the band aspect, so the picture is not stretched. Each art
  is stored raw in its own Sega-mapper 16K ROM bank as `[u16 ntiles][u8 palette[16]][u16 map][tiles]`. The
  `## sms dither:` option accepts the full list; palette selection stays undithered and only pixel assignment uses
  the chosen scheme.
- **Text colours:** palette entry 0 is the game's `text_bg:` (default black) and entry 1 its `text_ink:`; the sprite
  palette's entry 0 is the same background and entry 1 its `highlight_ink:` (the `0x0800` attribute selects it for
  selected options/words). All snap to the nearest SMS CRAM colour. The art uses the remaining 14 palette entries,
  though the picture may also use the reserved ones. Changing any of the three rebakes every art blob, so rebuild the
  `.sms`.
- **Storage:** scene/inventory blobs are ZX0-compressed into the main ROM; art banks start at `BANK_02` and are selected
  through the mapper.
- **Sound:** PT3 songs are converted at build time to an SN76489 register stream by `tools/smsmusic.py` and played by
  z88dk's PSGlib through a 50 Hz IM1 handler (`src/sms/sms_music.asm`). AY tone channels A/B/C map to the SN76489's
  three tone channels; noise lands on channel 3; the AY hardware envelope and low notes are approximated. The NTSC
  60 Hz vblank is divided down to 50 Hz, while a PAL console calls PSGlib every frame. The song stream is ZX0-packed
  into a data bank after the art and decoded into `SONG_WS_SIZE` bytes of RAM; PAUSE toggles music. The converter
  uses the pinned spectrumizer PT3 decoder, so a module with unsupported PT3 commands fails the build with a clear
  message instead of playing incorrectly.
- **Options:** `art_rows`, `margin` (N 8x8-cell side borders, filled with `text_bg`), `dither` (full list). Text
  width is fixed at 30 columns; dialog labels wrap at 28.
- **Controls:** D-pad up/down scrolls long text, or moves between highlighted words when it fits; left/right moves
  between highlighted words. Button 2 confirms and button 1 opens/closes the options/items dialog.
- **Build:** `zcc +sms -clib=new` plus `build/port_banks.asm` (and `port_song.asm` + `-pragma-define:CRT_ENABLE_RST=128`
  for music builds); output `<slug>.sms`.
- **Emulator:** EmulatorJS with the smsplus core (`emulator/sms`).

Key files: `tools/smsart.py`, `tools/smsmusic.py`, `src/sms/plat_sms.c`, `src/sms/sms_music.asm`,
`src/portable/core/`, `vendor/pixeloperator8/`.
