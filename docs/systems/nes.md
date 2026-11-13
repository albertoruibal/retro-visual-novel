# Nintendo Entertainment System

- **Black and white:** `mono: on` dithers the picture to white-on-black and forces white text.
- **Display:** 32 x 30 background tiles. Row 0 is blank, the scene title is on row 1, the art band occupies rows
  2..`art_rows + 1`, and the text pane runs from row `art_rows + 2` through row 29. (Row 1 keeps the title out of the
  8-scanline top overscan that emulators such as FCEUmm crop by default.) `art_rows` is 8, 10 or 12 (default
  10). The even band start and height keep the band aligned with the PPU's 2x2-tile attribute quadrants. Options and
  held items live in the action dialog (A confirms, B or Select opens/closes it); there is no permanent inventory row
  and long text scrolls with the D-pad.
- **Pattern tables:** every 8KB CHR bank has two 4KB pattern tables. Table 0 is used for the title/art band and
  holds the normal 96-glyph font (0..95) plus up to 160 art tiles (96..255). Table 1 is used for the text pane and
  holds the same normal font plus a highlight copy at 96..191. Text attributes always select palette 0, whose entry 2
  is the highlight colour; normal glyphs use pixel value 1 and highlighted glyphs pixel value 2, so a selected word or
  entry cannot tint the adjacent row. The custom NMI switches the PPU background table from 0 to 1 in the last art
  scanline's HBlank, using a generated delay table that accounts for the exact ppubuf flush length. A locked menu
  update defers the flush to the next frame, writing both selection rows atomically. Direct VRAM redraws force blank
  but keep the NMI running: the handler skips the PPU while the main thread owns it, still ticks the audio, and
  re-enables rendering at the next vblank (never mid-frame, which would show the top of the nametable on the bottom
  scanlines). A following redraw cancels the deferred re-enable, so the art and pane updates share one blank.
- **Colours:** the PPU has four background palettes of four colours; entry 0 is the shared universal background,
  fixed to the game's `text_bg:`. Palette 0 is body text (`entry 1 = text_ink`, `entry 2 = highlight_ink`) and
  palettes 1/2/3 carry three art colours each, for up to ten colours including the shared background.
  `tools/nesart.py` selects each art's three palettes from distinct NES colours by minimising the per-block
  quantization error and emits the full 64-byte nametable attribute table.
- **Art:** `tools/nesart.py` fits the source to 256 x `8 * art_rows`, preprocesses and quantises it to the NES
  palette, assigns one of the three art palettes per 2x2-tile block and deduplicates the 2bpp tiles into at most 160
  patterns. The `## nes dither:` option accepts the full list and dithers between each block's four colours; the
  block palettes are still chosen from the undithered image. The blob is
  `[u16 ntiles][u8 npalettes][palettes][u16 map][attrs]`, ZX0-compressed in bank 0; `plat_draw_art()` decodes it
  into a small RAM workspace before drawing. Tile patterns live in table 0 of the art's 8KB CHR ROM bank after the
  96 font tiles. `margin:` adds N 8x8-cell borders on the left and right, filled with `text_bg`; the picture is
  scaled to the inner width with its aspect preserved. The editor preview and the ROM use the same converter.
- **Storage/memory:** an MMC1 (mapper 1) cartridge with banked PRG and 8KB battery WRAM at `$6000`. The custom
  `src/nes/nes.cfg` puts all code, the NMI and the vector table in the **last** 16KB PRG bank (MMC1 mode 3 fixes it at
  `$C000-$FFFF`), and uses the switchable bank 0 at `$8000-$BFFF` for the ZX0-compressed scenes/inventory and art
  blobs. Converted song streams are densely packed into the PRG banks between bank 0 and the fixed bank, then unused
  banks pad the PRG count to a power of two; the iNES PRG count includes them. The layout supports up to 16 PRG banks
  (14 song banks). The C workspaces and BSS live in the 8KB PRG RAM; `src/6502/zx0.c` decodes scenes, inventory and
  art. `tools/gen_port.py --nes` writes `build/port_data.c/h`, `build/port_nes_chr.bin` and
  `build/port_nes_song.bin`; `tools/targets/nes.py` links the code, merges the banks, patches the iNES header
  (mapper 1, PRG/CHR counts), installs the custom NMI vector and appends the generated CHR banks.
- **CHR banks:** bank 0 is the boot bank (font, highlight copy and blank tiles); each art gets one 8KB CHR bank
  (`port_art_bank[id]`). MMC1 8KB CHR mode addresses at most 16 banks, so a game may have at most 15 arts.
  `src/nes/nes_mmc1.s` performs the serial MMC1 register writes.
- **Controls:** D-pad moves/scrolls; A confirms; B or Select opens/closes the action dialog; Start toggles music.
- **Sound:** PT3 songs are converted at build time by `tools/nesmusic.py` to a NES APU register stream. AY tone
  channels A/B map to pulse 1/2, AY channel C to the triangle (on/off; it has no volume control) and AY noise to the
  noise channel; the AY hardware envelope is approximated per frame and low notes are folded up until they fit the
  11-bit timer. A stream is raw in the PRG banks and read directly by `src/nes/nes_audio_tick.s` from the NMI, which
  divides the ~60Hz frame rate down to the stream's 50Hz. The song reader briefly maps the current song bank at
  `$8000` and restores bank 0 before returning. The NMI tick keeps running while a direct VRAM redraw has rendering
  off, so a scene change does not interrupt the song. The converter uses the pinned spectrumizer PT3 decoder, so an
  unsupported module fails the build with a clear message.
- **UI sounds:** the shared engine emits `plat_sfx()` calls for cursor moves, confirmations, backing out, item
  pickups/drops and blocked moves. On the NES a short pulse-2 sequence is overlaid on the music by the same NMI tick;
  the music's pulse-2 registers are shadowed, skipped while the SFX owns the channel, and restored when it ends.
  Other targets compile the SFX calls away.
- **Build:** `cl65 -t nes -C src/nes/nes.cfg -Oirs ...`, output `<slug>.nes`; cc65 is required (z88dk has no NES
  target). The editor Docker image contains cc65 (V2.18, whose `ppubuf` API `src/nes/nes_ppu.s` wraps); on a desktop
  install a matching cc65 and point the **Build toolchain** settings card at it.
- **Emulator:** the editor's Emulator tab runs the `.nes` in a pinned EmulatorJS build of FCEUmm (MMC1-capable). Its
  default keyboard mapping is arrows = D-pad, `Z` = A (confirm), `X` = B (open/close the dialog), `V` = Select and
  `Enter` = Start; remap it in the emulator's Control Settings. The ROM also runs in FCEUX, Mesen, Nestopia or another
  MMC1-capable NES emulator.
- **Limitations:** no boot-password screen. Story/inventory/art must fit the 16KB switchable bank; songs use the
  extra banks, up to 14 of them (MMC1 addresses 16 16KB PRG banks total). The fixed code bank has little headroom, so
  link-map guards reject an overflow. The art/text pattern-table split is timed from the NMI; unusual mid-frame
  rendering changes would need the delay table retuned. The 50Hz music stream is divided from the NTSC ~60Hz rate;
  PAL timing is not corrected.

Key files: `tools/targets/nes.py`, `tools/nesart.py`, `tools/nesmusic.py`, `src/nes/plat_nes.c`, `src/nes/nes_mmc1.s`,
`src/nes/nes_audio_tick.s`, `src/nes/nes_music.c`, `src/nes/nes_sfx.c`, `src/nes/nes.cfg`, `src/6502/zx0.c`,
`tools/gen_port.py`.
