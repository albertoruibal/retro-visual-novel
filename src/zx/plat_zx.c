/*
 * ZX Spectrum 128K platform layer for the shared portable core.
 *
 * The story engine (scenes, flags, options, words, inventory) now lives in
 * src/portable/core/.  This file supplies only the Spectrum side: NIRVANA+
 * art on 128K (a 1bpp monochrome renderer on 48K), the 64-column console,
 * direct row clears, blob loading, keyboard input, the boot password screen and
 * per-scene music.
 */
#include "engine.h"

#define ZX_KEY_UP IN_KEY_SCANCODE_7
#define ZX_KEY_DOWN IN_KEY_SCANCODE_6
#define ZX_KEY_LEFT IN_KEY_SCANCODE_5
#define ZX_KEY_RIGHT IN_KEY_SCANCODE_8

#ifndef ZX48
const unsigned char blank_tile[48];
#endif

static void set_colors(int ink, int paper, int bright)
{
    printf("\x10%c\x11%c\x13%c", '0' + ink, '0' + paper,
           '0' + (bright ? 1 : 0));
}

/* ZX attributes have one BRIGHT bit shared by ink and paper; gen_scenes emits
   TEXT_BG_BRIGHT as 0 for black, so a black background never forces bright. */
#define ZX_BG_ATTR ((unsigned char)((TEXT_BG_BRIGHT << 6) \
                                    | ((TEXT_BG & 7) << 3) | 7))

/* 48K art is 1bpp: bright white ink on black paper. */
#ifdef ZX48
#define ZX_ART_ATTR 0x47
#endif

#define set_text_colors(ink, bright) set_colors((ink), TEXT_BG, (bright))

static void text_at(unsigned char row, unsigned char col, const char *s)
{
    printf("\x16%c%c%s", row + 32, col + 32, s);
}

/* Clear one character row's pixels and attributes directly.  Printing a full
   line would wrap and make the ROM scroll the whole screen, which permanently
   shifts the NIRVANA+ background. */
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

void plat_text_at(unsigned char row, unsigned char col, const char *s,
                  unsigned char color)
{
    if (color == PLAT_COLOR_TITLE)
        set_text_colors(TITLE_INK, TITLE_BRIGHT);
    else if (color == PLAT_COLOR_SEL)
        set_text_colors(HIGHLIGHT_INK, HIGHLIGHT_BRIGHT);
    else
        set_text_colors(TEXT_INK, TEXT_BRIGHT);
    text_at(row, col, s);
}

void plat_load(unsigned char bank, unsigned short off, void *dst,
               unsigned char kind)
{
#ifndef ZX48
    /* The inventory blob decodes over art_ws, so the ISR's sprite slots must
       not read it mid-write.  Scene blobs do not touch the art workspace and
       must leave the current picture's tile pointer alone. */
    if (kind == PLAT_LOAD_INV)
        *(unsigned int *)NIRVANAP_TILE_IMAGES = (unsigned int)blank_tile;
    paged_unpack(bank, 0xC000 + (unsigned int)off, (unsigned int)dst);
#else
    (void)bank;
    if (kind == PLAT_LOAD_INV) {
        /* Inventory is compiled into the main image; scenes stay in the
           lower-RAM flat store. Both carry a u16 compressed-length prefix. */
        port_unpack((const void *)(inv_data + (unsigned int)off + 2u), dst);
    } else {
        port_unpack((const void *)(FLAT_DATA_ADDR + (unsigned int)off + 2u),
                    dst);
    }
#endif
}

void plat_draw_art(unsigned char id)
{
#if N_ART > 0
    if (id >= N_ART)
        id = 0;
#ifdef ZX48
    {
        unsigned char r, l, c;
        const unsigned char *src;

        /* Decode the compressed 1bpp band into art_ws, then copy whole rows
           into the Spectrum bitmap. art_off points at the [u16 length]
           prefix in art_data (all in the main image). */
        port_unpack((const void *)(art_data + (unsigned int)art_off[id] + 2u),
                    art_ws);
        for (r = 1; r <= ART_LINES; r++) {
            unsigned char *base = (unsigned char *)(0x4000
                + ((r >> 3) << 11) + ((r & 7) << 5));
            unsigned char *attr = (unsigned char *)(0x5800 + r * 32);
            for (l = 0; l < 8; l++) {
                src = art_ws + ((((unsigned int)r - 1u) * 8u + l) << 5);
                for (c = 0; c < 32; c++)
                    base[l * 256 + c] = src[c];
            }
            for (c = 0; c < 32; c++)
                attr[c] = ZX_ART_ATTR;
        }
    }
#else
    {
        unsigned char *buf;
        const unsigned char *map;
        const unsigned char *tiles;

        *(unsigned int *)NIRVANAP_TILE_IMAGES = (unsigned int)blank_tile;
        plat_load(art_bank[id], art_off[id], art_ws, PLAT_LOAD_SCENE);
        buf = art_ws;
        map = buf;
        tiles = buf + ART_MAP_LEN;
        *(unsigned int *)NIRVANAP_TILE_IMAGES = (unsigned int)tiles;
        for (unsigned char i = 0; i < ART_ROWS * ART_COLS; i++) {
            if ((i % 6) == 0)
                NIRVANAP_halt();
            NIRVANAP_drawT_raw(map[i], ART_LIN(i >> 4), (i & 15) << 1);
        }
    }
#endif
#else
    (void)id;
#endif
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
    /* _stage_ws occupies 0x6000..0x6000+STAGE_WS_SIZE. The song module lives
       directly after it, still in the always-mapped lower RAM, so it no longer
       competes with the engine for the crowded home bank. */
    return (unsigned char *)(0x6000 + STAGE_WS_SIZE);
}

