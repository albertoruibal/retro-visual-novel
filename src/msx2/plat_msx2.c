#include <msx.h>
#include <conio.h>
#include <games.h>
#include <interrupt.h>
#include <psg/vt2.h>
#include <sys/compiler.h>
#include "plat.h"
#include "port_data.h"

#ifndef MSX2_TEXT_8PX
#define MSX2_TEXT_8PX 0
#endif
#if MSX2_TEXT_8PX
#define MSX2_CHAR_PX 8
#define MSX2_CHAR_BYTES 4
#define MSX2_FONT_BYTES 4
#else
#define MSX2_CHAR_PX 6
#define MSX2_CHAR_BYTES 3
#define MSX2_FONT_BYTES 2
#endif
#define MSX2_FONT_CHARS 96

/* Screen 7 cell table expanded from the raw font at startup: the old
   pre-expanded table was 3 KB of the 16 KB fixed ROM bank. */
unsigned char port_font_cells[MSX2_FONT_CHARS * 8 * MSX2_FONT_BYTES];

#define MSX2_ROWS 24
#define MSX2_LINE 256          /* 512 pixels, four bits per pixel */
#define MSX2_TEXT_X ((512 - PORT_COLS * MSX2_CHAR_PX) / 2)
#define MSX2_BAND_ADDR (8 * MSX2_LINE)
#define MSX2_SCREEN_LINES 212
#define MSX2_TEXT_BG 0
#define MSX2_TEXT_HIGHLIGHT 14
#define MSX2_TEXT_BODY 15

static void screen7(void)
{
    #asm
    ld a,7
    ld ix,$005f
    ld iy,($fcc0)
    call $001c
    ei
    #endasm
}

/* ASCII16 mapper: the 0x8000 window is selected at 0x7000. */
void plat_set_bank(unsigned char bank) __z88dk_fastcall
{
    #asm
    ld a,l
    ld ($7000),a
    #endasm
}

static void palette_byte(unsigned char value) __z88dk_fastcall
{
    #asm
    ld a,l
    out ($9a),a
    #endasm
}

static void set_palette(const unsigned char *pal)
{
    unsigned char i;
    vdp_set_reg(16, 0);
    for (i = 0; i < 32; i++)
        palette_byte(pal[i]);
}

static void default_palette(void)
{
    unsigned char pal[32];
    unsigned char i;
    for (i = 0; i < 32; i++)
        pal[i] = 0;
    /* Entry 0 is the configured text background; entries 14/15 carry the
       highlight/text inks, all as little-endian red-blue, green byte pairs. */
    pal[0] = PORT_TEXT_BG & 0xFF;
    pal[1] = (PORT_TEXT_BG >> 8) & 0xFF;
    pal[28] = PORT_HIGHLIGHT_INK & 0xFF;
    pal[29] = (PORT_HIGHLIGHT_INK >> 8) & 0xFF;
    pal[30] = PORT_TEXT_INK & 0xFF;
    pal[31] = (PORT_TEXT_INK >> 8) & 0xFF;
    set_palette(pal);
}

extern void msx2_vwrite(const unsigned char *src, unsigned int addr,
                        unsigned int count);
extern void port_unpack(const void *src, void *dst) __smallc;
static unsigned char art_strip[2048];
extern void msx2_fill(unsigned int dx, unsigned int dy, unsigned int nx,
                      unsigned int ny, unsigned char color);
extern void msx2_text(const char *src, unsigned int addr, unsigned char n,
                      unsigned char mask);
extern void msx2_text8(const char *src, unsigned int addr, unsigned char n,
                       unsigned char mask);

static void build_font_cells(const unsigned char *raw)
{
    unsigned int i;
#if MSX2_TEXT_8PX
    for (i = 0; i < MSX2_FONT_CHARS * 8; i++) {
        unsigned char row = raw[i];
        unsigned char *d = port_font_cells + i * 4;
        d[0] = (unsigned char)((row & 0x01 ? 0xF0 : 0)
                               | (row & 0x02 ? 0x0F : 0));
        d[1] = (unsigned char)((row & 0x04 ? 0xF0 : 0)
                               | (row & 0x08 ? 0x0F : 0));
        d[2] = (unsigned char)((row & 0x10 ? 0xF0 : 0)
                               | (row & 0x20 ? 0x0F : 0));
        d[3] = (unsigned char)((row & 0x40 ? 0xF0 : 0)
                               | (row & 0x80 ? 0x0F : 0));
    }
#else
    for (i = 0; i < MSX2_FONT_CHARS * 8; i++) {
        unsigned char row = raw[i] & 0x0F;
        unsigned char *d = port_font_cells + i * 2;
        d[0] = (unsigned char)((row & 0x08 ? 0xF0 : 0)
                               | (row & 0x04 ? 0x0F : 0));
        d[1] = (unsigned char)((row & 0x02 ? 0xF0 : 0)
                               | (row & 0x01 ? 0x0F : 0));
    }
#endif
}

#if N_SONGS > 0
static unsigned char song_buf[SONG_WS_SIZE];

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
    return song_buf;
}

void plat_music_hook(unsigned char on)
{
    (void)on;
}
#endif

void plat_init(void)
{
    plat_set_bank(MSX2_FONT_BANK);
    build_font_cells((const unsigned char *)0x8000);
    plat_set_bank(PORT_DATA_BANK);
    screen7();
    vdp_set_reg(7, 0);
    vdp_set_reg(14, 0);
    default_palette();
    plat_clear();
#if N_SONGS > 0
    ay_vt2_stop();
    im1_init();
    add_raster_int(music_isr);
#endif
}

