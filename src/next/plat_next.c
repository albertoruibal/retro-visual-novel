/*
 * ZX Spectrum Next platform layer for the shared portable core.
 *
 * Text and the inventory band use the ULA (the same 64-column console as the
 * ZX target), while the picture is a Layer 2 band clipped to character rows
 * 1..ART_ROWS.  Scene, inventory and song blobs live in Next 16K banks and
 * are decoded with the vendored ZX0 decoder.
 */
#include <stdio.h>
#include <string.h>
#include <input.h>
#include <arch/zx/zx_input.h>
#include <sys/ioctl.h>
#include <psg/vt2.h>
#include <sys/compiler.h>
#include "plat.h"
#include "port_data.h"

#define ZX_KEY_UP IN_KEY_SCANCODE_7
#define ZX_KEY_DOWN IN_KEY_SCANCODE_6
#define ZX_KEY_LEFT IN_KEY_SCANCODE_5
#define ZX_KEY_RIGHT IN_KEY_SCANCODE_8

#define NEXT_EXT_KEYS_0 0xB0
#define NEXT_EXT_UP 0x08
#define NEXT_EXT_DOWN 0x04
#define NEXT_EXT_LEFT 0x02
#define NEXT_EXT_RIGHT 0x01

extern void nextreg(unsigned int regval) __z88dk_fastcall;
extern unsigned char nextreg_get(unsigned char reg) __z88dk_fastcall;
extern void paged_next_unpack(unsigned int bank, unsigned int src,
                              unsigned int dst);
extern void next_isr_install(void);
extern unsigned char next_isr_hook[];
extern unsigned char next_font[768];

#define ZX_BG_ATTR ((unsigned char)((PORT_TEXT_BG_BRIGHT << 6) \
                                    | ((PORT_TEXT_BG & 7) << 3) | 7))

static void border(unsigned char colour) __z88dk_fastcall
{
    #asm
    ld a,l
    out ($fe),a
    #endasm
}

static void zx_clr_row(unsigned char r, unsigned char attr_val)
{
    unsigned char *base = (unsigned char *)(0x4000
        + ((r >> 3) << 11) + ((r & 7) << 5));
    unsigned char *attr = (unsigned char *)(0x5800 + r * 32);
    for (unsigned char k = 0; k < 8; k++)
        for (unsigned char c = 0; c < 32; c++)
            base[k * 256 + c] = 0;
    for (unsigned char c = 0; c < 32; c++)
        attr[c] = attr_val;
}

void plat_clear_row(unsigned char row)
{
    zx_clr_row(row, ZX_BG_ATTR);
}

static void clear_text_rows(void)
{
    for (unsigned char r = PORT_TEXT_TOP; r <= PLAT_ROWS - 2; r++)
        zx_clr_row(r, ZX_BG_ATTR);
}

void plat_clear(void)
{
    for (unsigned char r = 0; r < PLAT_ROWS; r++)
        zx_clr_row(r, ZX_BG_ATTR);
}

void plat_clear_text(void)
{
    zx_clr_row(0, ZX_BG_ATTR);
    clear_text_rows();
#if PORT_OVERLAY_MENU
    zx_clr_row(PLAT_ROWS - 1, ZX_BG_ATTR);
#endif
}

void plat_clear_pane(void)
{
    clear_text_rows();
    zx_clr_row(PLAT_ROWS - 1, ZX_BG_ATTR);
}

static void draw_char(unsigned char row, unsigned char col,
                      unsigned char ch, unsigned char ink,
                      unsigned char bright)
{
    const unsigned char *glyph;
    unsigned char *base;
    unsigned char *dst;
    unsigned char *attr;
    unsigned char i;
    unsigned char bits;

    if (row >= PLAT_ROWS || col >= PORT_COLS || ch < 32 || ch > 127)
        return;
    glyph = next_font + (unsigned int)(ch - 32) * 8;
    base = (unsigned char *)(0x4000 + ((row >> 3) << 11)
                             + ((row & 7) << 5));
    dst = base + (col >> 1);
    attr = (unsigned char *)(0x5800 + row * 32);
    attr[col >> 1] = (unsigned char)((ink & 7)
                                     | ((PORT_TEXT_BG & 7) << 3)
                                     | ((bright || PORT_TEXT_BG_BRIGHT) ? 0x40 : 0));
    for (i = 0; i < 8; i++) {
        bits = glyph[i];
        if (col & 1)
            *dst = (unsigned char)((*dst & 0xF0) | (bits & 0x0F));
        else
            *dst = (unsigned char)((*dst & 0x0F) | ((bits & 0xF0)));
        dst += 256;
    }
}

void plat_text_at(unsigned char row, unsigned char col, const char *s,
                  unsigned char color)
{
    unsigned char ink, bright;
    unsigned char n = 0;
    if (color == PLAT_COLOR_TITLE) {
        ink = PORT_TITLE_INK;
        bright = PORT_TITLE_BRIGHT;
    } else if (color == PLAT_COLOR_SEL) {
        ink = PORT_HIGHLIGHT_INK;
        bright = PORT_HIGHLIGHT_BRIGHT;
    } else {
        ink = PORT_TEXT_INK;
        bright = PORT_TEXT_BRIGHT;
    }
    while (s[n] && col + n < PORT_COLS) {
        draw_char(row, (unsigned char)(col + n), (unsigned char)s[n],
                  ink, bright);
        n++;
    }
}

