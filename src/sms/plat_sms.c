#include <arch/sms.h>
#include <rect.h>
#include <input.h>
#include <arch/sms/PSGlib.h>
#include "plat.h"
#include "port_data.h"
#include "port_font8.h"

static unsigned int text_row[PORT_COLS];

volatile unsigned char sms_music_enabled = 0;
volatile unsigned char sms_music_region = 0x40;
volatile unsigned char sms_music_acc = 0;
extern unsigned char sms_detect_region(void) __smallc;

#if N_SONGS > 0
static unsigned char song_buf[SONG_WS_SIZE];
extern volatile unsigned char _SMSlib_PauseRequested;
#endif

/* SN76489 PSG SFX streams.  Each byte is sent straight to the PSG by
   PSGlib's SFX frame reader: a latched value (>= 0x80) or a data byte
   (0x40 | value), 0x38 | n waits n extra frames and 0x00 ends the effect.
   The effects mirror the NES UI sounds on tone channel 2 (0xCn tone,
   0xDn volume), which PSGlib restores for the music when the stream ends. */
static const unsigned char sms_sfx_move[] = {
    0xD0, 0xCF, 0x47, 0x39,
    0xDF, 0x39,
    0x00
};
static const unsigned char sms_sfx_confirm[] = {
    0xD0, 0xCB, 0x46, 0x3A,
    0xC5, 0x45, 0x3A,
    0xDF, 0x39,
    0x00
};
static const unsigned char sms_sfx_back[] = {
    0xD0, 0xC5, 0x45, 0x3A,
    0xCB, 0x46, 0x3A,
    0xDF, 0x39,
    0x00
};
static const unsigned char sms_sfx_pick[] = {
    0xD0, 0xCF, 0x47, 0x39,
    0xCB, 0x46, 0x39,
    0xC5, 0x45, 0x3A,
    0xDF, 0x39,
    0x00
};
static const unsigned char sms_sfx_drop[] = {
    0xD0, 0xC5, 0x45, 0x39,
    0xCB, 0x46, 0x39,
    0xCF, 0x47, 0x3A,
    0xDF, 0x39,
    0x00
};
static const unsigned char sms_sfx_error[] = {
    0xD0, 0xC0, 0x43, 0x3B,
    0xCC, 0x43, 0x3B,
    0xDF, 0x39,
    0x00
};
static const unsigned char *const sms_sfx_table[PLAT_SFX_COUNT] = {
    sms_sfx_move, sms_sfx_confirm, sms_sfx_back,
    sms_sfx_pick, sms_sfx_drop, sms_sfx_error
};

void plat_sfx(unsigned char id)
{
    if (id >= PLAT_SFX_COUNT)
        return;
    #asm
    di
    #endasm
    PSGSFXPlay((void *)sms_sfx_table[id], SFX_CHANNEL2);
    #asm
    ei
    #endasm
}

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
    sms_music_region = sms_detect_region();
    sms_music_enabled = (N_SONGS > 0);
    sms_vdp_feature_enable(VDP_FEATURE_VBLANK_INTERRUPT);
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
    unsigned int k;
#if N_SONGS > 0
    if (_SMSlib_PauseRequested) {
        _SMSlib_PauseRequested = 0;
        toggle_music();
        return 0;
    }
#endif
    k = in_stick_1();
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
#if N_SONGS > 0
    set_music(scene_song[id]);
#else
    (void)id;
#endif
}

#if N_SONGS > 0
unsigned char *plat_song_ws(void)
{
    return song_buf;
}

void plat_music_hook(unsigned char on)
{
    sms_music_enabled = on;
}
#endif

extern void port_unpack(const void *src, void *dst) __smallc;

void plat_load(unsigned char bank, unsigned short off, void *dst,
               unsigned char kind)
{
    if (kind == PLAT_LOAD_SONG) {
#if N_SONGS > 0
        MM_FFFF = bank;
        port_unpack((const void *)(0x8000 + (unsigned int)off + 2), dst);
        MM_FFFF = 0;
#else
        (void)bank;
        (void)off;
        (void)dst;
#endif
        return;
    }
    if (kind == PLAT_LOAD_INV)
        port_unpack(port_inv_data, dst);
    else
        port_unpack(port_scene_data + off, dst);
}
