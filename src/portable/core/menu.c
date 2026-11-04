#include "port.h"

#if HAVE_MESSAGES
/* Modal interstitial used by an option's `msg` text.  It owns the text pane
   (the art and title stay visible), then any recognised adventure key returns
   to the caller, which applies the option's effects and follows its target. */
void show_message(const char *text)
{
    unsigned char top = PORT_TEXT_TOP;
    unsigned char hint_row = (unsigned char)(PLAT_ROWS - 1);
    unsigned char body_rows = (unsigned char)(hint_row - top);
    unsigned int first = 0;
    for (;;) {
        const char *p = text;
        char buf[PORT_COLS + 2];
        unsigned int row = 0, r = 0, scroll_max;
        unsigned char k;
        plat_clear_pane();
        while (*p) {
            text_next_segment(&p, PORT_TEXT_WIDTH, buf);
            if (r >= first && row < body_rows) {
                plat_text_at((unsigned char)(top + row), 0, buf,
                             PLAT_COLOR_BODY);
                row++;
            }
            r++;
        }
        scroll_max = (r > body_rows) ? r - body_rows : 0;
        if (first > scroll_max)
            first = scroll_max;
        if (scroll_max) {
            if (first)
                plat_text_at(top, PORT_SCROLL_COL, PORT_SCROLL_UP,
                             PLAT_COLOR_BODY);
            if (first < scroll_max)
                plat_text_at((unsigned char)(hint_row - 1), PORT_SCROLL_COL,
                             PORT_SCROLL_DOWN, PLAT_COLOR_BODY);
        }
        plat_text_at(hint_row, 0, ">", PLAT_COLOR_SEL);
        plat_text_at(hint_row, 2, port_game_popup_hint, PLAT_COLOR_SEL);
        do {
            k = plat_read_key();
        } while (!k);
        plat_wait_release();
        if (scroll_max) {
            if (k == CURSOR_UP && first) {
                first--;
                continue;
            }
            if (k == CURSOR_DOWN && first < scroll_max) {
                first++;
                continue;
            }
        }
        break;
    }
}
#endif

#if !PORT_OVERLAY_MENU
static void mark_option(unsigned char k, unsigned char on)
{
    PortSceneHdr *sc = (PortSceneHdr *)scene_ws;
#if PORT_SIMPLE_OPTIONS
    print_option_simple(opt_row[k],
                        (const char *)scene_ws
                        + sc->opts[opt_idx[k]].label_off, on);
#else
    print_option(opt_row[k],
                 (const char *)scene_ws + sc->opts[opt_idx[k]].label_off, on);
#endif
}
#endif

#if HAVE_WORDS
static unsigned char word_flag_of(unsigned char k)
{
    PortSceneHdr *sc = (PortSceneHdr *)scene_ws;
    PortWordHdr *words = (PortWordHdr *)(scene_ws + sc->words_off);
    return words[word_sel[k]].flag;
}

#if PORT_MARKER_MATCH_CELL
/* Two 4x8 console columns share one 8x8 attribute cell.  Return non-zero if a
   still-selectable word covers column ``c`` of ``row`` so the cursor marker
   can keep the colour already in that half-cell. */
static unsigned char word_covers(unsigned char row, unsigned char c)
{
    unsigned char i;
    for (i = 0; i < word_count; i++)
        if (word_row[i] == row && c >= word_col[i]
                && c - word_col[i] < word_len[i])
            return 1;
    return 0;
}
#endif

static void mark_word(unsigned char k, unsigned char on)
{
    char buf[PORT_COLS + 2];
    unsigned char n = word_len[k], i, row, marker_color = 1;
    unsigned char maxn = PORT_TEXT_WIDTH - word_col[k];
    if (word_row[k] < text_scroll
            || word_row[k] >= text_scroll + text_rows)
        return;
    if (n > maxn)
        n = maxn;
    for (i = 0; i < n; i++)
        buf[i] = word_ptr[k][i];
    buf[n] = 0;
    row = text_top + word_row[k] - text_scroll;
    if (word_col[k]) {
#if PORT_MARKER_MATCH_CELL
        if (!word_covers(row, (unsigned char)((word_col[k] - 1) ^ 1)))
            marker_color = 0;
#endif
        if (on) {
            plat_text_at(row, word_col[k] - 1, ">", marker_color);
        } else {
            char prev[2];
            prev[0] = (char)word_prev[k];
            prev[1] = 0;
            plat_text_at(row, word_col[k] - 1, prev, marker_color);
        }
    }
    plat_text_at(row, word_col[k], buf, 1);
}

