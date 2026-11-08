/*
 * NES platform layer for the shared portable story engine.
 *
 * The PPU shows a 32x30 background-only screen.  The NES background pattern
 * table is 256 tiles (4KB), shared by the normal 96-glyph font (indices
 * 0..95) and up to 160 art tiles (96..255).  Highlighted text uses the same
 * font tiles with attribute palette 1; body text uses palette 0.  The art
 * band occupies nametable rows 2..art_rows+1 (row 0 title, row 1 blank); the
 * text pane starts at art_rows+2.  The even band start and height keep it
 * aligned with the PPU's 2x2-tile attribute quadrants.
 *
 * The cartridge is MMC1 (mapper 1): 32KB PRG with the story data resident,
 * 8KB PRG RAM at $6000 for the C workspaces, and one 8KB CHR ROM bank per art
 * (bank 0 is the boot bank with the font and blank tiles).
 *
 * Large redraws (art, pane clears) write VRAM directly with the NMI and
 * rendering off.  Text and attribute updates use the cc65 ppubuf ring buffer:
 * `nes_ppu_put` queues a byte and the library NMI flushes it during vblank
 * and resets the scroll.  Keeping text writes small avoids overrunning the
 * vblank window, and the scroll reset cannot be left stale.
 */
#include <nes.h>

#include "plat.h"
#include "port_data.h"

#define PPU_CTRL1 (*(volatile unsigned char *)0x2000)
#define PPU_CTRL2 (*(volatile unsigned char *)0x2001)
#define PPU_SCROLL (*(volatile unsigned char *)0x2005)
#define PPU_ADDR (*(volatile unsigned char *)0x2006)
#define PPU_DATA (*(volatile unsigned char *)0x2007)
#define JOYPAD0 (*(volatile unsigned char *)0x4016)

#ifndef NES_FONT_TILES
#define NES_FONT_TILES 96
#endif
#ifndef NES_ART_BASE
#define NES_ART_BASE 96
#endif

#define NT_BASE 0x2000
#define NT_ATTR 0x23C0

static unsigned char attr_shadow[64];
static unsigned char direct_mode;

extern void __cdecl__ nes_ppu_put(unsigned char value, unsigned int addr);
extern void port_unpack(const void *src, void *dst);
extern void nes_mmc1_init(void);
extern void nes_chr_bank(unsigned char bank);

static void ppu_addr(unsigned int addr)
{
    PPU_ADDR = (unsigned char)(addr >> 8);
    PPU_ADDR = (unsigned char)addr;
}

static void ppu_write(unsigned char value)
{
    PPU_DATA = value;
}

static void begin_direct(void)
{
    PPU_CTRL1 = 0;         /* NMI off while the VRAM is written directly */
    PPU_CTRL2 = 0;
    direct_mode = 1;
}

static void end_direct(void)
{
    direct_mode = 0;
    ppu_addr(0x2000);
    PPU_SCROLL = 0;
    PPU_SCROLL = 0;
    PPU_CTRL2 = 0x0A;      /* background on, sprites off, no clipping */
    PPU_CTRL1 = 0x80;      /* NMI on: its handler flushes and resets scroll */
}

static void write_attr(unsigned char index)
{
    if (direct_mode) {
        ppu_addr(NT_ATTR + index);
        ppu_write(attr_shadow[index]);
    } else {
        nes_ppu_put(attr_shadow[index], (unsigned int)NT_ATTR + index);
    }
}

/* Set the 2-bit palette for the 2x2-tile quadrant containing (row, col). */
static void set_cell_attr(unsigned char row, unsigned char col,
                          unsigned char palette)
{
    unsigned char by, bx, quad, index, shift;
    if (row >= PLAT_ROWS || col >= PORT_COLS)
        return;
    by = (unsigned char)(row >> 2);
    bx = (unsigned char)(col >> 2);
    index = (unsigned char)(by * 8 + bx);
    quad = (unsigned char)(((row & 2) ? 2 : 0) | ((col & 2) ? 1 : 0));
    shift = (unsigned char)(quad * 2);
    {
        unsigned char value = (unsigned char)(
            (attr_shadow[index] & (unsigned char)~(3u << shift))
            | (unsigned char)((palette & 0x03) << shift));
        if (value != attr_shadow[index]) {
            attr_shadow[index] = value;
            write_attr(index);
        }
    }
}

static void clear_row_now(unsigned char row)
{
    unsigned char i;
    ppu_addr(NT_BASE + (unsigned int)row * PORT_COLS);
    for (i = 0; i < PORT_COLS; i++)
        ppu_write(0);
    for (i = 0; i < PORT_COLS; i++)
        set_cell_attr(row, i, 0);
}

void plat_init(void)
{
    unsigned int i;

    begin_direct();
    nes_mmc1_init();

    /* Palette 0 = body text, palette 1 = highlighted text, palettes 2/3 =
       art (background only until the first art is drawn). */
    ppu_addr(0x3F00);
    ppu_write(PORT_TEXT_BG);
    ppu_write(PORT_TEXT_INK);
    ppu_write(PORT_TEXT_INK);
    ppu_write(PORT_TEXT_INK);
    ppu_write(PORT_TEXT_BG);
    ppu_write(PORT_HIGHLIGHT_INK);
    ppu_write(PORT_HIGHLIGHT_INK);
    ppu_write(PORT_HIGHLIGHT_INK);
    for (i = 0; i < 8; i++)
        ppu_write(PORT_TEXT_BG);

    for (i = 0; i < 64; i++)
        attr_shadow[i] = 0;
    ppu_addr(NT_BASE);
    for (i = 0; i < 960; i++)
        ppu_write(0);
    ppu_addr(NT_ATTR);
    for (i = 0; i < 64; i++)
        ppu_write(0);

    nes_chr_bank(0);
    end_direct();
}

