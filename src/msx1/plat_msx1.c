/*
 * MSX1 platform layer (TMS9918A Graphics II).
 *
 * SCREEN 2 gives a 32x24 tile display: the title is row 0, the art band rows
 * 1..art_rows, and the text pane the rows below.  The art band is stored as
 * name-table entries plus colour-table cells; its unique 8x8 patterns are
 * copied into the pattern-generator banks for the screen thirds it spans.
 * Scene/inventory/song data uses the same ASCII16-mapped banks as the MSX2
 * target (bank 1 for story data, one bank per art, a font bank after them).
 */
#include <msx.h>
#include <conio.h>
#include <games.h>
#include "plat.h"
#include "port_data.h"

#ifndef PORT_ART_WS
#define PORT_ART_WS 4096
#endif
#ifndef PORT_OVERLAY_MENU
#define PORT_OVERLAY_MENU 0
#endif
#ifndef PORT_ART_ROWS
#define PORT_ART_ROWS 10
#endif
#ifndef PORT_TEXT_TOP
#define PORT_TEXT_TOP (1 + PORT_ART_ROWS)
#endif

#define MSX1_ROWS 24
#define MSX1_COLS 32
#define MSX1_PNT 0x1800
#define MSX1_CT 0x2000
#define MSX1_PATTERN 0x0000
#define MSX1_NAMES (MSX1_ROWS * MSX1_COLS)
#define MSX1_COLOUR_BYTES (MSX1_NAMES * 8)
#define MSX1_ART_CELLS (PORT_ART_ROWS * MSX1_COLS)
#define MSX1_FONT_TILES 96

static unsigned char art_ws[PORT_ART_WS];

/* The name-table byte for the character cell; the font occupies patterns
   0..95 and each art's patterns follow at 96..95+ntiles. */
#define MSX1_BG ((unsigned char)(((PORT_TEXT_BG & 0x0F) << 4) \
                                 | (PORT_TEXT_BG & 0x0F)))

extern void msx1_vwrite(const unsigned char *src, unsigned int addr,
                        unsigned int count);
extern void msx1_fill(unsigned int addr, unsigned char value,
                      unsigned int count);
extern void msx1_text(const char *src, unsigned int pnt, unsigned int ct,
                      unsigned char n, unsigned char color);
extern void msx1_set_reg(unsigned char reg, unsigned char value);
extern void port_unpack(const void *src, void *dst) __smallc;

/* ASCII16 mapper: the 0x8000 window is selected at 0x7000. */
void plat_set_bank(unsigned char bank) __z88dk_fastcall
{
    #asm
    ld a,l
    ld ($7000),a
    #endasm
}

static void screen2(void)
{
    #asm
    ld a,2
    call $005f
    ei
    #endasm
}

/* Clear a run of whole character rows in the name and colour tables. */
static void clear_rows(unsigned char first, unsigned char last)
{
    unsigned char row;
    for (row = first; row <= last && row < MSX1_ROWS; row++) {
        msx1_fill(MSX1_PNT + (unsigned int)row * MSX1_COLS, 0,
                  MSX1_COLS);
        msx1_fill(MSX1_CT + (unsigned int)row * MSX1_COLS * 8, MSX1_BG,
                  MSX1_COLS * 8);
    }
}

void plat_init(void)
{
    unsigned char i;

    screen2();
    msx1_set_reg(7, PORT_TEXT_BG & 0x0F);

    /* Copy the shared 8x8 font into each Graphics II pattern bank (one bank
       per eight-row screen third).  The raw font sits in its own ROM bank. */
    plat_set_bank(MSX1_FONT_BANK);
    for (i = 0; i < 3; i++)
        msx1_vwrite((const unsigned char *)0x8000,
                    (unsigned int)i * 0x0800, 768);
    plat_set_bank(PORT_DATA_BANK);
    plat_clear();
}

void plat_clear(void)
{
    msx1_fill(MSX1_PNT, 0, MSX1_NAMES);
    msx1_fill(MSX1_CT, MSX1_BG, MSX1_COLOUR_BYTES);
}

void plat_clear_text(void)
{
    clear_rows(0, 0);
    clear_rows(PORT_TEXT_TOP, MSX1_ROWS - 2);
#if PORT_OVERLAY_MENU
    clear_rows(MSX1_ROWS - 1, MSX1_ROWS - 1);
#endif
}

void plat_clear_pane(void)
{
    clear_rows(PORT_TEXT_TOP, MSX1_ROWS - 1);
}

void plat_clear_row(unsigned char row)
{
    clear_rows(row, row);
}