void plat_text(unsigned char row, unsigned char col, const char *s)
{
    plat_text_at(row, col, s, PLAT_COLOR_BODY);
}

void plat_text_color(unsigned char row, unsigned char col, const char *s,
                     unsigned char color)
{
    plat_text_at(row, col, s, color);
}

void plat_set_bank(unsigned char bank) __z88dk_fastcall
{
    (void)bank;
}

void plat_load(unsigned char bank, unsigned short off, void *dst,
               unsigned char kind)
{
    (void)kind;
    paged_next_unpack(bank, 0xC000 + (unsigned int)off, (unsigned int)dst);
}

static void upload_palette(unsigned char bank, unsigned short off)
{
    const unsigned char *p;
    unsigned int i;

    #asm
    di
    #endasm
    nextreg((0x56 << 8) | (unsigned char)(bank * 2));
    nextreg((0x57 << 8) | (unsigned char)(bank * 2 + 1));
    p = (const unsigned char *)(0xC000 + off);
    nextreg((0x43 << 8) | 0x10);      /* Layer 2 first palette, auto-inc */
    nextreg((0x40 << 8) | 0x00);      /* index 0 */
    for (i = 0; i < 256; i++) {
        nextreg((0x44 << 8) | p[i * 2]);
        nextreg((0x44 << 8) | p[i * 2 + 1]);
    }
    nextreg((0x56 << 8) | 0);         /* restore bank 0 */
    nextreg((0x57 << 8) | 1);
    #asm
    ei
    #endasm
}

void plat_draw_art(unsigned char id)
{
#if N_ART > 0
    unsigned char last;
    if (id >= N_ART)
        id = 0;
    nextreg((0x70 << 8) | 0x00);      /* 256x192x8, palette offset 0 */
    nextreg((0x15 << 8) | 0x00);      /* S L U: Layer 2 over ULA */
    nextreg((0x69 << 8) | 0x80);      /* enable Layer 2 */
    nextreg((0x12 << 8) | port_art_bank[id]);
    upload_palette(port_art_pal_bank[id], port_art_pal_off[id]);
    last = (unsigned char)(8 * (PORT_ART_ROWS + 1) - 1);
    nextreg((0x1c << 8) | 0x01);      /* reset Layer 2 clip index */
    nextreg((0x18 << 8) | 0);
    nextreg((0x18 << 8) | 255);
    nextreg((0x18 << 8) | 8);         /* character row 1 */
    nextreg((0x18 << 8) | last);
#else
    (void)id;
#endif
}

static unsigned char pad_dirs(void)
{
    unsigned char ext = nextreg_get(NEXT_EXT_KEYS_0);
    unsigned int joy = in_JoyKempston();
    unsigned char k = 0;

    if ((ext & NEXT_EXT_UP) || (joy & in_UP)) k |= in_UP;
    if ((ext & NEXT_EXT_DOWN) || (joy & in_DOWN)) k |= in_DOWN;
    if ((ext & NEXT_EXT_LEFT) || (joy & in_LEFT)) k |= in_LEFT;
    if ((ext & NEXT_EXT_RIGHT) || (joy & in_RIGHT)) k |= in_RIGHT;
    if (joy & in_FIRE) k |= in_FIRE;
    return k;
}

unsigned char plat_read_key(void)
{
    for (;;) {
        if (in_KeyPressed(IN_KEY_SCANCODE_p)) {
#if N_SONGS > 0
            toggle_music();
#endif
            plat_wait_release();
            continue;
        }
        if (in_KeyPressed(ZX_KEY_UP) ||
            in_KeyPressed(IN_KEY_SCANCODE_w)) return 1;
        if (in_KeyPressed(ZX_KEY_DOWN) ||
            in_KeyPressed(IN_KEY_SCANCODE_s)) return 2;
        if (in_KeyPressed(IN_KEY_SCANCODE_ENTER)) return 3;
#if PORT_OVERLAY_MENU
        if (in_KeyPressed(IN_KEY_SCANCODE_SPACE)) return PORT_KEY_MENU;
#endif
        if (in_KeyPressed(ZX_KEY_LEFT) ||
            in_KeyPressed(IN_KEY_SCANCODE_a)) return 6;
        if (in_KeyPressed(ZX_KEY_RIGHT) ||
            in_KeyPressed(IN_KEY_SCANCODE_d)) return 7;
        {
            unsigned char pad = pad_dirs();
            if (pad & in_UP) return 1;
            if (pad & in_DOWN) return 2;
            if (pad & in_LEFT) return 6;
            if (pad & in_RIGHT) return 7;
            if (pad & in_FIRE) return 3;
        }
        #asm
        halt
        #endasm
    }
}

