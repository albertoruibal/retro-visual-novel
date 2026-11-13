/*
 * Game Boy Color APU stream player and UI audio support.
 *
 * tools/gbmusic.py converts a PT3 module to a stream of register commands:
 * the low byte of an APU register (0x10..0x3F) followed by its value, a wait
 * run 0x80 | (n - 1), an end marker 0x00 or a loop marker 0x01.  Each song is
 * stored at the start of one or more consecutive MBC1 banks, so the player
 * only has to advance the bank when the 0x4000 window wraps.
 *
 * Songs are streamed from ROM because a converted stream is much larger than
 * the Game Boy's 8K work RAM.  The vblank handler divides the ~59.7 Hz frame
 * rate down to the stream's 50 Hz; the player saves and restores the main
 * thread's ROM bank around its reads.
 *
 * The shared engine calls plat_sfx() for UI sounds; src/gb/gb_sfx.asm owns the
 * pulse-2 sequencer and snapshots the music registers while an effect plays.
 */

#include <gb/gb.h>
#include "plat.h"
#include "port_data.h"

#define CMD_END 0x00
#define CMD_LOOP 0x01
#define CMD_WAIT 0x80

volatile unsigned char gb_sfx_req;
unsigned short gb_sfx_ptr;
unsigned char gb_sfx_wait;
unsigned char gb_sfx_sh_vol;
unsigned char gb_sfx_sh_lo;
unsigned char gb_sfx_sh_hi;

extern void gb_sfx_tick(void) NONBANKED;

#if N_SONGS > 0
extern unsigned char port_bank_reg;

static unsigned char music_playing;
static unsigned char music_bank;
static unsigned char music_start_bank;
static unsigned short music_off;
static unsigned short music_start_off;
static unsigned char music_wait;
static unsigned char music_vbl_acc;

void gb_music_tick(void) NONBANKED;
#endif

static void music_silence(void) NONBANKED
{
    NR52_REG = 0x00;
}

static void music_init_apu(void) NONBANKED
{
    unsigned char i;

    music_silence();
    NR52_REG = 0x80;
    NR50_REG = 0x77;
    NR51_REG = 0xFF;
    NR11_REG = 0x80;
    NR21_REG = 0x80;
    NR30_REG = 0x80;
    for (i = 0; i < 8; i++) {
        *(volatile unsigned char *)(0xFF30 + i) = 0xFF;
        *(volatile unsigned char *)(0xFF38 + i) = 0x00;
    }
}

void gb_audio_ensure_on(void) NONBANKED
{
    if (!(NR52_REG & 0x80))
        music_init_apu();
}

void plat_sfx(unsigned char id) NONBANKED
{
    gb_sfx_req = (unsigned char)(id + 1);
}

#if N_SONGS > 0
static unsigned char music_byte(void) NONBANKED
{
    if (music_off >= 0x4000) {
        music_off = 0;
        music_bank++;
        plat_set_bank(music_bank);
    }
    return *(const unsigned char *)(0x4000 + music_off++);
}

void gb_music_play(unsigned char bank, unsigned short off) __smallc NONBANKED
{
    music_playing = 0;
    music_bank = bank;
    music_start_bank = bank;
    music_off = off;
    music_start_off = off;
    music_wait = 0;
    music_vbl_acc = 5;
    music_init_apu();
    music_playing = 1;
}

void gb_music_stop(void) __smallc NONBANKED
{
    music_playing = 0;
    music_wait = 0;
    music_silence();
}

void gb_music_tick(void) NONBANKED
{
    unsigned char prev, cmd, value;

    if (!music_playing)
        return;
    if (music_wait) {
        music_wait--;
        return;
    }
    prev = port_bank_reg;
    plat_set_bank(music_bank);
    for (;;) {
        cmd = music_byte();
        if (cmd == CMD_END) {
            music_playing = 0;
            music_silence();
            break;
        }
        if (cmd == CMD_LOOP) {
            music_bank = music_start_bank;
            music_off = music_start_off;
            plat_set_bank(music_bank);
            continue;
        }
        if (cmd >= CMD_WAIT) {
            music_wait = cmd & 0x7F;
            break;
        }
        if (cmd >= 0x10) {
            value = music_byte();
            *(volatile unsigned char *)(0xFF00 + cmd) = value;
        }
    }
    plat_set_bank(prev);
}

#endif

void gb_music_vbl(void) NONBANKED
{
#if N_SONGS > 0
    music_vbl_acc += 5;          /* 59.7 Hz -> ~50 Hz: play 5 of 6 frames */
    if (music_vbl_acc >= 6) {
        music_vbl_acc -= 6;
        gb_music_tick();
    }
#endif
    gb_sfx_tick();
}
