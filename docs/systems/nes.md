# Nintendo Entertainment System

- **Display:** 32 x 30 background tiles. The scene title is on row 0, row 1 is blank, the art band occupies rows
  2..`art_rows + 1`, and the text pane runs from row `art_rows + 2` through row 29. `art_rows` is 6, 8 or 10 (default
  10). The even band start and height keep the band aligned with the PPU's 2x2-tile attribute quadrants. Options and
  held items live in the action dialog (A confirms, B or Select opens/closes it); there is no permanent inventory row
  and long text scrolls with the D-pad.
- **Pattern table:** the NES background pattern table is only 256 tiles (4KB), so the normal 96-glyph font (indices
  0..95) and up to 160 art tiles (96..255) share it. Highlighted text does not use a second font: the attribute
  palette selects palette 0 (body) or palette 1 (highlight) for the 2x2-tile quadrant. Palettes 2 and 3 are the art
  palettes. The highlight palette is applied per 2x2-tile quadrant, so adjacent text rows can share it; the `>` marker
  is the reliable selection indicator (and keeps working if the palette is overwritten by the neighbouring body
  text).
- **Colours:** the PPU has four background palettes of four colours; entry 0 is the shared universal background,
  fixed to the game's `text_bg:`. Palette 0 is body text, palette 1 is highlighted text and palettes 2/3 carry three
  art colours each. `tools/nesart.py` clusters each art's 2x2-tile block palettes into the two art palettes and emits
  the full 64-byte nametable attribute table.
- **Art:** `tools/nesart.py` fits the source to 256 x `8 * art_rows`, preprocesses and quantises it to the NES
  palette, assigns a palette per 2x2-tile block and deduplicates the 2bpp tiles into at most 160 patterns. The blob
  (uncompressed, in PRG ROM) is `[u16 ntiles][u8 npalettes][palettes][u16 map][attrs]`; tile patterns live in the
  art's 8KB CHR ROM bank after the 96 font tiles. The editor preview and the ROM use the same converter.
- **Storage/memory:** an MMC1 (mapper 1) cartridge with 32KB PRG and 8KB battery WRAM at `$6000`. The story data
  (scenes/inventory compressed with ZX0, plus the art maps/attributes/palettes) is resident in the 32KB PRG; the C
  workspaces and the C stack live in the 8KB PRG RAM. `src/6502/zx0.c` decodes the scene/inventory blobs.
  `tools/gen_port.py --nes` writes `build/port_data.c/h` and `build/port_nes_chr.bin`; `tools/targets/nes.py` links the
  code, patches the iNES header (mapper 1, CHR bank count) and appends the generated CHR banks.
- **CHR banks:** bank 0 is the boot bank (font and blank tiles); each art gets one 8KB CHR bank (`port_art_bank[id]`).
  MMC1 8KB CHR mode addresses at most 16 banks, so a game may have at most 15 arts. `src/nes/nes_mmc1.s` performs the
  serial MMC1 register writes.
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
  `art_rows` if the linker overflows); highlights use the coarser 2x2-tile attribute granularity.

Key files: `tools/targets/nes.py`, `tools/nesart.py`, `src/nes/plat_nes.c`, `src/nes/nes_mmc1.s`, `src/6502/zx0.c`,
`tools/gen_port.py`.