void plat_wait_release(void)
{
    while (in_KeyPressed(ZX_KEY_UP) ||
           in_KeyPressed(ZX_KEY_DOWN) ||
           in_KeyPressed(ZX_KEY_LEFT) ||
           in_KeyPressed(ZX_KEY_RIGHT) ||
           in_KeyPressed(IN_KEY_SCANCODE_w) ||
           in_KeyPressed(IN_KEY_SCANCODE_a) ||
           in_KeyPressed(IN_KEY_SCANCODE_s) ||
           in_KeyPressed(IN_KEY_SCANCODE_d) ||
           in_KeyPressed(IN_KEY_SCANCODE_p) ||
           pad_dirs() ||
#if PORT_OVERLAY_MENU
           in_KeyPressed(IN_KEY_SCANCODE_SPACE) ||
#endif
           in_KeyPressed(IN_KEY_SCANCODE_ENTER)) {
        #asm
        halt
        #endasm
    }
}

#if N_SONGS > 0
unsigned char *plat_song_ws(void)
{
    return (unsigned char *)(0x6000 + STAGE_WS_SIZE);
}

void plat_music_hook(unsigned char on)
{
    if (on) {
        next_isr_hook[0] = 0xCD;      /* call ay_vt2_play */
        next_isr_hook[1] = (unsigned char)(unsigned int)ay_vt2_play;
        next_isr_hook[2] = (unsigned char)((unsigned int)ay_vt2_play >> 8);
        return;
    }
    next_isr_hook[0] = 0xC9;          /* ret */
}
#endif

void plat_scene_entered(unsigned char id)
{
#if N_SONGS > 0
    set_music(scene_song[id]);
#else
    (void)id;
#endif
}

#if NEED_PASSWORD
#define PW_MAX 16

static unsigned char up_ascii(unsigned char c)
{
    return (c >= 'a' && c <= 'z') ? (unsigned char)(c - 32) : c;
}

static void password_screen(void)
{
    unsigned char buf[PW_MAX + 1];
    unsigned char n, i, ok;
    unsigned char tlen = 0;

    nextreg((0x69 << 8) | 0x00);      /* hide Layer 2 during the prompt */
    plat_clear_text();

    while (port_game_title[tlen])
        tlen++;
    plat_text_at(PORT_TEXT_TOP,
                 (tlen < 60) ? (unsigned char)((60 - tlen) / 2) : 0,
                 port_game_title, PLAT_COLOR_TITLE);

    plat_text_at(PORT_TEXT_TOP + 1, 0, port_game_password_label,
                 PLAT_COLOR_BODY);

    for (;;) {
        n = 0;
        buf[0] = 0;
        for (;;) {
            unsigned int k;
            do {
                k = in_Inkey();
            } while (!k);
            in_WaitForNoKey();
            if (k == 13)
                break;
            if ((k == 12 || k == 8) && n)
                n--;
            else if (k >= 32 && k < 127 && n < PW_MAX)
                buf[n++] = (unsigned char)k;
            else
                continue;
            buf[n] = 0;
            zx_clr_row(PORT_TEXT_TOP + 2, ZX_BG_ATTR);
            plat_text_at(PORT_TEXT_TOP + 2, 2, (const char *)buf,
                         PLAT_COLOR_BODY);
        }

        ok = (n > 0) && (port_game_password[n] == 0);
        for (i = 0; i < n && ok; i++)
            if (up_ascii(buf[i]) != up_ascii(port_game_password[i]))
                ok = 0;
        if (ok)
            return;

        plat_text_at(PORT_TEXT_TOP + 3, 0, "Wrong password. Try again.",
                     PLAT_COLOR_SEL);
    }
}

void plat_boot(void)
{
    if (port_game_password[0])
        password_screen();
}
#endif

void plat_init(void)
{
    border(0);
    nextreg((0x70 << 8) | 0x00);
    nextreg((0x15 << 8) | 0x00);
    nextreg((0x69 << 8) | 0x00);      /* Layer 2 starts hidden */

    {
        unsigned char *font = next_font;
#if NEED_ACCENT_FONT
        unsigned char i, j;
#endif
        #asm
        di
        #endasm
        nextreg((0x56 << 8) | (unsigned char)(NEXT_FONT_BANK * 2));
        nextreg((0x57 << 8) | 1);
        memcpy(font, (const void *)0xC000, 768);
#if NEED_ACCENT_FONT
        for (i = 0; i < N_ACCENT_GLYPHS; i++) {
            const unsigned char *slotp =
                (const unsigned char *)(0xC000 + 768 + i * 2);
            unsigned short off = (unsigned short)(slotp[0] | (slotp[1] << 8));
            const unsigned char *glyphp =
                (const unsigned char *)(0xC000 + 768 + N_ACCENT_GLYPHS * 2
                                        + i * 8);
            for (j = 0; j < 8; j++)
                font[off + j] = glyphp[j];
        }
#endif
        nextreg((0x56 << 8) | 0);
        nextreg((0x57 << 8) | 1);
        #asm
        ei
        #endasm
    }

    plat_clear();
    ay_vt2_stop();
#if N_SONGS > 0
    next_isr_install();
#endif
}
