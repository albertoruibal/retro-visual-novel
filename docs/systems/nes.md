# Nintendo Entertainment System

- **Display:** 32 x 30 background tiles. The scene title is on row 0, row 1 is blank, the art band occupies rows
  2..`art_rows + 1`, and the text pane runs from row `art_rows + 2` through row 29. `art_rows` is 6, 8 or 10 (default
  10). The even band start and height keep the band aligned with the PPU's 2x2-tile attribute quadrants. Options and
  held items live in the action dialog (A confirms, B or Select opens/closes it); there is no permanent inventory row
  and long text scrolls with the D-pad.
- **Pattern tables:** every 8KB CHR bank has two 4KB pattern tables. Table 0 is used for the title/art band and
  holds the normal 96-glyph font (0..95) plus up to 160 art tiles (96..255). Table 1 is used for the text pane and
  holds the same normal font plus a highlight copy at 96..191. Text attributes always select palette 0, whose entry 2
  is the highlight colour; normal glyphs use pixel value 1 and highlighted glyphs pixel value 2, so a selected word or
  entry cannot tint the adjacent row. The custom NMI switches the PPU background table from 0 to 1 after the art band,
  using a generated delay table that compensates for the ppubuf queue length.
- **Colours:** the PPU has four background palettes of four colours; entry 0 is the shared universal background,
  fixed to the game's `text_bg:`. Palette 0 is body text (`entry 1 = text_ink`, `entry 2 = highlight_ink`), palette 1
  is unused by text and palettes 2/3 carry three art colours each. `tools/nesart.py` clusters each art's 2x2-tile
  block palettes into the two art palettes and emits the full 64-byte nametable attribute table.
- **Art:** `tools/nesart.py` fits the source to 256 x `8 * art_rows`, preprocesses and quantises it to the NES
  palette, assigns a palette per 2x2-tile block and deduplicates the 2bpp tiles into at most 160 patterns. The blob
  (uncompressed, in PRG ROM) is `[u16 ntiles][u8 npalettes][palettes][u16 map][attrs]`; tile patterns live in table 0
  of the art's 8KB CHR ROM bank after the 96 font tiles. The editor preview and the ROM use the same converter.
- **Storage/memory:** an MMC1 (mapper 1) cartridge with 32KB PRG and 8KB battery WRAM at `$6000`. The story data
  (scenes/inventory compressed with ZX0, plus the art maps/attributes/palettes) is resident in the 32KB PRG; the C
  workspaces and the C stack live in the 8KB PRG RAM. `src/6502/zx0.c` decodes the scene/inventory blobs.
  `tools/gen_port.py --nes` writes `build/port_data.c/h` and `build/port_nes_chr.bin`; `tools/targets/nes.py` links the
  code, patches the iNES header (mapper 1, CHR bank count), installs the custom NMI vector and appends the generated
  CHR banks.
- **CHR banks:** bank 0 is the boot bank (font, highlight copy and blank tiles); each art gets one 8KB CHR bank
  (`port_art_bank[id]`). MMC1 8KB CHR mode addresses at most 16 banks, so a game may have at most 15 arts.
  `src/nes/nes_mmc1.s` performs the serial MMC1 register writes.
- **Controls:** D-pad moves/scrolls; A confirms; B or Select opens/closes the action dialog. Start toggles music when
  a NES music player is added.
- **Sound:** not implemented yet. The NES build ignores the game's `songs:`/`music:` settings; other targets still
  play them.
- **Build:** `cl65 -t nes -Oirs ...`, output `<slug>.nes`; cc65 is required (z88dk has no NES target). The editor
  Docker image contains cc65 (V2.18, whose `ppubuf` API `src/nes/nes_ppu.s` wraps); on a desktop install a matching
  cc65 and point the **Build toolchain** settings card at it.
- **Emulator:** the editor's Emulator tab runs the `.nes` in a pinned EmulatorJS build of FCEUmm (MMC1-capable). Its
  default keyboard mapping is arrows = D-pad, `Z` = A (confirm), `X` = B (open/close the dialog), `V` = Select and
  `Enter` = Start; remap it in the emulator's Control Settings. The ROM also runs in FCEUX, Mesen, Nestopia or another
  MMC1-capable NES emulator.
- **Limitations:** no boot-password screen; the 32KB PRG is the main size limit (shorten the story or reduce
  `art_rows` if the linker overflows). The art/text pattern-table split is timed from the NMI; unusual mid-frame
  rendering changes would need the delay table retuned.

Key files: `tools/targets/nes.py`, `tools/nesart.py`, `src/nes/plat_nes.c`, `src/nes/nes_mmc1.s`, `src/6502/zx0.c`,
`tools/gen_port.py`.