static void ensure_word_visible(unsigned char k)
{
#if PORT_NO_TEXT_SCROLL
    (void)k;
#else
    if (word_row[k] < text_scroll)
        text_scroll = word_row[k];
    else if (word_row[k] >= text_scroll + text_rows)
        text_scroll = (unsigned char)(word_row[k] - text_rows + 1);
    else
        return;
    if (text_scroll > scroll_max)
        text_scroll = scroll_max;
    render_text();
    draw_scroll_markers();
#endif
}
#endif

#if !PORT_OVERLAY_MENU
static void mark_item(unsigned char sel, unsigned char on)
{
#if HAVE_WORDS
    if (sel < word_count) {
        if (on)
            ensure_word_visible(sel);
        mark_word(sel, on);
        return;
    }
#endif
    mark_option((unsigned char)(sel - word_count), on);
}
#endif

#if !PORT_OVERLAY_MENU
unsigned char choose_option(unsigned char navail)
{
    unsigned char sel = word_count, on_inv = 0;
    unsigned char total = (unsigned char)(word_count + navail);
    if (!total) {
#if HAVE_INV_BLOB
        if (!inv_nvis)
            return SCENE_NONE;
        on_inv = 1;
        inv_cur = 0;
        if (inv_first != 0)
            draw_inventory();
        else
            inv_mark(0, 1);
#else
        return SCENE_NONE;
#endif
    }
    if (!on_inv) {
        if (sel >= total)               /* words only: start on the first word */
            sel = 0;
        mark_item(sel, 1);
    }
    for (;;) {
        unsigned char k = 0;
        do {
            k = plat_read_key();
        } while (!k);
        plat_wait_release();
        if (on_inv) {
            if (k == CURSOR_UP && inv_cur > 0) {
                inv_step(-1);
            } else if (k == CURSOR_UP && total) {
                inv_mark(inv_cur, 0);
                inv_cur = 0xFF;
                on_inv = 0;
                mark_item(sel, 1);
            } else if (k == CURSOR_DOWN || k == CURSOR_RIGHT) {
                inv_step(1);
            } else if (k == CURSOR_LEFT) {
                inv_step(-1);
            } else if (k == CURSOR_ENTER && inv_nvis) {
#if HAVE_INV_BLOB
                return drop_screen(inv_vis[inv_cur]);
#endif
                return SCENE_NONE;
            }
            continue;
        }
#if !PORT_NO_TEXT_SCROLL
        if (k == CURSOR_LEFT) {
            if (text_scroll) {
                text_scroll--;
                render_text();
                draw_scroll_markers();
                mark_item(sel, 1);
            }
            continue;
        }
        if (k == CURSOR_RIGHT) {
            if (text_scroll < scroll_max) {
                text_scroll++;
                render_text();
                draw_scroll_markers();
                mark_item(sel, 1);
            }
            continue;
        }
#endif
        if (k == CURSOR_UP) {
            if (sel > 0) {
                mark_item(sel, 0);
                sel--;
                mark_item(sel, 1);
            }
        } else if (k == CURSOR_DOWN) {
            if (sel + 1 < total) {
                mark_item(sel, 0);
                sel++;
                mark_item(sel, 1);
            } else if (inv_nvis) {
                mark_item(sel, 0);
                on_inv = 1;
                inv_cur = 0;
                if (inv_first != 0)
                    draw_inventory();       /* reset a scrolled window */
                else
                    inv_mark(0, 1);
            }
        } else if (k == CURSOR_ENTER) {
#if HAVE_WORDS
            if (sel < word_count) {
                flag_set(word_flag_of(sel), 1);
                return SCENE_NONE;
            }
#endif
            {
                PortOptHdr *o = &((PortSceneHdr *)scene_ws)
                    ->opts[opt_idx[sel - word_count]];
#if HAVE_MESSAGES
                if (o->msg_off)
                    show_message((const char *)scene_ws + o->msg_off);
#endif
                opt_apply(o->set, o->unset, o->pick, o->leave, o->clear);
                return o->next;
            }
        }
    }
}
#else
static void redraw_text_pane(void)
{
    plat_clear_pane();
    text_fresh = 1;
    render_text();
    scroll_max = (text_total > text_rows)
        ? (unsigned char)(text_total - text_rows) : 0;
    if (text_scroll > scroll_max) {
        text_scroll = scroll_max;
        render_text();
    }
#if !PORT_NO_TEXT_SCROLL
    draw_scroll_markers();
#endif
}

