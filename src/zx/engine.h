#ifndef ZX_ENGINE_H
#define ZX_ENGINE_H

#include <stdio.h>
#include <string.h>
#include <input.h>
#include <sys/ioctl.h>
#include <arch/zx.h>
#ifndef ZX48
#include <arch/zx/nirvana+.h>
#include <psg/vt2.h>
#endif
#include "port.h"

/* Paged data and the art workspace live in the ZX assembly files. */
extern unsigned char art_ws[];
extern void paged_unpack(unsigned int bank, unsigned int src,
                         unsigned int dst);
#ifndef NO_TAPE_LOADER
extern void load_banks(void);
#endif
#if N_SONGS > 0
extern const unsigned char song_bank[];
extern const unsigned short song_off[];
void set_music(unsigned char song);
void toggle_music(void);
#endif
#if NEED_ACCENT_FONT
extern const unsigned short adventure_font_slots[];
extern const unsigned char adventure_font_glyphs[];
extern unsigned char *crt_font64(void);
#endif

#define ART_COLS 16
#define ART_ROWS (ART_LINES / 2)
#define ART_LIN(r) ((r) * 16 + 16)

#endif
