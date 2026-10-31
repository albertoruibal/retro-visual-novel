#include <arch/sms.h>
#include <rect.h>
#include <input.h>
#include "plat.h"
#include "port_data.h"
#include "port_font8.h"

static unsigned int text_row[PORT_COLS];

/* Two extra 1bpp glyphs uploaded after the font: up/down scroll arrows. */
static const unsigned char scroll_arrows[16] = {
    0x18, 0x3C, 0x7E, 0xFF, 0x18, 0x18, 0x18, 0x00,
    0x18, 0x18, 0x18, 0xFF, 0x7E, 0x3C, 0x18, 0x00
};

static unsigned int text_tile(unsigned char c)
{
    if (c == 1)
        return SMS_FONT_TILES - 2;
    if (c == 2)
        return SMS_FONT_TILES - 1;
    return (c >= 32 && c < 128) ? (unsigned char)(c - 32) : 0;
}

void plat_init(void)
{
    static const unsigned char palette[16] = {
        PORT_TEXT_BG, PORT_TEXT_INK, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    };
    static const unsigned char sprite_palette[16] = {
        PORT_TEXT_BG, PORT_HIGHLIGHT_INK, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    };
    sms_memcpy_mem_to_cram(0, (void *)palette, 16);
    sms_memcpy_mem_to_cram(16, (void *)sprite_palette, 16);
    sms_vdp_set_write_address(0);
    sms_copy_font_8x8_to_vram((void *)port_font8, 96, 0, 1);
    sms_vdp_set_write_address((SMS_FONT_TILES - 2) * 32);
    sms_copy_font_8x8_to_vram((void *)scroll_arrows, 2, 0, 1);
    sms_display_on();
    plat_clear();
}

void plat_clear(void)
{
    static struct r_Rect8 all = { 0, 32, 0, PLAT_ROWS };
    sms_tiles_clear_area(&all, 0);
}

void plat_clear_pane(void)
{
    static struct r_Rect8 pane = { 0, 32, PORT_TEXT_TOP,
                                   PLAT_ROWS - PORT_TEXT_TOP };
    sms_tiles_clear_area(&pane, 0);
}

void plat_text_color(unsigned char row, unsigned char col, const char *s,
                     unsigned char color)
{
    unsigned char i;
    unsigned int attr = (color == PLAT_COLOR_SEL) ? 0x0800 : 0;
    static struct r_Rect8 line = { 0, PORT_COLS, 0, 1 };
    for (i = 0; i < PORT_COLS; i++)
        text_row[i] = attr;
    while (*s && col < PORT_COLS) {
        unsigned char c = (unsigned char)*s++;
        text_row[col++] = attr | text_tile(c);
    }
    line.y = row;
    sms_tiles_put_area(&line, text_row);
}

void plat_text_at(unsigned char row, unsigned char col, const char *s,
                  unsigned char color)
{
    unsigned char n = 0;
    unsigned int attr = (color == PLAT_COLOR_SEL) ? 0x0800 : 0;
    static struct r_Rect8 area = { 0, 0, 0, 1 };
    while (s[n] && col + n < PORT_COLS) {
        unsigned char c = (unsigned char)s[n];
        text_row[n] = attr | text_tile(c);
        n++;
    }
    if (!n)
        return;
    area.x = col;
    area.width = n;
    area.y = row;
    sms_tiles_put_area(&area, text_row);
}

void plat_text(unsigned char row, unsigned char col, const char *s)
{
    plat_text_color(row, col, s, 0);
}

void plat_draw_art(unsigned char id)
{
#if HAVE_ART
    unsigned char *p;
    unsigned int ntiles;
    static struct r_Rect8 band = { 0, 32, 1, PORT_ART_ROWS };
    if (id >= N_ART)
        return;
    MM_FFFF = port_art_bank[id];
    p = (unsigned char *)(0x8000 + port_art_off[id]);
    ntiles = p[0] | ((unsigned int)p[1] << 8);
    sms_memcpy_mem_to_cram(0, (void *)(p + 2), 16);
    if (ntiles) {
        sms_vdp_set_write_address(SMS_FONT_TILES * 32);
        sms_copy_mem_to_vram((void *)(p + 18 + PORT_ART_ROWS * 64),
                             ntiles * 32);
    }
    sms_tiles_put_area(&band, (void *)(p + 18));
#else
    (void)id;
#endif
}

unsigned char plat_read_key(void)
{
    unsigned int k = in_stick_1();
    if (k & 0x01) return 1;
    if (k & 0x02) return 2;
    if (k & 0x04) return 6;
    if (k & 0x08) return 7;
    if (k & 0x40) return PORT_KEY_MENU;
    if (k & 0x80) return 3;
    return 0;
}

void plat_wait_release(void)
{
    while (in_stick_1() & 0xCF)
        ;
}

void plat_clear_row(unsigned char row)
{
    static struct r_Rect8 line = { 0, PORT_COLS, 0, 1 };
    line.y = row;
    sms_tiles_clear_area(&line, 0);
}

void plat_boot(void)
{
}

void plat_scene_entered(unsigned char id)
{
    (void)id;
}

extern void port_unpack(const void *src, void *dst) __smallc;

void plat_load(unsigned char bank, unsigned short off, void *dst,
               unsigned char kind)
{
    (void)bank;
    if (kind == PLAT_LOAD_INV)
        port_unpack(port_inv_data, dst);
    else
        port_unpack(port_scene_data + off, dst);
}