void plat_clear(void)
{
    msx2_fill(0, 0, 512, MSX2_SCREEN_LINES, MSX2_TEXT_BG);
}

/* show_scene redraws the whole art band; only the title row and the text /
   inventory pane need clearing, which saves most of the VDP fill time. */
void plat_clear_text(void)
{
    msx2_fill(0, 0, 512, 8, MSX2_TEXT_BG);
    msx2_fill(0, (unsigned int)(1 + PORT_ART_ROWS) * 8, 512,
              (unsigned int)(MSX2_ROWS - 1 - PORT_ART_ROWS) * 8,
              MSX2_TEXT_BG);
}

/* Clear only the text pane below the art band, keeping the scene title (row 0)
   and the picture on rows 1..PORT_ART_ROWS. */
void plat_clear_pane(void)
{
    msx2_fill(0, (unsigned int)PORT_TEXT_TOP * 8, 512,
              (unsigned int)(MSX2_ROWS - PORT_TEXT_TOP) * 8,
              MSX2_TEXT_BG);
}

void plat_text_at(unsigned char row, unsigned char col, const char *s,
                  unsigned char color)
{
    unsigned char n = 0;
    if (row >= MSX2_ROWS)
        return;
    while (s[n] && col + n < PORT_COLS)
        n++;
    if (!n)
        return;
#if MSX2_TEXT_8PX
    msx2_text8(s,
               (unsigned int)row * 8 * MSX2_LINE + MSX2_TEXT_X / 2
               + (unsigned int)col * MSX2_CHAR_BYTES,
               n, (color == PLAT_COLOR_SEL)
               ? (MSX2_TEXT_HIGHLIGHT << 4) | MSX2_TEXT_HIGHLIGHT
               : (MSX2_TEXT_BODY << 4) | MSX2_TEXT_BODY);
#else
    msx2_text(s,
              (unsigned int)row * 8 * MSX2_LINE + MSX2_TEXT_X / 2
              + (unsigned int)col * MSX2_CHAR_BYTES,
              n, (color == PLAT_COLOR_SEL)
              ? (MSX2_TEXT_HIGHLIGHT << 4) | MSX2_TEXT_HIGHLIGHT
              : (MSX2_TEXT_BODY << 4) | MSX2_TEXT_BODY);
#endif
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
    unsigned char bank, strip;
    unsigned char *p;
    unsigned int len;
    if (id >= N_ART)
        return;
    plat_set_bank(PORT_DATA_BANK);
    bank = port_art_bank[id];
    plat_set_bank(bank);
    p = (unsigned char *)0x8000;
    set_palette(p);
    p += 32;
    for (strip = 0; strip < PORT_ART_ROWS; strip++) {
        len = (unsigned int)p[0] | ((unsigned int)p[1] << 8);
        p += 2;
        port_unpack(p, art_strip);
        msx2_vwrite(art_strip, MSX2_BAND_ADDR + strip * 2048, 2048);
        p += len;
    }
    /* Leave the scene/inventory bank selected: the engine reads its tables
       (scene offsets, item names, start flags) from it after drawing. */
    plat_set_bank(PORT_DATA_BANK);
#else
    (void)id;
#endif
}

/* SNSMAT ($0141) reads a keyboard matrix row: A selects the row and the
   returned bits are clear for pressed keys.  Interrupts are disabled so the
   BIOS keyboard ISR cannot switch the PPI row selection mid-read. */
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

/* Every key plat_read_key() consumes, by SNSMAT row/bit.  Waiting for these
   (instead of the joystick bits alone) keeps a held confirm key such as
   ENTER, which is not in joystick(1)'s row-8 mapping, from repeating into the
   next scene and selecting its first option. */
static unsigned char msx_keys_held(void)
{
    unsigned char held = 0;
    held |= (unsigned char)~msx_matrix(0) & 0x54;   /* 2 4 6 */
    held |= (unsigned char)~msx_matrix(1) & 0x01;   /* 8 */
    held |= (unsigned char)~msx_matrix(2) & 0x40;   /* A */
    held |= (unsigned char)~msx_matrix(3) & 0x02;   /* D */
#if N_SONGS > 0
    held |= (unsigned char)~msx_matrix(4) & 0x20;   /* P */
#endif
    held |= (unsigned char)~msx_matrix(5) & 0x11;   /* S W */
    held |= (unsigned char)~msx_matrix(7) & 0x80;   /* ENTER */
    held |= (unsigned char)~msx_matrix(8) & 0xF1;   /* SPACE, arrows */
    return held;
}

#if PORT_OVERLAY_MENU
/* GTTRIG(0) is the keyboard space bar.  z88dk keeps the BIOS wrappers in
   msxbios.lib, which this ROM2 link does not pull in, so call the BIOS entry
   directly (the same way screen7() does). */
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
    /* Check SPACE before the joystick bits so an emulator's keyboard-joystick
       mapping cannot turn it into the confirm button. */
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
#if N_SONGS > 0
        if (c == 'p' || c == 'P') {
            toggle_music();
            while (kbhit())
                getch();
            return 0;
        }
#endif
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

void plat_clear_row(unsigned char row)
{
    msx2_fill(0, (unsigned int)row * 8, 512, 8, MSX2_TEXT_BG);
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
        plat_set_bank(bank);
        port_unpack((const void *)(0x8000 + (unsigned int)off + 2), dst);
        plat_set_bank(PORT_DATA_BANK);
        return;
    }
    plat_set_bank(PORT_DATA_BANK);
    if (kind == PLAT_LOAD_INV)
        port_unpack(port_inv_data, dst);
    else
        port_unpack(port_scene_data + off, dst);
}
