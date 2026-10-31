/* Shared AY music player for the ZX, CPC and MSX2 targets. */
#include "port.h"

#if defined(N_SONGS) && N_SONGS > 0
#include <psg/vt2.h>

static unsigned char cur_song = SONG_NONE;
static unsigned char music_on = 1;

/* Stop the current module and, when the scene wants one, decode it into the
   platform's resident workspace and start the VT2 player. The platform hook
   installs/detaches the interrupt entry on ZX and is a no-op elsewhere. */
static void music_apply(void)
{
    unsigned char *ws;

    plat_music_hook(0);
    ay_vt2_stop();

    if (!(music_on && cur_song != SONG_NONE))
        return;

    ws = plat_song_ws();
    plat_load(song_bank[cur_song], song_off[cur_song], ws, PLAT_LOAD_SONG);
    ay_vt2_init((vt2_song *)ws);
    ay_vt2_start();
    plat_music_hook(1);
}

void set_music(unsigned char song)
{
    if (song == cur_song)
        return;
    cur_song = song;
    music_apply();
}

void toggle_music(void)
{
    music_on = !music_on;
    music_apply();
}
#endif
