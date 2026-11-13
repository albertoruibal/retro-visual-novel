/* Shared music player: AY VT2 on ZX/CPC/MSX2, SN76489 PSGlib on SMS, the APU
   stream player on Game Boy Color and the banked APU player on NES. */
#include "port.h"

#if defined(N_SONGS) && N_SONGS > 0
#ifndef PORT_MUSIC_PSG
#define PORT_MUSIC_PSG 0
#endif
#ifndef PORT_MUSIC_GB
#define PORT_MUSIC_GB 0
#endif
#ifndef PORT_MUSIC_NES
#define PORT_MUSIC_NES 0
#endif
#if PORT_MUSIC_PSG
extern void sms_psg_play(void *song) __smallc;
extern void sms_psg_stop(void) __smallc;
#elif PORT_MUSIC_GB
extern void gb_music_play(unsigned char bank, unsigned short off) __smallc;
extern void gb_music_stop(void) __smallc;
#elif PORT_MUSIC_NES
extern void nes_music_play(unsigned char bank, unsigned short off) __smallc;
extern void nes_music_stop(void) __smallc;
#else
#include <psg/vt2.h>
#endif

static unsigned char cur_song = SONG_NONE;
static unsigned char music_on = 1;

/* Stop the current module and, when the scene wants one, start the platform
   player.  GB and NES stream the converted song straight from banked ROM; the
   AY/PSG targets decode it into a resident workspace first. */
static void music_apply(void)
{
#if !PORT_MUSIC_GB && !PORT_MUSIC_NES
    unsigned char *ws;
#endif

    plat_music_hook(0);
#if PORT_MUSIC_PSG
    sms_psg_stop();
#elif PORT_MUSIC_GB
    gb_music_stop();
#elif PORT_MUSIC_NES
    nes_music_stop();
#else
    ay_vt2_stop();
#endif

    if (!(music_on && cur_song != SONG_NONE))
        return;

#if PORT_MUSIC_GB
    gb_music_play(song_bank[cur_song], song_off[cur_song]);
#elif PORT_MUSIC_NES
    nes_music_play(song_bank[cur_song], song_off[cur_song]);
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