void plat_clear(void)
{
    unsigned int i;
    begin_direct();
    for (i = 0; i < 64; i++)
        attr_shadow[i] = 0;
    ppu_addr(NT_BASE);
    for (i = 0; i < 960; i++)
        ppu_write(0);
    ppu_addr(NT_ATTR);
    for (i = 0; i < 64; i++)
        ppu_write(0);
    end_direct();
}

void plat_clear_row(unsigned char row)
{
    if (row >= PLAT_ROWS)
        return;
    begin_direct();
    clear_row_now(row);
    end_direct();
}

void plat_clear_pane(void)
{
    unsigned char row;
    begin_direct();
    for (row = PORT_TEXT_TOP; row < PLAT_ROWS; row++)
        clear_row_now(row);
    end_direct();
}

void plat_clear_text(void)
{
    unsigned char row;
    begin_direct();
    clear_row_now(0);
    for (row = PORT_TEXT_TOP; row < PLAT_ROWS; row++)
        clear_row_now(row);
    end_direct();
}

void plat_text_at(unsigned char row, unsigned char col, const char *s,
                  unsigned char color)
{
    unsigned char i = 0;
    unsigned char palette = (color == PLAT_COLOR_SEL) ? 1 : 0;
    if (row >= PLAT_ROWS)
        return;
    while (s[i] && col + i < PORT_COLS) {
        unsigned char ch = (unsigned char)s[i];
        if (ch < 32 || ch > 127)
            ch = 32;
        nes_ppu_put((unsigned char)(ch - 32),
                    (unsigned int)NT_BASE
                    + (unsigned int)row * PORT_COLS + col + i);
        i++;
    }
    for (i = 0; s[i] && col + i < PORT_COLS; i++)
        set_cell_attr(row, (unsigned char)(col + i), palette);
}

void plat_text_color(unsigned char row, unsigned char col, const char *s,
                     unsigned char color)
{
    plat_text_at(row, col, s, color);
}

void plat_text(unsigned char row, unsigned char col, const char *s)
{
    plat_text_at(row, col, s, PLAT_COLOR_BODY);
}

void plat_draw_art(unsigned char id)
{
    const unsigned char *p, *map, *attrs;
    unsigned int ntiles, i;
    unsigned char npal, k;

    if (id >= N_ART)
        return;
    p = port_art_data + port_art_off[id];
    ntiles = (unsigned int)p[0] | ((unsigned int)p[1] << 8);
    npal = p[2];
    map = p + 3 + (unsigned int)npal * 4;
    attrs = map + (unsigned int)PORT_COLS * PORT_ART_ROWS * 2;
    (void)ntiles;

    begin_direct();
    nes_chr_bank(port_art_bank[id]);
    ppu_addr(0x3F08);
    for (k = 0; k < 8; k++)
        ppu_write(p[3 + k]);
    ppu_addr(NT_BASE + (unsigned int)PORT_ART_TOP * PORT_COLS);
    for (i = 0; i < (unsigned int)PORT_COLS * PORT_ART_ROWS; i++) {
        unsigned int idx = (unsigned int)map[i * 2]
            | ((unsigned int)map[i * 2 + 1] << 8);
        ppu_write((unsigned char)(NES_ART_BASE + idx));
    }
    ppu_addr(NT_ATTR);
    for (i = 0; i < 64; i++) {
        attr_shadow[i] = attrs[i];
        ppu_write(attrs[i]);
    }
    end_direct();
}

void plat_load(unsigned char bank, unsigned short off, void *dst,
               unsigned char kind)
{
    (void)bank;
    if (kind == PLAT_LOAD_INV)
        port_unpack(port_inv_data, dst);
    else
        port_unpack(port_scene_data + off, dst);
}

void plat_set_bank(unsigned char bank)
{
    (void)bank;
}

void plat_boot(void)
{
}

void plat_scene_entered(unsigned char id)
{
#if N_SONGS > 0
    set_music(scene_song[id]);
#else
    (void)id;
#endif
}

static unsigned char read_pad(void)
{
    unsigned char i, value = 0;
    JOYPAD0 = 1;
    JOYPAD0 = 0;
    for (i = 0; i < 8; i++)
        value = (unsigned char)((value << 1) | (JOYPAD0 & 0x01));
    return value;
}

unsigned char plat_read_key(void)
{
    unsigned char pad = read_pad();
    if (pad & 0x80)          /* A */
        return 3;
    if (pad & (0x40 | 0x20)) /* B or Select */
        return PORT_KEY_MENU;
    if (pad & 0x08)          /* Up */
        return 1;
    if (pad & 0x04)          /* Down */
        return 2;
    if (pad & 0x02)          /* Left */
        return 6;
    if (pad & 0x01)          /* Right */
        return 7;
    if (pad & 0x10) {        /* Start: music toggle */
#if N_SONGS > 0
        toggle_music();
#endif
        return 0;
    }
    return 0;
}

void plat_wait_release(void)
{
    unsigned int i;
    while (read_pad()) {
        for (i = 0; i < 64; i++)
            ;
    }
}