void plat_text_at(unsigned char row, unsigned char col, const char *s,
                  unsigned char color)
{
    unsigned char n = 0;
    unsigned char cell;
    unsigned int pnt, ct;
    if (row >= MSX1_ROWS || col >= MSX1_COLS)
        return;
    while (s[n] && col + n < MSX1_COLS)
        n++;
    if (!n)
        return;
    pnt = MSX1_PNT + (unsigned int)row * MSX1_COLS + col;
    ct = MSX1_CT + ((unsigned int)row * MSX1_COLS + col) * 8;
    if (color == PLAT_COLOR_SEL)
        cell = PORT_HIGHLIGHT_INK & 0xFF;
    else
        cell = PORT_TEXT_INK & 0xFF;
    msx1_text(s, pnt, ct, n, cell);
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
#if HAVE_ART
    unsigned char bank, npat, r, c, j, b;
    unsigned int off;
    const unsigned char *cells, *patterns;
    const unsigned char *src;
    if (id >= N_ART)
        return;
    bank = port_art_bank[id];
    off = port_art_off[id];
    plat_set_bank(bank);
    port_unpack((const void *)(0x8000 + off + 2), art_ws);
    plat_set_bank(PORT_DATA_BANK);

    npat = art_ws[0];
    cells = art_ws + 1;
    patterns = cells + (unsigned int)MSX1_ART_CELLS * 9;

    /* The art spans screen rows 1..art_rows, so it only uses pattern banks 0
       and 1 (the third bank carries text on rows 16..23). */
    for (j = 0; j < npat; j++) {
        for (b = 0; b < 2; b++)
            msx1_vwrite(patterns + (unsigned int)j * 8,
                        (unsigned int)b * 0x0800
                        + (unsigned int)(MSX1_FONT_TILES + j) * 8, 8);
    }
    for (r = 0; r < PORT_ART_ROWS; r++) {
        for (c = 0; c < MSX1_COLS; c++) {
            src = cells + ((unsigned int)r * MSX1_COLS + c) * 9;
            msx1_vwrite(src,
                        MSX1_PNT + (unsigned int)(1 + r) * MSX1_COLS + c, 1);
            msx1_vwrite(src + 1,
                        MSX1_CT + ((unsigned int)(1 + r) * MSX1_COLS + c) * 8,
                        8);
        }
    }
#else
    (void)id;
#endif
}

/* SNSMAT ($0141) reads a keyboard matrix row: A selects the row and the
   returned bits are clear for pressed keys. */
static unsigned char msx_matrix(unsigned char row) __z88dk_fastcall
{
    #asm
    di
    ld      a,l
    call    $0141
    ld      l,a
    ld      h,0
    ei
    #endasm
}

static unsigned char msx_keys_held(void)
{
    unsigned char held = 0;
    held |= (unsigned char)~msx_matrix(0) & 0x54;   /* 2 4 6 */
    held |= (unsigned char)~msx_matrix(1) & 0x01;   /* 8 */
    held |= (unsigned char)~msx_matrix(2) & 0x40;   /* A */
    held |= (unsigned char)~msx_matrix(3) & 0x02;   /* D */
    held |= (unsigned char)~msx_matrix(5) & 0x11;   /* S W */
    held |= (unsigned char)~msx_matrix(7) & 0x80;   /* ENTER */
    held |= (unsigned char)~msx_matrix(8) & 0xF1;   /* SPACE, arrows */
    return held;
}

#if PORT_OVERLAY_MENU
static unsigned char msx_space(void)
{
    #asm
    ld      a,0
    call    $00D8
    ei
    ld      l,a
    ld      h,0
    #endasm
}
#endif

unsigned char plat_read_key(void)
{
    unsigned int k;
#if PORT_OVERLAY_MENU
    if (msx_space()) return PORT_KEY_MENU;
#endif
    k = joystick(0) | joystick(1);
    if (k & MOVE_UP) return 1;
    if (k & MOVE_DOWN) return 2;
    if (k & MOVE_LEFT) return 6;
    if (k & MOVE_RIGHT) return 7;
    if (k & MOVE_FIRE) return 3;
#if PORT_OVERLAY_MENU
    if (k & MOVE_FIRE2) return PORT_KEY_MENU;
#endif
    if (kbhit()) {
        int c = getch();
#if PORT_OVERLAY_MENU
        if (c == ' ') return PORT_KEY_MENU;
        if (c == '\r' || c == '\n') return 3;
#else
        if (c == '\r' || c == '\n' || c == ' ') return 3;
#endif
        if (c == 'w' || c == '8') return 1;
        if (c == 's' || c == '2') return 2;
        if (c == 'a' || c == '4') return 6;
        if (c == 'd' || c == '6') return 7;
    }
    return 0;
}

void plat_wait_release(void)
{
    for (;;) {
        while ((joystick(0) | joystick(1))
               & (MOVE_UP | MOVE_DOWN | MOVE_LEFT | MOVE_RIGHT | MOVE_FIRE
#if PORT_OVERLAY_MENU
                  | MOVE_FIRE2
#endif
                  )) {
            #asm
            nop
            #endasm
        }
        while (kbhit())
            getch();
        if (!msx_keys_held())
            break;
    }
}

void plat_boot(void)
{
}

void plat_scene_entered(unsigned char id)
{
    (void)id;
}

void plat_load(unsigned char bank, unsigned short off, void *dst,
               unsigned char kind)
{
    plat_set_bank(PORT_DATA_BANK);
    if (kind == PLAT_LOAD_INV)
        port_unpack(port_inv_data, dst);
    else
        port_unpack(port_scene_data + off, dst);
}
