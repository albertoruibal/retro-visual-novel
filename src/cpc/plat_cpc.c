#include <conio.h>
#include <cpc.h>
#include <games.h>
#include <input.h>
#include <interrupt.h>
#include <psg/vt2.h>
#include <string.h>
#include "plat.h"
#include "port_data.h"
#include "port_font4.h"

#define CPC_SCREEN 0xC000
#define CPC_SCREEN_BYTES 16384
#ifndef SONG_WS_ADDR
#define SONG_WS_ADDR 0x9600
#endif

#if PORT_ART_MODE == 0
#define CPC_WIDTH 160
#define CPC_INKS 16
#elif PORT_ART_MODE == 2
#define CPC_WIDTH 640
#define CPC_INKS 2
#else
#define CPC_WIDTH 320
#define CPC_INKS 4
#endif

#define CPC_TEXT_INK (CPC_INKS - 1)

static unsigned char font_w = 8;
static unsigned char font_bytes = 1;
static unsigned char font_cols = PORT_COLS;

/* Per-ink screen-byte lookups for one glyph scanline.  The 4-bit font row is
   expanded to the CPC bitplane layout once, so drawing a glyph is just a few
   table reads and stores instead of a per-pixel test-and-shift loop. */
#if PORT_ART_MODE == 0
static unsigned char m0_pair[2][4];
#elif PORT_ART_MODE == 1
static unsigned char m1_nib[2][16];
static unsigned char m1_dbl[2][4];
#endif

extern void cpc_set_ink(unsigned int pen, unsigned int color);

/* Pen 0 is the configured text background (the title/text pane clears to it);
   text and highlight use the top two inks.  Mode 2 has only two pens, so it
   renders highlight in the text ink.  Mode 1 is a monochrome screen: its four
   pens are a black/grey/white ramp shared by the picture and the text, so the
   configured text colours do not apply. */
static void set_text_palette(void)
{
#if PORT_ART_MODE == 1
    cpc_set_ink(0, 0);
    cpc_set_ink(1, 13);
    cpc_set_ink(2, 26);
    cpc_set_ink(3, 26);
#else
    cpc_set_ink(0, PORT_TEXT_BG);
    cpc_set_ink(CPC_TEXT_INK, PORT_TEXT_INK);
    if (CPC_INKS > 2)
        cpc_set_ink(CPC_TEXT_INK - 1, PORT_HIGHLIGHT_INK);
#endif
}

extern void cpc_unpack_banked(unsigned int bank, unsigned int off, void *dst);
extern void cpc_restore_base(void);
extern void port_unpack(const void *src, void *dst);

#if PORT_ART_MODE == 2
static unsigned char dbl4(unsigned char n)
{
    return (unsigned char)(((n & 8) ? 0xC0 : 0)
                           | ((n & 4) ? 0x30 : 0)
                           | ((n & 2) ? 0x0C : 0)
                           | ((n & 1) ? 0x03 : 0));
}
#endif

static void clear_char_row(unsigned char row)
{
    unsigned char blk;
    unsigned char *p = (unsigned char *)CPC_SCREEN;
    for (blk = 0; blk < 8; blk++)
        memset(p + (unsigned int)blk * 0x800 + (unsigned int)row * 80,
               0, 80);
}

#if PORT_ART_MODE == 0
/* Two Mode 0 pixels (bit1 = left, bit0 = right) as one screen byte. */
static unsigned char mode0_pair(unsigned char ink, unsigned char px)
{
    unsigned char b = 0;
    if (px & 2) {
        if (ink & 1) b |= 0x80;
        if (ink & 2) b |= 0x08;
        if (ink & 4) b |= 0x20;
        if (ink & 8) b |= 0x02;
    }
    if (px & 1) {
        if (ink & 1) b |= 0x40;
        if (ink & 2) b |= 0x04;
        if (ink & 4) b |= 0x10;
        if (ink & 8) b |= 0x01;
    }
    return b;
}
#elif PORT_ART_MODE == 1
/* Four Mode 1 pixels (bit3 = leftmost) as one screen byte. */
static unsigned char mode1_nib(unsigned char ink, unsigned char px)
{
    unsigned char b = 0, k;
    for (k = 0; k < 4; k++) {
        if (px & (0x08 >> k)) {
            if (ink & 2) b |= (unsigned char)(0x80 >> k);
            if (ink & 1) b |= (unsigned char)(0x08 >> k);
        }
    }
    return b;
}
#endif

