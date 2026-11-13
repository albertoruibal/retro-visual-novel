/*
 * Nintendo Game Boy Color (CGB) platform layer.
 *
 * The 160x144 background is a 20x18 tile map in 0x9800.  Font tiles occupy
 * 0..95, art tiles 96..253 and the two scroll arrows 254/255, so LCDC bit 4
 * selects the unsigned 0x8000 pattern table.  On CGB each map cell also has an
 * attribute byte in VRAM bank 1 selecting one of eight four-colour background
 * palettes; palettes 6/7 are the body and highlight text palettes and the art
 * uses 0..5.  The cartridge is CGB-enhanced, so the same code runs on a DMG:
 * palette and attribute writes are skipped and BGP provides four shades.
 *
 * The portable metadata stays in bank 0; scene/inventory blobs start at bank 1
 * and art follows.  VRAM is written directly (one byte at a time, waiting for
 * HBlank/VBlank) by gb_vram.asm; this avoids the GBDK tile helpers and keeps the
 * bank-switched copy paths under our own calling convention. The target is
 * built with SDCC.
 */
#include <gb/gb.h>
#include "plat.h"
#include "port_data.h"
#include "port_font2.h"

#define GB_MAP_ROWS PLAT_ROWS
#define GB_ARROW_TILES 254
#define GB_MAP 0x9800
#define GB_TILES 0x8000

static const unsigned char scroll_arrows[32] = {
    0x18, 0x18, 0x3C, 0x3C, 0x7E, 0x7E, 0xFF, 0xFF,
    0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00, 0x00,
    0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0xFF, 0xFF,
    0x7E, 0x7E, 0x3C, 0x3C, 0x18, 0x18, 0x00, 0x00,
};

static unsigned char blank_row[PORT_COLS];
static unsigned char blank_attr[PORT_COLS];
static unsigned short text_pal[8];

extern void gb_vram_copy(unsigned char *dst, const unsigned char *src,
                         unsigned int n) __smallc;
extern void gb_music_vbl(void) NONBANKED;

unsigned char port_bank_reg;

void plat_set_bank(unsigned char bank) __z88dk_fastcall
{
    port_bank_reg = bank;
    #asm
    ld a,(_port_bank_reg)
    ld (0x2000),a
    #endasm
}

static unsigned char gb_is_cgb(void)
{
    return _cpu == CGB_TYPE;
}

static void gb_clear_row(unsigned char row)
{
    gb_vram_copy((unsigned char *)(GB_MAP + (unsigned int)row * 32),
                 blank_row, PORT_COLS);
    if (gb_is_cgb()) {
        VBK_REG = 1;
        gb_vram_copy((unsigned char *)(GB_MAP + (unsigned int)row * 32),
                     blank_attr, PORT_COLS);
        VBK_REG = 0;
    }
}

void plat_init(void)
{
    unsigned char row, col;
    LCDC_REG = 0x90;              /* LCD off, BG 0x9800, tiles 0x8000 */
    BGP_REG = 0xE4;
    SCY_REG = 0;
    SCX_REG = 0;
    for (col = 0; col < PORT_COLS; col++)
        blank_attr[col] = GB_TEXT_PAL;
    if (gb_is_cgb()) {
        VBK_REG = 0;
        for (col = 0; col < 8; col++)
            text_pal[col] = gb_text_palette[col];
        set_bkg_palette(GB_TEXT_PAL, 2, text_pal);
    }
    gb_vram_copy((unsigned char *)GB_TILES, port_font2, sizeof(port_font2));
    gb_vram_copy((unsigned char *)(GB_TILES + GB_ARROW_TILES * 16),
              scroll_arrows, sizeof(scroll_arrows));
    for (row = 0; row < GB_MAP_ROWS; row++)
        gb_clear_row(row);
    LCDC_REG = 0x91;              /* LCD + background on */
    disable_interrupts();
    add_VBL(gb_music_vbl);
    enable_interrupts();
}

void plat_clear(void)
{
    unsigned char row;
    for (row = 0; row < GB_MAP_ROWS; row++)
        gb_clear_row(row);
}

void plat_clear_pane(void)
{
    unsigned char row;
    for (row = PORT_TEXT_TOP; row < GB_MAP_ROWS; row++)
        gb_clear_row(row);
}

