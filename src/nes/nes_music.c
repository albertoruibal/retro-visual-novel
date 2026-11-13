/*
 * NES APU music player front end.
 *
 * tools/nesmusic.py converts each PT3 module to a stream of APU register
 * writes.  Every song is stored raw in the PRG banks after the story bank;
 * nes_audio_tick.s (NMI) reads one 50 Hz frame at a time, briefly mapping the
 * song bank at $8000 and restoring bank 0 before returning.
 *
 * This file only runs on the main thread: it initialises the APU, starts and
 * stops a song, and owns the state shared with the NMI tick.  The NMI tick is
 * assembly because a cc65 C function would clobber the zero-page temporaries
 * and the soft stack of the interrupted main code.
 */
#include "plat.h"
#include "port_data.h"

#define APU(reg) (*(volatile unsigned char *)(0x4000 + (reg)))
#define APU_STATUS (*(volatile unsigned char *)0x4015)
#define APU_FRAME (*(volatile unsigned char *)0x4017)

unsigned char nes_music_playing;
unsigned char nes_music_bank;
unsigned short nes_music_off;
unsigned char nes_music_wait;
unsigned char nes_music_div;
unsigned char nes_music_sh_vol;
unsigned char nes_music_sh_lo;
unsigned char nes_music_sh_hi;
unsigned char nes_music_sh_valid;
unsigned char nes_sfx_request;

void nes_music_stop(void) __smallc;

void nes_music_stop(void) __smallc
{
    nes_music_playing = 0;
    nes_music_wait = 0;
    nes_music_sh_valid = 0;
    APU(0x00) = 0x30;
    APU(0x04) = 0x30;
    APU(0x08) = 0x00;
    APU(0x0C) = 0x30;
    APU_STATUS = 0x00;
}

void nes_music_play(unsigned char bank, unsigned short off) __smallc;

void nes_music_play(unsigned char bank, unsigned short off) __smallc
{
    nes_music_playing = 0;
    nes_music_bank = bank;
    nes_music_off = off;
    nes_music_wait = 0;
    nes_music_div = 5;
    nes_music_sh_valid = 0;
    APU(0x01) = 0x08;          /* sweep off on pulse 1 */
    APU(0x05) = 0x08;          /* sweep off on pulse 2 */
    APU_FRAME = 0x40;          /* 4-step frame counter, IRQ inhibited */
    APU_STATUS = 0x0F;         /* pulse 1/2, triangle and noise on */
    nes_music_playing = 1;
}

void plat_music_hook(unsigned char on)
{
    (void)on;
}
