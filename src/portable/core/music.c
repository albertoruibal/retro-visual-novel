/* Shared music player: AY VT2 on ZX/CPC/MSX2, SN76489 PSGlib on SMS and
   the APU stream player on Game Boy Color. */
#include "port.h"

#if defined(N_SONGS) && N_SONGS > 0
#ifndef PORT_MUSIC_PSG
#define PORT_MUSIC_PSG 0
#endif
#ifndef PORT_MUSIC_GB
#define PORT_MUSIC_GB 0
#endif
#if PORT_MUSIC_PSG
extern void sms_psg_play(void *song) __smallc;
extern void sms_psg_stop(void) __smallc;
#elif PORT_MUSIC_GB
extern void gb_music_play(unsigned char bank, unsigned short off) __smallc;
extern void gb_music_stop(void) __smallc;
#else
#include <psg/vt2.h>
#endif

static unsigned char cur_song = SONG_NONE;
static unsigned char music_on = 1;

/* Stop the current module and, when the scene wants one, decode it into the
   platform's resident workspace and start the platform player. The platform
   hook installs/detaches the interrupt entry on ZX and gates the SMS ISR. */
static void music_apply(void)
{
#if !PORT_MUSIC_GB
    unsigned char *ws;
#endif

    plat_music_hook(0);
#if PORT_MUSIC_PSG
    sms_psg_stop();
#elif PORT_MUSIC_GB
    gb_music_stop();
#else
    ay_vt2_stop();
#endif

    if (!(music_on && cur_song != SONG_NONE))
        return;

#if PORT_MUSIC_GB
    gb_music_play(song_bank[cur_song], song_off[cur_song]);
#else
    ws = plat_song_ws();
    plat_load(song_bank[cur_song], song_off[cur_song], ws, PLAT_LOAD_SONG);
#if PORT_MUSIC_PSG
    sms_psg_play(ws);
#else
    ay_vt2_init((vt2_song *)ws);
    ay_vt2_start();
#endif
#endif
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
