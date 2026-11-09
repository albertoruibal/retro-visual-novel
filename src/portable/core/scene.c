#include "port.h"

/* --------------------------------------------------------------- scenes */
unsigned char collect_options(void)
{
    PortSceneHdr *sc = (PortSceneHdr *)scene_ws;
    unsigned char n = 0, i;
    for (i = 0; i < NOPT_MAX && i < sc->nopt; i++) {
        PortOptHdr *o = &sc->opts[i];
        if (o->next == SCENE_NONE)
            continue;
        if (!opt_visible(scene_ws, o->cond_off, o->ncond, o->pick))
            continue;
        opt_idx[n] = i;
#if !PORT_OVERLAY_MENU
#if PORT_SIMPLE_OPTIONS
        opt_nrows[n] = 1;
#else
        opt_nrows[n] = count_rows(
            (const char *)scene_ws + o->label_off, PORT_OPT_WIDTH);
#endif
#endif
        n++;
    }
    return n;
}

unsigned char show_scene(unsigned char id)
{
    PortSceneHdr *sc;
    unsigned char navail, i;
#if !PORT_OVERLAY_MENU
    unsigned char row;
    unsigned char optrows = 0, invrow = PLAT_ROWS - 1;
#endif
    load_scene(id);
    sc = (PortSceneHdr *)scene_ws;
    flag_set(sc->ending, 1);
    plat_scene_entered(id);
#if PORT_KEEP_ART
    if (sc->art != cur_art) {
        plat_draw_art(sc->art);
        cur_art = sc->art;
#if !PORT_ART_CLEARS_TEXT
        plat_clear_text();
#endif
    } else {
        plat_clear_text();
    }
#else
    plat_clear();
    plat_draw_art(sc->art);
#endif
    {
        char title[PORT_COLS + 1];
        const char *t = (const char *)scene_ws + sc->title_off;
        unsigned char n = 0;
        while (t[n] && n < PORT_COLS)
            n++;
        for (i = 0; i < n; i++)
            title[i] = t[i];
        title[n] = 0;
        plat_text_at(PORT_TITLE_ROW, 0, title, PLAT_COLOR_TITLE);
    }
    navail = collect_options();
    text_top = PORT_TEXT_TOP;
#if PORT_OVERLAY_MENU
    /* The text owns every row below the art; the options and held items live
       in the A-button overlay instead of a reserved menu area. */
    text_rows = (unsigned char)(PLAT_ROWS - text_top);
#else
    for (i = 0; i < navail; i++)
        optrows += opt_nrows[i];
    if (optrows < (unsigned char)(invrow - text_top))
        row = invrow - optrows;
    else if (optrows <= invrow)
        /* More option rows than the text pane has: start them above the pane
           so the last entry does not land on the inventory row. The text
           keeps a single scrolling row. */
        row = (unsigned char)(invrow - optrows);
    else
        row = 0;
    text_rows = (row > text_top) ? (unsigned char)(row - text_top) : 1;
#endif
    text_scroll = 0;
    scroll_max = 0;
    text_fresh = 1;
    render_text();
    if (text_total > text_rows)
        scroll_max = (unsigned char)(text_total - text_rows);
#if !PORT_OVERLAY_MENU
    for (i = 0; i < navail; i++) {
        opt_row[i] = row;
#if PORT_SIMPLE_OPTIONS
        print_option_simple(row, (const char *)scene_ws
                            + sc->opts[opt_idx[i]].label_off, 0);
#else
        print_option(row, (const char *)scene_ws
                     + sc->opts[opt_idx[i]].label_off, 0);
#endif
        row += opt_nrows[i];
    }
#endif
#if !PORT_NO_TEXT_SCROLL
    draw_scroll_markers();
#endif
#if !PORT_OVERLAY_MENU
    inv_cur = 0xFF;
    inv_first = 0;
    draw_inventory();
#endif
    return navail;
}
