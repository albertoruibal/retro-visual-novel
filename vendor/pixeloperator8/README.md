# Pixel Operator Mono 8

`font8x8.bin` holds the 96 ASCII glyphs (U+0020..U+007F) from Pixel Operator Mono 8, eight bytes per glyph. Rows are
LSB-left (bit 0 is the leftmost pixel), matching the convention used by `tools/gbart.py` and `tools/gen_port.py`.

- Upstream: <https://www.dafont.com/pixel-operator.font>
- Archive: `https://dl.dafont.com/dl/?f=pixel_operator`
- File: `PixelOperatorMono8.ttf`, version 2018.10.04-1
- Designer: Jayvee Enaguas (HarvettFox96)
- Licence: Creative Commons Zero (CC0) 1.0, see `LICENSE.txt`

Hashes:

    PixelOperatorMono8.ttf  b627505e178c0c51b0ce7d432f2974fdc2064339f17fb5242b7237becad3c467
    font8x8.bin             c1f5401607350b532666894740c6c4aff412cc6e35a7b601e40156035f04ee07

`font8x8.bin` is generated from the TTF by `tools/make_font8.py`. The script renders every glyph at 8x scale, thresholds
each 8x8 block at 50% (the outlines are pixel-aligned), and writes the LSB-left rows. Run it in the editor container,
which has Pillow, then paste the printed `ACCENT_GLYPHS_8X8` block into `tools/gen_scenes.py`:

    docker exec retro-visual-novel-editor-1 sh -lc 'python3 tools/make_font8.py'

The accented glyphs (`Á Ñ á é í Ü ü ñ ó ú ¿`) are stored in `tools/gen_scenes.ACCENT_GLYPHS_8X8` under the same byte
slots as the ZX/CPC/portable text encoding, so all targets share one accent mapping. Pixel Operator Mono 8 is
monospaced with an 8-pixel advance, a 7-pixel ascent and a 1-pixel descent; the designed accented glyphs fit the 8x8
cell without clipping.