static void build_glyph_tables(void)
{
#if PORT_ART_MODE == 0 || PORT_ART_MODE == 1
    unsigned char i, j;
    for (i = 0; i < 2; i++) {
        unsigned char ink = (unsigned char)(i ? CPC_TEXT_INK - 1
                                              : CPC_TEXT_INK);
#if PORT_ART_MODE == 0
        for (j = 0; j < 4; j++)
            m0_pair[i][j] = mode0_pair(ink, j);
#else
        for (j = 0; j < 16; j++)
            m1_nib[i][j] = mode1_nib(ink, j);
        for (j = 0; j < 4; j++) {
            /* Two source pixels, each doubled horizontally. */
            unsigned char d = (unsigned char)(((j & 2) ? 0x0C : 0)
                                              | ((j & 1) ? 0x03 : 0));
            m1_dbl[i][j] = m1_nib[i][d];
        }
#endif
    }
#endif
}

#if N_SONGS > 0
static void music_isr(void)
{
    M_PRESERVE_MAIN;
    M_PRESERVE_INDEX;
    ay_vt2_play();
    M_RESTORE_INDEX;
    M_RESTORE_MAIN;
}

unsigned char *plat_song_ws(void)
{
    return (unsigned char *)SONG_WS_ADDR;
}

void plat_music_hook(unsigned char on)
{
    (void)on;
}
#endif

void plat_init(void)
{
    unsigned char i;
    unsigned char max_ink = CPC_INKS;
    cpc_setmode(PORT_ART_MODE);
    memset((void *)CPC_SCREEN, 0, CPC_SCREEN_BYTES);
    for (i = 0; i < max_ink; i++)
        cpc_set_ink(i, 0);
    set_text_palette();
    cpc_SetBorder(0);
    cpc_restore_base();
    font_w = (PORT_COLS <= CPC_WIDTH / 8) ? 8 : 4;
    font_cols = (unsigned char)(CPC_WIDTH / font_w);
#if PORT_ART_MODE == 0
    font_bytes = (unsigned char)(font_w / 2);
#elif PORT_ART_MODE == 2
    font_bytes = (unsigned char)(font_w / 8);
#else
    font_bytes = (unsigned char)(font_w / 4);
#endif
    build_glyph_tables();
    while (kbhit())
        getch();
#if N_SONGS > 0
    ay_vt2_stop();
    im1_init();
    add_raster_int(music_isr);
#endif
}

void plat_clear(void)
{
    memset((void *)CPC_SCREEN, 0, CPC_SCREEN_BYTES);
}

/* Clear the rows below the art band (and above the inventory) in one memset
   per scanline block instead of one per character row. */
static void clear_pane_rows(void)
{
    unsigned char blk;
    for (blk = 0; blk < 8; blk++)
        memset((unsigned char *)CPC_SCREEN + (unsigned int)blk * 0x800
               + (unsigned int)PORT_TEXT_TOP * 80, 0,
               (unsigned int)(PLAT_ROWS - PORT_TEXT_TOP) * 80);
}

void plat_clear_text(void)
{
    clear_char_row(0);
    clear_pane_rows();
}

void plat_clear_pane(void)
{
    clear_pane_rows();
}

void plat_draw_art(unsigned char id)
{
#if HAVE_ART
    unsigned char n, i, blk, *p;
    unsigned char inks[CPC_INKS];
    unsigned int chunk, j;
    unsigned char *src;
    if (id >= N_ART) {
        plat_clear_text();           /* no art in this game: still clear the pane */
        return;
    }
    /* Blank every pen first: the decoder writes the blob straight into video
       RAM, so without this its header and scanline chunks would be visible
       (most of all in the text area at the bottom) until the scatter and the
       clears finish. */
    for (i = 0; i < CPC_INKS; i++)
        cpc_set_ink(i, 0);
    cpc_restore_base();
    if (port_art_bank[id] == 2)
        port_unpack((const void *)(0x8000 + (unsigned int)port_art_off[id] + 2),
                    (void *)CPC_SCREEN);
    else
        cpc_unpack_banked(port_art_bank[id],
                          (unsigned int)port_art_off[id] + 2,
                          (void *)CPC_SCREEN);
    p = (unsigned char *)CPC_SCREEN;
    n = *p++;
    src = p + n;                    /* chunks start after the n ink bytes */
    if (n > CPC_INKS)
        n = CPC_INKS;
    for (i = 0; i < n; i++)
        inks[i] = p[i];
    chunk = (unsigned int)PORT_ART_ROWS * 80;
    for (blk = 8; blk > 0; blk--) {
        unsigned char b = blk - 1;
        unsigned char *s = src + (unsigned int)b * chunk;
        unsigned char *d = (unsigned char *)CPC_SCREEN
            + (unsigned int)b * 0x800 + 80;
        /* Descending block order plus a backwards copy keeps the in-place
           source chunks intact. */
        for (j = chunk; j > 0; j--)
            d[j - 1] = s[j - 1];
    }
    plat_clear_text();
    /* Keep the picture's own palette. The blob reserves entry 0 for the text
       background and the top two for the configured text/highlight inks (Mode
       2 uses the text ink for both), so the picture keeps its full ink count
       while cleared rows and text keep the author's colours. Apply it only
       once the garbage is cleared. */
    for (i = 0; i < n; i++)
        cpc_set_ink(i, inks[i]);
    cpc_restore_base();
#else
    (void)id;
#endif
}