void plat_text_at(unsigned char row, unsigned char col, const char *s,
                  unsigned char color)
{
    unsigned char tiles[PORT_COLS];
    unsigned char attrs[PORT_COLS];
    unsigned char palette = (color == PLAT_COLOR_SEL) ? GB_TEXT_SEL_PAL
                                                      : GB_TEXT_PAL;
    unsigned char n = 0;
    if (row >= GB_MAP_ROWS)
        return;
    while (s[n] && col + n < PORT_COLS) {
        unsigned char c = (unsigned char)s[n];
        if (c == 1)
            tiles[n] = GB_ARROW_TILES;
        else if (c == 2)
            tiles[n] = (unsigned char)(GB_ARROW_TILES + 1);
        else
            tiles[n] = (c >= 32 && c < 128) ? (unsigned char)(c - 32) : 0;
        attrs[n] = palette;
        n++;
    }
    if (n) {
        if (gb_is_cgb())
            VBK_REG = 0;
        gb_vram_copy((unsigned char *)(GB_MAP + row * 32 + col), tiles, n);
        if (gb_is_cgb()) {
            VBK_REG = 1;
            gb_vram_copy((unsigned char *)(GB_MAP + row * 32 + col),
                         attrs, n);
            VBK_REG = 0;
        }
    }
}

void plat_text_color(unsigned char row, unsigned char col, const char *s,
                     unsigned char color)
{
    plat_text_at(row, col, s, color);
}

void plat_text(unsigned char row, unsigned char col, const char *s)
{
    plat_text_at(row, col, s, 0);
}

void plat_draw_art(unsigned char id)
{
#if HAVE_ART
    unsigned char bank, row, ntiles, npals, *p, *map, *attr;
    unsigned int off;
    unsigned short *pals;
    if (id >= N_ART)
        return;
    plat_set_bank(PORT_DATA_BANK);
    bank = port_art_bank[id];
    off = port_art_off[id];
    plat_set_bank(bank);
    p = (unsigned char *)(0x4000 + off);
    ntiles = p[0];
    npals = p[1];
    if (!ntiles) {
        for (row = 0; row < PORT_ART_ROWS; row++)
            plat_clear_row((unsigned char)(row + 1));
        plat_set_bank(PORT_DATA_BANK);
        return;
    }
    if (npals > 6)
        npals = 6;
    pals = (unsigned short *)(p + 2);
    map = p + 2 + (unsigned int)npals * 8 + (unsigned int)ntiles * 16;
    attr = map + PORT_ART_ROWS * PORT_COLS;
    if (gb_is_cgb()) {
        VBK_REG = 0;
        if (npals)
            set_bkg_palette(GB_ART_PAL_BASE, npals, (uint16_t *)pals);
    }
    gb_vram_copy((unsigned char *)(GB_TILES + GB_ART_TILE_BASE * 16),
                 p + 2 + (unsigned int)npals * 8,
                 (unsigned int)ntiles * 16);
    for (row = 0; row < PORT_ART_ROWS; row++)
        gb_vram_copy((unsigned char *)(GB_MAP + (row + 1) * 32),
                     map + (unsigned int)row * PORT_COLS, PORT_COLS);
    if (gb_is_cgb()) {
        VBK_REG = 1;
        for (row = 0; row < PORT_ART_ROWS; row++)
            gb_vram_copy((unsigned char *)(GB_MAP + (row + 1) * 32),
                         attr + (unsigned int)row * PORT_COLS, PORT_COLS);
        VBK_REG = 0;
    }
    plat_set_bank(PORT_DATA_BANK);
#else
    (void)id;
#endif
}

unsigned char plat_read_key(void)
{
    unsigned char k = joypad();
#if N_SONGS > 0
    if (k & J_SELECT) {
        toggle_music();
        plat_wait_release();
        return 0;
    }
#endif
    if (k & J_UP) return 1;
    if (k & J_DOWN) return 2;
    if (k & J_LEFT) return 6;
    if (k & J_RIGHT) return 7;
    if (k & (J_A | J_START)) return 3;
    if (k & J_B) return PORT_KEY_MENU;
    return 0;
}

void plat_wait_release(void)
{
    while (joypad() & (J_UP | J_DOWN | J_LEFT | J_RIGHT |
                       J_A | J_B | J_START | J_SELECT)) {
        #asm
        nop
        #endasm
    }
}

void plat_clear_row(unsigned char row)
{
    gb_clear_row(row);
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

#if N_SONGS > 0
void plat_music_hook(unsigned char on)
{
    (void)on;
}
#endif

extern void port_unpack(const void *src, void *dst) __smallc;

void plat_load(unsigned char bank, unsigned short off, void *dst,
               unsigned char kind)
{
    (void)kind;
    plat_set_bank(bank);
    port_unpack((const void *)(0x4000 + (unsigned int)off), dst);
    plat_set_bank(PORT_DATA_BANK);
}
