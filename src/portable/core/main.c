#include "port.h"

#if defined(__CC65__)
int main(void)
#else
void main(void)
#endif
{
    plat_init();
    reset_game();
    cur = 0;
    plat_boot();
    for (;;) {
        unsigned char navail = show_scene(cur);
        unsigned char next;
#if !PORT_OVERLAY_MENU
#if HAVE_INV_BLOB
        if (!navail && !word_count && !inv_nvis) {
#else
        if (!navail && !word_count) {
#endif
            for (;;)
                plat_wait_release();
        }
#endif
        next = choose_option(navail);
        if (next != SCENE_NONE)
            cur = next;
        /* SCENE_NONE means "stay here" (an item screen just closed). */
    }
#if defined(__CC65__)
    return 0;
#endif
}