void plat_text_at(unsigned char row, unsigned char col, const char *s,
                  unsigned char color)
{
    unsigned int addr = (unsigned int)CPC_SCREEN + (unsigned int)row * 80
        + (unsigned int)col * font_bytes;
#if PORT_ART_MODE != 2
    unsigned char ink = (color == PLAT_COLOR_SEL && CPC_INKS > 2) ? 1 : 0;
#else
    (void)color;
#endif
    while (*s && col < PORT_COLS && col < font_cols) {
        unsigned char c = (unsigned char)*s++;
        const unsigned char *g;
        unsigned char sy;
        if (c < 32 || c >= 128)
            c = '?';
        g = port_font4 + (unsigned int)(c - 32) * 8;
        for (sy = 0; sy < 8; sy++) {
            unsigned char *p = (unsigned char *)(addr
                                                 + (unsigned int)sy * 0x800);
            unsigned char bits = g[sy] & 0x0F;
#if PORT_ART_MODE == 0
            if (font_w == 8) {
                p[0] = m0_pair[ink][(bits & 0x08) ? 3 : 0];
                p[1] = m0_pair[ink][(bits & 0x04) ? 3 : 0];
                p[2] = m0_pair[ink][(bits & 0x02) ? 3 : 0];
                p[3] = m0_pair[ink][(bits & 0x01) ? 3 : 0];
            } else {
                p[0] = m0_pair[ink][(bits >> 2) & 3];
                p[1] = m0_pair[ink][bits & 3];
            }
#elif PORT_ART_MODE == 1
            if (font_w == 8) {
                p[0] = m1_dbl[ink][(bits >> 2) & 3];
                p[1] = m1_dbl[ink][bits & 3];
            } else {
                p[0] = m1_nib[ink][bits];
            }
#else
            p[0] = (font_w == 8) ? dbl4(bits)
                                 : (unsigned char)(bits << 4);
#endif
        }
        addr += font_bytes;
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
    plat_text_at(row, col, s, 0);
}

unsigned char plat_read_key(void)
{
    unsigned char key = 0;
    unsigned int k;
#if N_SONGS > 0
    {
        unsigned char c = (unsigned char)in_Inkey();
        if (c == 'p' || c == 'P') {
            toggle_music();
            plat_wait_release();
            cpc_restore_base();
            return 0;
        }
    }
#endif
#if PORT_OVERLAY_MENU
    /* The firmware buffer does not always report SPACE, and an emulator's
       keyboard joystick can turn it into fire, so read the key matrix
       directly before the joystick bits.  in_Inkey() does not consume it. */
    if (in_Inkey() == ' ') {
        cpc_restore_base();
        return PORT_KEY_MENU;
    }
#endif
    k = joystick(1) | joystick(2);
    if (k & MOVE_UP) key = 1;
    else if (k & MOVE_DOWN) key = 2;
    else if (k & MOVE_LEFT) key = 6;
    else if (k & MOVE_RIGHT) key = 7;
    else if (k & MOVE_FIRE) key = 3;
    else if (kbhit()) {
        int c = getch();
        if (c == 'w' || c == '8' || c == 0xF0) key = 1;
        else if (c == 's' || c == '2' || c == 0xF1) key = 2;
        else if (c == 'a' || c == '4' || c == 0xF2) key = 6;
        else if (c == 'd' || c == '6' || c == 0xF3) key = 7;
#if PORT_OVERLAY_MENU
        else if (c == ' ') key = PORT_KEY_MENU;
        else if (c == '\r') key = 3;
#else
        else if (c == '\r' || c == ' ') key = 3;
#endif
    }
    cpc_restore_base();
    return key;
}

void plat_wait_release(void)
{
    for (;;) {
        unsigned int k = joystick(1) | joystick(2);
        if (!(k & (MOVE_UP | MOVE_DOWN | MOVE_LEFT | MOVE_RIGHT | MOVE_FIRE))
                && !in_Inkey() && !kbhit())
            break;
        if (kbhit())
            getch();
    }
    cpc_restore_base();
}

void plat_clear_row(unsigned char row)
{
    clear_char_row(row);
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

void plat_load(unsigned char bank, unsigned short off, void *dst,
               unsigned char kind)
{
    if (kind == PLAT_LOAD_SONG) {
        if (bank == 2)
            port_unpack((const void *)(0x8000 + (unsigned int)off + 2), dst);
        else
            cpc_unpack_banked(bank, (unsigned int)off + 2, dst);
        return;
    }
    if (kind == PLAT_LOAD_INV)
        port_unpack(port_inv_data, dst);
    else
        port_unpack(port_scene_data + off, dst);
}