static const char *menu_label(unsigned char nopt, unsigned char i)
{
    if (i < nopt)
        return (const char *)scene_ws
            + ((PortSceneHdr *)scene_ws)->opts[opt_idx[i]].label_off;
    return port_item_names
        + port_item_name_off[inv_vis[i - nopt] - ITEM_BASE];
}

static unsigned char menu_entry_rows(unsigned char nopt, unsigned char i)
{
#if PORT_NO_WRAP
    (void)nopt;
    (void)i;
    return 1;
#else
    unsigned char width = PORT_OPT_WIDTH;
    if (i >= nopt)
        width = (unsigned char)(width - 2);
    return count_rows(menu_label(nopt, i), width);
#endif
}

/* Keep the selected entry (and its wrapped lines) inside the pane. */
static void menu_clamp(unsigned char nopt, unsigned char sel,
                       unsigned char *first)
{
    unsigned int rows;
    unsigned char i;
    if (*first > sel)
        *first = sel;
    for (;;) {
        rows = 0;
        for (i = *first; i <= sel; i++)
            rows += menu_entry_rows(nopt, i);
        if (rows <= text_rows || *first >= sel)
            break;
        (*first)++;
    }
}

static unsigned char draw_menu_entry(unsigned char nopt, unsigned char i,
                                     unsigned char row, unsigned char on)
{
    unsigned char col = PORT_OPT_INDENT;
    unsigned char width = PORT_OPT_WIDTH;
    const char *label = menu_label(nopt, i);

    print_option_marker(row, on);
    if (i >= nopt) {
        plat_text_at(row, PORT_OPT_INDENT, "*", on ? 1 : 0);
        col = (unsigned char)(PORT_OPT_INDENT + 2);
        width = (unsigned char)(width - 2);
    }
    return print_text_color(row, col, label, width, on ? 1 : 0);
}

static void draw_menu_move(unsigned char nopt, unsigned char first,
                           unsigned char prev, unsigned char sel)
{
    unsigned char row = text_top, j;
    unsigned char last = (prev > sel) ? prev : sel;
    for (j = first; j <= last; j++) {
        if (j == prev)
            draw_menu_entry(nopt, j, row, 0);
        if (j == sel)
            draw_menu_entry(nopt, j, row, 1);
        row = (unsigned char)(row + menu_entry_rows(nopt, j));
    }
}

static void draw_menu(unsigned char nopt, unsigned char total,
                      unsigned char sel, unsigned char first)
{
    unsigned char i, row = text_top;
    plat_clear_pane();
    for (i = first; i < total && row < PLAT_ROWS; i++)
        row = (unsigned char)(row + draw_menu_entry(nopt, i, row, i == sel));
    if (first)
        plat_text_at(text_top, PORT_SCROLL_COL, PORT_SCROLL_UP, 0);
    if (i < total)
        plat_text_at(PLAT_ROWS - 1, PORT_SCROLL_COL, PORT_SCROLL_DOWN, 0);
}

static unsigned char menu_screen(void)
{
    unsigned char nopt = collect_options();
    unsigned char total, sel = 0, first = 0, first_drawn, prev, k;
    collect_items();
    total = nopt;
#if HAVE_INV_BLOB
    total = (unsigned char)(nopt + inv_nvis);
#endif
    if (!total)
        return SCENE_NONE;
    menu_clamp(nopt, sel, &first);
    draw_menu(nopt, total, sel, first);
    first_drawn = first;
    for (;;) {
        do {
            k = plat_read_key();
        } while (!k);
        plat_wait_release();
        if (k == CURSOR_MENU)
            return SCENE_NONE;
        if (k == CURSOR_UP || k == CURSOR_DOWN) {
            if ((k == CURSOR_UP && sel)
                    || (k == CURSOR_DOWN && sel + 1 < total)) {
                prev = sel;
                if (k == CURSOR_UP)
                    sel--;
                else
                    sel++;
                menu_clamp(nopt, sel, &first);
                if (first != first_drawn) {
                    draw_menu(nopt, total, sel, first);
                    first_drawn = first;
                } else {
                    draw_menu_move(nopt, first, prev, sel);
                }
            }
        } else if (k == CURSOR_ENTER) {
            if (sel < nopt) {
                PortOptHdr *o = &((PortSceneHdr *)scene_ws)->opts[opt_idx[sel]];
#if HAVE_MESSAGES
                if (o->msg_off)
                    show_message((const char *)scene_ws + o->msg_off);
#endif
                opt_apply(o->set, o->unset, o->pick, o->leave, o->clear);
                return o->next;
            }
#if HAVE_INV_BLOB
            return drop_screen(inv_vis[sel - nopt]);
#else
            return SCENE_NONE;
#endif
        }
    }
}

