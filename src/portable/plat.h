/* Small platform surface shared by the ZX Spectrum and portable runtimes. */
#ifndef PORT_PLAT_H
#define PORT_PLAT_H

#include <sys/compiler.h>

#ifndef PLAT_ROWS
#define PLAT_ROWS 24
#endif

/* Extra key code: the overlay-menu/back button (GB B, SMS button 1,
   CPC/MSX SPACE). */
#define PORT_KEY_MENU 8

/* Text colour slots understood by every platform.  The title slot is the
   scene/item heading: the ZX uses its `## zx title_ink` (default: body
   colour), while the portable targets use their body colour. */
#define PLAT_COLOR_BODY 0
#define PLAT_COLOR_SEL 1
#define PLAT_COLOR_TITLE 2

void plat_init(void);
/* Optional once-per-boot screen (the ZX password prompt); a no-op elsewhere. */
void plat_boot(void);
void plat_clear(void);
void plat_clear_text(void);
void plat_clear_pane(void);
void plat_clear_row(unsigned char row);
void plat_text(unsigned char row, unsigned char col, const char *s);
void plat_text_color(unsigned char row, unsigned char col, const char *s,
                     unsigned char color);
void plat_text_at(unsigned char row, unsigned char col, const char *s,
                  unsigned char color);
void plat_draw_art(unsigned char id);
/* Load a scene/inventory/song blob from ``bank`` at ``off`` into ``dst``.  The
   platform owns the storage model: 0xC000 paging on the Spectrum, a mapper
   window on SMS/CPC/MSX/GB, or a plain array on a non-banked target. */
#define PLAT_LOAD_SCENE 0
#define PLAT_LOAD_INV 1
#define PLAT_LOAD_SONG 2
void plat_load(unsigned char bank, unsigned short off, void *dst,
               unsigned char kind);
/* Called after a scene is loaded (selects the per-scene song). */
void plat_scene_entered(unsigned char id);
/* Shared music player hooks: the workspace is target-owned, and ``hook``
   attaches/detaches the interrupt entry (ZX's NIRVANA+) or does nothing when
   the interrupt is installed once in plat_init(). */
unsigned char *plat_song_ws(void);
void plat_music_hook(unsigned char on);
void set_music(unsigned char song);
void toggle_music(void);
void plat_set_bank(unsigned char bank) __z88dk_fastcall;
unsigned char plat_read_key(void);
void plat_wait_release(void);

#endif
