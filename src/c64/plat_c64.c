/*
 * Commodore 64 platform layer for the shared portable story engine.
 *
 * The VIC-II runs in multicolor character mode.  The 256-entry charset at
 * $A000 holds 96 hi-res text glyphs (indices 0..95) followed by up to 160
 * multicolor art tiles (indices 96..255).  Screen RAM is $A800, colour RAM
 * $D800.  VIC bank 2 is selected through CIA2, and the linker config reserves
 * $A000-$ABFF and puts BSS at $AC00.
 */
#include <conio.h>

#include "plat.h"
#include "port_data.h"
#include "port_font8.h"

#define CIA1_PRA (*(volatile unsigned char *)0xDC00)
#define CIA1_PRB (*(volatile unsigned char *)0xDC01)
#define CIA1_DDRA (*(volatile unsigned char *)0xDC02)
#define CIA1_DDRB (*(volatile unsigned char *)0xDC03)
#define CIA2_PRA (*(volatile unsigned char *)0xDD00)

#define VIC_CTRL1 (*(volatile unsigned char *)0xD011)
#define VIC_CTRL2 (*(volatile unsigned char *)0xD016)
#define VIC_MEM (*(volatile unsigned char *)0xD018)
#define VIC_BORDER (*(volatile unsigned char *)0xD020)
#define VIC_BG (*(volatile unsigned char *)0xD021)
#define VIC_COLOR1 (*(volatile unsigned char *)0xD022)
#define VIC_COLOR2 (*(volatile unsigned char *)0xD023)

#define SCREEN ((volatile unsigned char *)0xA800)
#define CHARSET ((volatile unsigned char *)0xA000)
#define COLORS ((volatile unsigned char *)0xD800)

#ifndef C64_FONT_TILES
#define C64_FONT_TILES 96
#endif
#ifndef C64_ART_WS_SIZE
#define C64_ART_WS_SIZE 2300
#endif

extern void port_unpack(const void *src, void *dst);
extern unsigned char c64_any_key_down(void);

#if HAVE_ART
static unsigned char art_ws[C64_ART_WS_SIZE];
#endif

static void display_off(void)
{
    VIC_CTRL1 &= (unsigned char)~0x10;         /* DEN off */
}

static void display_on(void)
{
    VIC_CTRL1 |= 0x10;
}

static void clear_cells(unsigned char first, unsigned char last)
{
    unsigned int base, i;
    unsigned char row;
    for (row = first; row <= last && row < PLAT_ROWS; row++) {
        base = (unsigned int)row * PORT_COLS;
        for (i = 0; i < PORT_COLS; i++) {
            SCREEN[base + i] = 0;
            COLORS[base + i] = 0;
        }
    }
}

void plat_init(void)
{
    unsigned int i;

    display_off();
    /* VIC bank 2: $8000-$BFFF.  Bits 0-1 of CIA2 port A are inverted. */
    CIA2_PRA = (unsigned char)((CIA2_PRA & 0xFC) | 0x01);
    VIC_MEM = 0xA8;          /* screen $A800, charset $A000 */
    VIC_BG = PORT_TEXT_BG;
    VIC_BORDER = PORT_TEXT_BG;
    VIC_COLOR1 = 0;
    VIC_COLOR2 = 0;
    for (i = 0; i < sizeof(port_font8); i++)
        CHARSET[i] = port_font8[i];
    clear_cells(0, PLAT_ROWS - 1);
    VIC_CTRL2 = 0xD8;        /* MCM + CSEL */
    VIC_CTRL1 = 0x1B;        /* DEN, RSEL, YSCROLL 3 (character mode) */
    display_on();
    *(volatile unsigned char *)0xCC = 0;   /* KERNAL cursor blink off */
    *(volatile unsigned char *)0xC6 = 0;   /* clear keyboard buffer */
}

void plat_clear(void)
{
    display_off();
    clear_cells(0, PLAT_ROWS - 1);
    display_on();
}

