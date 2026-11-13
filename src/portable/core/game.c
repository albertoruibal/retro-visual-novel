#include "port.h"

/* --------------------------------------------------------------- flags */
unsigned char flag_get(unsigned char id)
{
    return (id == FLAG_NONE) ? 0 : (flags[id >> 3] >> (id & 7)) & 1;
}

void flag_set(unsigned char id, unsigned char v)
{
    if (id == FLAG_NONE)
        return;
    if (v)
        flags[id >> 3] |= 1 << (id & 7);
    else
        flags[id >> 3] &= ~(1 << (id & 7));
}

void reset_game(void)
{
    PORT_PAGE_DATA();
    memset(flags, 0, sizeof(flags));
#if N_START > 0
    {
        unsigned char i;
        for (i = 0; i < N_START; i++)
            flag_set(port_start_flags[i], 1);
    }
#endif
}

static unsigned char cond_ok(const unsigned char *p, unsigned char n)
{
    while (n--) {
        unsigned char ok = flag_get(p[0]);
        if (p[1])
            ok = !ok;
        if (!ok)
            return 0;
        p += 2;
    }
    return 1;
}

#if GAME_CARRY > 0
static unsigned char count_items(void)
{
    unsigned char n = 0, id;
    for (id = ITEM_BASE; id < ITEM_BASE + N_ITEMS; id++)
        if (flag_get(id))
            n++;
    return n;
}
#endif

unsigned char opt_visible(const unsigned char *blob,
                                 unsigned int cond_off, unsigned char ncond,
                                 unsigned char pick)
{
    if (ncond && !cond_ok(blob + cond_off, ncond))
        return 0;
    if (pick != FLAG_NONE && flag_get(pick))
        return 0;
#if GAME_CARRY > 0
    if (pick != FLAG_NONE && count_items() >= GAME_CARRY)
        return 0;
#endif
    return 1;
}

void opt_apply(unsigned char set_, unsigned char unset,
                      unsigned char pick, unsigned char leave,
                      unsigned char clear)
{
#if PORT_SFX
    unsigned char picked = (pick != FLAG_NONE && !flag_get(pick));
    unsigned char dropped = (leave != FLAG_NONE && flag_get(leave));
#endif
    if (clear & 1)
        reset_game();
    flag_set(set_, 1);
    flag_set(unset, 0);
    flag_set(pick, 1);
    flag_set(leave, 0);
#if PORT_SFX
    if (picked)
        SFX(PLAT_SFX_PICK);
    else if (dropped)
        SFX(PLAT_SFX_DROP);
    else
        SFX(PLAT_SFX_CONFIRM);
#endif
}

void load_scene(unsigned char id)
{
    if (id >= N_SCENES)
        id = 0;
    /* MSX2 keeps the scene table in a paged ROM bank and the previous scene
       may have left an art bank selected, so page the data bank in before
       reading the offset. */
    PORT_PAGE_DATA();
#if PORT_BANKED_SCENES
    plat_load(port_scene_bank[id], port_scene_off[id], scene_ws,
              PLAT_LOAD_SCENE);
#else
    plat_load(0, port_scene_off[id], scene_ws, PLAT_LOAD_SCENE);
#endif
    PORT_PAGE_DATA();
}

#if HAVE_INV_BLOB
void load_inv(void)
{
#if PORT_BANKED_SCENES
    plat_load(port_inv_bank, port_inv_off, inv_ws, PLAT_LOAD_INV);
#else
    plat_load(0, 0, inv_ws, PLAT_LOAD_INV);
#endif
    PORT_PAGE_DATA();
}
#endif

/* A stored line is [u8 ncond][(flag id, negated) * ncond]text\0. */
const unsigned char *line_text(const unsigned char *s,
                                      unsigned char *visible)
{
    unsigned char n = *s++;
    unsigned char ok = 1, i;
    for (i = 0; i < n; i++) {
        unsigned char v = flag_get(s[0]);
        if (s[1])
            v = !v;
        if (!v)
            ok = 0;
        s += 2;
    }
    *visible = ok;
    return s;
}