unsigned char choose_option(unsigned char navail)
{
    unsigned char sel = 0, k;
    (void)navail;
#if HAVE_WORDS
    if (word_count)
        mark_word(0, 1);
#else
    (void)sel;
#endif
    for (;;) {
        do {
            k = plat_read_key();
        } while (!k);
        plat_wait_release();
        if (k == CURSOR_MENU) {
            unsigned char next = menu_screen();
            if (next != SCENE_NONE)
                return next;
#if PORT_INV_OVERWRITES_ART && PORT_KEEP_ART
            /* The item screen shared the art workspace; let show_scene()
               restore the picture and text from scratch. */
            if (cur_art == 0xFF)
                return SCENE_NONE;
#endif
            redraw_text_pane();
#if HAVE_WORDS
            if (word_count) {
                if (sel >= word_count)
                    sel = (unsigned char)(word_count - 1);
                ensure_word_visible(sel);
                mark_word(sel, 1);
            }
#endif
            continue;
        }
#if !PORT_NO_TEXT_SCROLL
        if (scroll_max && (k == CURSOR_UP || k == CURSOR_DOWN)) {
            if (k == CURSOR_UP && text_scroll) {
                text_scroll--;
                render_text();
                draw_scroll_markers();
#if HAVE_WORDS
                if (word_count)
                    mark_word(sel, 1);
#endif
            } else if (k == CURSOR_DOWN && text_scroll < scroll_max) {
                text_scroll++;
                render_text();
                draw_scroll_markers();
#if HAVE_WORDS
                if (word_count)
                    mark_word(sel, 1);
#endif
            }
            continue;
        }
#endif
        if (k == CURSOR_UP) {
#if HAVE_WORDS
            if (sel) {
                mark_word(sel, 0);
                sel--;
                ensure_word_visible(sel);
                mark_word(sel, 1);
            }
#endif
        } else if (k == CURSOR_DOWN) {
#if HAVE_WORDS
            if (sel + 1 < word_count) {
                mark_word(sel, 0);
                sel++;
                ensure_word_visible(sel);
                mark_word(sel, 1);
            }
#endif
        } else if (k == CURSOR_LEFT) {
#if HAVE_WORDS
            if (word_count) {
                if (sel) {
                    mark_word(sel, 0);
                    sel--;
                    ensure_word_visible(sel);
                    mark_word(sel, 1);
                }
            }
#if !PORT_NO_TEXT_SCROLL
            else if (text_scroll) {
                text_scroll--;
                render_text();
                draw_scroll_markers();
            }
#endif
#else
#if !PORT_NO_TEXT_SCROLL
            if (text_scroll) {
                text_scroll--;
                render_text();
                draw_scroll_markers();
            }
#endif
#endif
        } else if (k == CURSOR_RIGHT) {
#if HAVE_WORDS
            if (word_count) {
                if (sel + 1 < word_count) {
                    mark_word(sel, 0);
                    sel++;
                    ensure_word_visible(sel);
                    mark_word(sel, 1);
                }
            }
#if !PORT_NO_TEXT_SCROLL
            else if (text_scroll < scroll_max) {
                text_scroll++;
                render_text();
                draw_scroll_markers();
            }
#endif
#else
#if !PORT_NO_TEXT_SCROLL
            if (text_scroll < scroll_max) {
                text_scroll++;
                render_text();
                draw_scroll_markers();
            }
#endif
#endif
#if HAVE_WORDS
        } else if (k == CURSOR_ENTER && word_count) {
            flag_set(word_flag_of(sel), 1);
            return SCENE_NONE;
#endif
        }
    }
}
#endif
