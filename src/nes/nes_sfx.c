/*
 * NES UI sound effects.
 *
 * The shared engine calls plat_sfx() for cursor moves, confirmations, item
 * pickups/drops, backing out and blocked moves.  The actual APU work happens
 * in nes_audio_tick.s during the NMI, where it can overlay a short pulse-2
 * sequence on top of the music without disturbing the song's other channels.
 * This file only records the request.
 */
#include "plat.h"
#include "port_data.h"

extern unsigned char nes_sfx_request;

void plat_sfx(unsigned char id)
{
    if (id >= PLAT_SFX_COUNT)
        return;
    *(volatile unsigned char *)0x4005 = 0x08;  /* pulse-2 sweep off */
    *(volatile unsigned char *)0x4017 = 0x40;  /* 4-step, IRQ inhibited */
    *(volatile unsigned char *)0x4015 = 0x0F;
    nes_sfx_request = (unsigned char)(id + 1);
}
