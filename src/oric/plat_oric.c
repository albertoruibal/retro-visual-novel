/*
 * Oric Atmos platform layer for the shared portable story engine.
 *
 * The screen is the 240x200 HIRES bitmap at $A000: 40 bytes per row, six
 * one-bit pixels per byte (bit 6 set, bit 5 leftmost).  Text is drawn in
 * software with a 6x8 glyph table; there is no separate text screen in the
 * bitmap band.  The three text rows below the bitmap are blanked at startup.
 *
 * Story data is resident and ZX0-compressed (the Atmos has no banked memory).
 * Art is decoded straight into the bitmap band.  The portable overlay dialog
 * provides the options/items screen; there is no pinned menu or inventory row.
 */
#include <conio.h>

#include "plat.h"
#include "port_data.h"
#include "port_font6.h"

#define HIRES ((volatile unsigned char *)0xA000)
#define TEXT ((volatile unsigned char *)0xBB80)
#define BOTTOM_TEXT ((volatile unsigned char *)0xBF68)
#define HIRES_ATTR 30                 /* 50 Hz HIRES */

extern void port_unpack(const void *src, void *dst);

static void wait_frames(void)
{
    volatile unsigned int i;
    /* The Atmos has no CPU-visible vsync.  This is only the boot delay that
       lets the ULA latch the HIRES mode attribute before we reuse $BB80. */
    for (i = 0; i < 30000; i++)
        ;
    for (i = 0; i < 30000; i++)
        ;
}

static void clear_band(unsigned char first, unsigned char last)
{
    unsigned char row, line, col;
    for (row = first; row <= last && row < PLAT_ROWS; row++)
        for (line = 0; line < 8; line++) {
            unsigned int base = ((unsigned int)row * 8 + line) * PORT_COLS;
            for (col = 0; col < PORT_COLS; col++)
                HIRES[base + col] = 0x40;
        }
}

void plat_init(void)
{
    unsigned char i;

    /* Switch the ULA to HIRES, wait for it to latch, then clear the bitmap.
       The mode attribute shares this RAM with the bitmap's line 176. */
    TEXT[0] = HIRES_ATTR;
    wait_frames();
    clear_band(0, PLAT_ROWS - 1);
    /* Each byte is an ink attribute: every cell in the three text rows below
       the bitmap shows blank paper, so no ROM charset garbage leaks in. */
    for (i = 0; i < 3 * 40; i++)
        BOTTOM_TEXT[i] = 0x00;
}

void plat_clear(void)
{
    clear_band(0, PLAT_ROWS - 1);
}

void plat_clear_text(void)
{
    clear_band(0, 0);
    clear_band(PORT_TEXT_TOP, PLAT_ROWS - 1);
}

void plat_clear_pane(void)
{
    clear_band(PORT_TEXT_TOP, PLAT_ROWS - 1);
}

void plat_clear_row(unsigned char row)
{
    if (row >= PLAT_ROWS)
        return;
    clear_band(row, row);
}

static void draw_glyph(unsigned char row, unsigned char col, unsigned char ch,
                       unsigned char color)
{
    const unsigned char *glyph;
    unsigned int base;
    unsigned char i, bits;

    if (row >= PLAT_ROWS || col >= PORT_COLS)
        return;
    if (ch < 32 || ch > 127)
        ch = 32;
    glyph = port_font6 + (unsigned int)(ch - 32) * 8;
    base = (unsigned int)row * 8 * PORT_COLS + col;
    for (i = 0; i < 8; i++) {
        bits = (unsigned char)(glyph[i] & 0x3F);
        if (color == PLAT_COLOR_SEL)
            bits = (unsigned char)(~bits & 0x3F);
        HIRES[base + (unsigned int)i * PORT_COLS] = 0x40 | bits;
    }
}

void plat_text_at(unsigned char row, unsigned char col, const char *s,
                  unsigned char color)
{
    if (row >= PLAT_ROWS)
        return;
    while (*s && col < PORT_COLS) {
        draw_glyph(row, col, (unsigned char)*s++, color);
        col++;
    }
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

#if HAVE_ART
void plat_draw_art(unsigned char id)
{
    const unsigned char *p;

    if (id >= N_ART)
        return;
    p = port_art_data + port_art_off[id];
    /* Two raw colour bytes (ignored on this monochrome target) precede the
       ZX0 pixel stream.  Decode directly into the art band: its first row is
       character row PORT_ART_TOP. */
    port_unpack(p + 2, (void *)(HIRES + (unsigned int)PORT_ART_TOP * 8
                                * PORT_COLS));
}
#else
void plat_draw_art(unsigned char id)
{
    (void)id;
}
#endif

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
    (void)id;
}

unsigned char plat_read_key(void)
{
    unsigned char c;

    if (!kbhit())
        return 0;
    c = cgetc();
    if (c == 11 || c == 'W' || c == 'w')
        return 1;                              /* CURSOR_UP */
    if (c == 10 || c == 'S' || c == 's')
        return 2;                              /* CURSOR_DOWN */
    if (c == 8 || c == 'A' || c == 'a')
        return 6;                              /* CURSOR_LEFT */
    if (c == 9 || c == 'D' || c == 'd')
        return 7;                              /* CURSOR_RIGHT */
    if (c == 13)
        return 3;                              /* CURSOR_ENTER */
    if (c == 32)
        return PORT_KEY_MENU;
    return 0;
}

void plat_wait_release(void)
{
    while (kbhit())
        cgetc();
}
