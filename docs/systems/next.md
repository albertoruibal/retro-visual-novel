# ZX Spectrum Next

The Next target is a native `+zxn` build. It uses the same portable story engine
as the other targets, a ULA text layer, **Layer 2** 256-colour art and the
Next's AY player. The output is a NextZXOS `.nex` executable.

- **Display:** 256 x 192 Layer 2 mode (8bpp), with the picture clipped to
  character rows `1..art_rows`. The scene title is on ULA row 0, text on rows
  `art_rows+1..22`, and the inventory band on row 23. Text is 64 columns, 4x8
  glyphs.
- **Art:** each art is a 256 x `8*art_rows` band in a 256-colour palette. The
  palette is 9-bit RGB333; the converter uses Pillow median-cut (or a fixed
  16-colour palette when `palette: spectrum` is selected). `crop:` and the
  shared colour controls behave as on the ZX target. `dither: off` is a hard
  snap; any other dither value uses Floyd-Steinberg. `match:` does not apply to
  the 256-colour quantiser.
- **Storage:** scene, inventory and song blobs are ZX0-compressed in 16K Next
  banks. Each art reserves three 16K banks (the band starts at Layer 2 row 8);
  palettes are packed 32 per bank. The build fails if the data needs bank 112
  or more, or if the lower-RAM staging/song window at `0x6000` overflows.
- **Sound:** the shared AY VT2/PT3 player, driven by a small IM1 handler.
- **Options:** `art_rows` (even 8..16, default 10), `menu: popup`, `title_ink`.
  The same `# Game` text colours, `carry`, password, songs and item settings
  apply.
- **Build:** `python3 tools/build.py build demo-game next`; the output is
  `<slug>.nex` in the game folder.
- **Emulator:** no emulator is bundled. Run the `.nex` with an installed
  ZEsarUX 13.0 (TBBlue machine):

      python3 tools/build.py run demo-game next

  `tools/spectrum.py` also accepts `run <game>.nex` and uses ZEsarUX's
  `--machine TBBlue` path. The editor's Emulator tab lists only targets with a
  bundled web runtime; ZX Next is intentionally not listed. The editor Docker
  image has no ZEsarUX, so run the built `.nex` from the host (or point
  `$ZESARUX` at an installed binary).

## Memory map

| Region | Contents |
|---|---|
| `0x4000-0x7FFF` | ULA screen (bank 5); `0x6000-0x7FFF` is the staging/song window |
| `0x8000-0xBFFF` | resident code, data and BSS |
| `0xC000-0xCFFF` | bank 0: CRT data and AY player variables |
| `0xE000-0xFFFF` | bank 0 upper half: `scene_ws` and `inv_ws` |
| banks 8..15 | Layer 2 palettes |
| banks 16+ | Layer 2 art (three banks per art), then the resident font bank, then compressed scenes/inventory/songs |

`paged_next_unpack(bank, src, dst)` maps the source 16K bank over `0xC000`,
copies the length-prefixed ZX0 stream into `_stage_ws`, restores bank 0, then
decodes into the caller's workspace with interrupts enabled.