/* Swap the NIRVANA+ ISR hook between "LD HL,0" and "CALL ay_vt2_play".  The
   halt before the placeholder keeps the engine's race in sync; on attach the
   target is written first so an interrupt never sees a half-set CALL. */
void plat_music_hook(unsigned char on)
{
    if (on) {
        NIRVANAP_ISR_HOOK[1] = (unsigned char)(unsigned int)ay_vt2_play;
        NIRVANAP_ISR_HOOK[2] = (unsigned char)((unsigned int)ay_vt2_play >> 8);
        NIRVANAP_ISR_HOOK[0] = 0xCD;            /* CALL */
        return;
    }
    NIRVANAP_halt();
    NIRVANAP_ISR_HOOK[0] = 0x21;                /* LD HL,0 (placeholder) */
    NIRVANAP_ISR_HOOK[1] = 0x00;
    NIRVANAP_ISR_HOOK[2] = 0x00;
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

/* Fill the raced art band (rows 1..ART_LINES) with black, same halt batching as
   plat_draw_art. */
static void fill_art_band_black(void)
{
#ifdef ZX48
    for (unsigned char r = 1; r <= ART_LINES; r++)
        zx_clr_row(r, ZX_ART_ATTR);
#else
    for (unsigned char i = 0; i < ART_ROWS * ART_COLS; i++) {
        if ((i % 6) == 0)
            NIRVANAP_halt();
        NIRVANAP_fillT_raw(0, ART_LIN(i >> 4), (i & 15) << 1);
    }
#endif
}

static unsigned char up_ascii(unsigned char c)
{
    return (c >= 'a' && c <= 'z') ? (unsigned char)(c - 32) : c;
}

static void password_screen(void)
{
    unsigned char buf[PW_MAX + 1];
    unsigned char n, i, ok;
    unsigned char tlen = 0;

    fill_art_band_black();
    plat_clear_text();

    while (game_title[tlen])
        tlen++;
    plat_text_at(PORT_TEXT_TOP,
                 (tlen < 60) ? (unsigned char)((60 - tlen) / 2) : 0,
                 game_title, PLAT_COLOR_TITLE);

    set_text_colors(7, 0);
    text_at(PORT_TEXT_TOP + 1, 0, game_password_label);

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
            set_text_colors(7, n ? 1 : 0);
            text_at(PORT_TEXT_TOP + 2, 2, (const char *)buf);
        }

        ok = (n > 0) && (game_password[n] == 0);
        for (i = 0; i < n && ok; i++)
            if (up_ascii(buf[i]) != up_ascii(game_password[i]))
                ok = 0;
        if (ok)
            return;

        set_text_colors(2, 1);
        text_at(PORT_TEXT_TOP + 3, 0, "Wrong password. Try again.");
    }
}
#endif

#if NEED_PASSWORD
void plat_boot(void)
{
    if (game_password[0])
        password_screen();
}
#endif

void plat_init(void)
{
    zx_border(0);

#ifndef NO_TAPE_LOADER
    load_banks();
#endif

#ifndef ZX48
    NIRVANAP_start();
    *(unsigned int *)NIRVANAP_TILE_IMAGES = (unsigned int)blank_tile;
#else
    for (unsigned char r = 1; r <= ART_LINES; r++)
        zx_clr_row(r, ZX_ART_ATTR);
#endif

#if NEED_ACCENT_FONT
    {
        unsigned char *font = crt_font64();
        unsigned char i, j;
        for (i = 0; i < N_ACCENT_GLYPHS; i++) {
            unsigned short off = adventure_font_slots[i];
            for (j = 0; j < 8; j++)
                font[off + j] = adventure_font_glyphs[i * 8 + j];
        }
        console_ioctl(IOCTL_GENCON_SET_FONT64, &font);
    }
#endif

    zx_clr_row(PLAT_ROWS - 1, ZX_BG_ATTR);
    zx_clr_row(0, ZX_BG_ATTR);
#if N_SONGS > 0
    ay_vt2_stop();
#endif
}
