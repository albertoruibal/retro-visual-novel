/*
 * MSX1 platform layer (TMS9918A Graphics II).
 *
 * SCREEN 2 gives a 32x24 tile display: the title is row 0, the art band rows
 * 1..art_rows, and the text pane the rows below.  Colour-table entries are
 * indexed by pattern number (one 2 KB bank per screen third), not by screen
 * cell, so every cell sharing a pattern also shares that pattern's colours.
 * The art band is stored as name-table entries plus colour-table bytes for
 * each pattern; its unique 8x8 patterns are copied into the pattern-generator
 * banks for the screen thirds it spans.
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

/* Highlights need their own copies of the glyph patterns because Graphics II
   colour is attached to a pattern, not to a screen cell.  The cache maps a
   normal font pattern to a spare pattern slot per screen third. */
#define HL_FREE 0xFF
static unsigned char pattern_used[3][32];
static unsigned char hl_pattern[3][96];

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

static void set_pattern_used(unsigned char bank, unsigned char p)
{
    pattern_used[bank][p >> 3] |= (unsigned char)(1 << (p & 7));
}

static unsigned char pattern_is_used(unsigned char bank, unsigned char p)
{
    return pattern_used[bank][p >> 3] & (unsigned char)(1 << (p & 7));
}

static void reset_highlight_cache(void)
{
    unsigned char bank, i;
    for (bank = 0; bank < 3; bank++) {
        for (i = 0; i < 32; i++)
            pattern_used[bank][i] = 0;
        for (i = 0; i < 96; i++)
            hl_pattern[bank][i] = HL_FREE;
        for (i = 0; i < MSX1_FONT_TILES; i++)
            set_pattern_used(bank, i);
    }
}

/* Return a pattern slot for highlighted glyph ``p`` in ``bank``.  The glyph
   is copied from the font ROM and its colour entry set to the highlight ink
   when a new slot is allocated. */
static unsigned char highlight_pattern(unsigned char bank, unsigned char p)
{
    unsigned char hp = hl_pattern[bank][p];
    unsigned char i;
    unsigned int addr;
    if (hp != HL_FREE)
        return hp;
    for (i = 255; i >= MSX1_FONT_TILES; i--) {
        if (pattern_is_used(bank, i))
            continue;
        hp = i;
        set_pattern_used(bank, hp);
        hl_pattern[bank][p] = hp;
        plat_set_bank(MSX1_FONT_BANK);
        msx1_vwrite((const unsigned char *)(0x8000 + (unsigned int)p * 8),
                    MSX1_PATTERN + (unsigned int)bank * 0x0800
                    + (unsigned int)hp * 8, 8);
        plat_set_bank(PORT_DATA_BANK);
        addr = MSX1_CT + (unsigned int)bank * 0x0800
               + (unsigned int)hp * 8;
        msx1_fill(addr, PORT_HIGHLIGHT_INK & 0xFF, 8);
        return hp;
    }
    return p;
}

static void mark_art_patterns(void)
{
    unsigned char r, c, bank;
    unsigned int off;
    for (r = 0; r < PORT_ART_ROWS; r++) {
        bank = (unsigned char)((1 + r) / 8);
        for (c = 0; c < MSX1_COLS; c++) {
            off = ((unsigned int)r * MSX1_COLS + c) * 9;
            set_pattern_used(bank, art_ws[1 + off]);
        }
    }
}

/* Clear a run of whole character rows in the name table.  Blank cells use
   pattern 0, whose colour entry stays at the background colour. */
static void clear_rows(unsigned char first, unsigned char last)
{
    unsigned char row;
    for (row = first; row <= last && row < MSX1_ROWS; row++)
        msx1_fill(MSX1_PNT + (unsigned int)row * MSX1_COLS, 0,
                  MSX1_COLS);
}

void plat_init(void)
{
    unsigned char i;

    screen2();
    msx1_set_reg(7, PORT_TEXT_BG & 0x0F);
    reset_highlight_cache();

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
    /* The colour table is per pattern number, not per cell: pass the bank
       base and let the asm write each glyph's colour below its pattern. */
    ct = MSX1_CT + (unsigned int)(row / 8) * 0x800;
    if (color == PLAT_COLOR_SEL) {
        /* Selected text uses cached duplicate patterns so its highlight ink
           does not recolour every other occurrence of the same glyph. */
        unsigned char j, ch, p, hp;
        for (j = 0; j < n; j++) {
            ch = (unsigned char)s[j];
            p = (ch >= 32 && ch < 128) ? (unsigned char)(ch - 32) : 0;
            hp = highlight_pattern((unsigned char)(row / 8), p);
            msx1_vwrite(&hp, pnt + j, 1);
        }
        return;
    }
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
            /* Colour table entry for this pattern in its screen third. */
            msx1_vwrite(src + 1,
                        MSX1_CT + (unsigned int)((1 + r) / 8) * 0x800
                        + (unsigned int)src[0] * 8, 8);
        }
    }
    reset_highlight_cache();
    mark_art_patterns();
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

/* Read PSG register 14 (the joystick inputs) directly.  z88dk's joystick()
   masks the result to five bits in the prebuilt classic library, dropping the
   second fire button, so button 2 could never open the action dialog.  R#15
   selects the port: bits 0-3 high, bits 4-5 low and G-Port (bit 6) set for
   port 1; bit 6 clear for port 2. */
static unsigned char msx_joy_raw(unsigned char port) __z88dk_fastcall
{
    #asm
    di
    ld      c,l
    ld      a,15
    out     (0A0h),a
    in      a,(0A2h)
    and     080h
    or      00Fh
    bit     0,c
    jr      nz, msx1_joy_port2
    or      040h
msx1_joy_port2:
    out     (0A1h),a
    ld      a,14
    out     (0A0h),a
    in      a,(0A2h)
    ei
    ld      l,a
    ld      h,0
    #endasm
}

static unsigned int msx_joy_bits(unsigned char raw)
{
    unsigned char v = (unsigned char)~raw;
    unsigned int k = 0;
    if (v & 0x01) k |= MOVE_UP;
    if (v & 0x02) k |= MOVE_DOWN;
    if (v & 0x04) k |= MOVE_LEFT;
    if (v & 0x08) k |= MOVE_RIGHT;
    if (v & 0x10) k |= MOVE_FIRE;
    if (v & 0x20) k |= MOVE_FIRE2;
    return k;
}

/* Device 1 is the cursor-key pseudo-stick; the two PSG ports are read
   directly so both fire buttons work. */
static unsigned int msx_joy(void)
{
    return (unsigned int)(joystick(1)
        | msx_joy_bits(msx_joy_raw(0))
        | msx_joy_bits(msx_joy_raw(1)));
}

unsigned char plat_read_key(void)
{
    unsigned int k;
#if PORT_OVERLAY_MENU
    if (msx_space()) return PORT_KEY_MENU;
#endif
    k = msx_joy();
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
        while (msx_joy()
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