void plat_clear_pane(void)
{
    clear_cells(PORT_TEXT_TOP, PLAT_ROWS - 1);
}

void plat_clear_text(void)
{
    clear_cells(0, 0);
    clear_cells(PORT_TEXT_TOP, PLAT_ROWS - 1);
}

void plat_clear_row(unsigned char row)
{
    unsigned int base = (unsigned int)row * PORT_COLS;
    unsigned int i;
    if (row >= PLAT_ROWS)
        return;
    for (i = 0; i < PORT_COLS; i++) {
        SCREEN[base + i] = 0;
        COLORS[base + i] = 0;
    }
}

static unsigned char text_colour(unsigned char color)
{
    if (color == PLAT_COLOR_SEL)
        return PORT_HIGHLIGHT_INK;
    return PORT_TEXT_INK;
}

void plat_text_at(unsigned char row, unsigned char col, const char *s,
                  unsigned char color)
{
    unsigned int o;
    unsigned char c = text_colour(color);

    if (row >= PLAT_ROWS)
        return;
    o = (unsigned int)row * PORT_COLS + col;
    while (*s && col < PORT_COLS) {
        unsigned char ch = (unsigned char)*s++;
        if (ch < 32 || ch > 127)
            ch = 32;
        SCREEN[o] = (unsigned char)(ch - 32);
        COLORS[o] = c;
        o++;
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
    const unsigned char *p, *map, *colors;
    unsigned char ntiles, c22, c23, i, row, col;
    unsigned int o;

    if (id >= N_ART)
        return;
    display_off();
    p = port_art_data + port_art_off[id];
    port_unpack(p, art_ws);
    ntiles = art_ws[0];
    c22 = art_ws[1];
    c23 = art_ws[2];
    VIC_COLOR1 = c22;
    VIC_COLOR2 = c23;
    if (!ntiles) {
        clear_cells(1, PORT_ART_ROWS);
        display_on();
        return;
    }
    for (i = 0; i < ntiles; i++)
        for (o = 0; o < 8; o++)
            CHARSET[(unsigned int)C64_FONT_TILES * 8 + (unsigned int)i * 8 + o]
                = art_ws[3 + (unsigned int)i * 8 + o];
    map = art_ws + 3 + (unsigned int)ntiles * 8;
    colors = map + (unsigned int)PORT_COLS * PORT_ART_ROWS;
    for (row = 0; row < PORT_ART_ROWS; row++) {
        o = (unsigned int)(1 + row) * PORT_COLS;
        for (col = 0; col < PORT_COLS; col++) {
            unsigned int k = (unsigned int)row * PORT_COLS + col;
            SCREEN[o + col] = (unsigned char)(C64_FONT_TILES + map[k]);
            COLORS[o + col] = colors[k];
        }
    }
    display_on();
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
#if N_SONGS > 0
    set_music(scene_song[id]);
#else
    (void)id;
#endif
}

unsigned char plat_read_key(void)
{
    unsigned char c;
    if (!kbhit())
        return 0;
    c = cgetc();
    if (c == 'W' || c == 'w' || c == 145)
        return 1;                          /* CURSOR_UP */
    if (c == 'S' || c == 's' || c == 17)
        return 2;                          /* CURSOR_DOWN */
    if (c == 'A' || c == 'a' || c == 157)
        return 6;                          /* CURSOR_LEFT */
    if (c == 'D' || c == 'd' || c == 29)
        return 7;                          /* CURSOR_RIGHT */
    if (c == 13)
        return 3;                          /* CURSOR_ENTER */
    if (c == 32)
        return PORT_KEY_MENU;
    if (c == 'P' || c == 'p') {
#if N_SONGS > 0
        toggle_music();
#endif
        return 0;
    }
    return 0;
}

void plat_wait_release(void)
{
    unsigned char i;
    while (kbhit())
        cgetc();
    while (c64_any_key_down()) {
        for (i = 0; i < 8; i++)
            ;
    }
    while (kbhit())
        cgetc();
}
