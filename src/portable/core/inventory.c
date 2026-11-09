#include "port.h"

/* ------------------------------------------------------------- inventory */
void collect_items(void)
{
    unsigned char k;
    inv_nvis = 0;
    for (k = ITEM_BASE; k < ITEM_BASE + N_ITEMS; k++)
        if (flag_get(k))
            inv_vis[inv_nvis++] = k;
}


#if !PORT_OVERLAY_MENU
/* Two 4x8 console columns share one 8x8 attribute cell on the ZX/Next.  A
   selection marker placed just before an item can therefore share its cell
   with the previous item's last character; keep it in the body colour so the
   highlight does not leak into that character. */
static unsigned char inv_marker_color(unsigned char on)
{
#if PORT_MARKER_MATCH_CELL
    (void)on;
    return 0;
#else
    return on ? 1 : 0;
#endif
}

static unsigned char inv_fit(unsigned char from)
{
    unsigned char k, col = 2, n = 0;
    for (k = from; k < inv_nvis; k++) {
        const char *name = port_item_names
            + port_item_name_off[inv_vis[k] - ITEM_BASE];
        unsigned char len = name_len(name);
        if (col + len > PORT_INV_CONTENT_COLS)
            break;
        col += len + 1;
        n++;
    }
    return n;
}

void draw_inventory(void)
{
    unsigned char k, col, row = PLAT_ROWS - 1;
    PORT_PAGE_DATA();
    clear_row(row);
    collect_items();
    if (inv_cur != 0xFF && inv_cur >= inv_nvis)
        inv_cur = inv_nvis ? inv_nvis - 1 : 0;
    if (inv_cur == 0xFF || inv_cur < inv_first)
        inv_first = (inv_cur == 0xFF) ? 0 : inv_cur;
    inv_win = inv_fit(inv_first);
    while (inv_cur != 0xFF && inv_cur >= inv_first + inv_win) {
        inv_first++;
        inv_win = inv_fit(inv_first);
    }
    if (inv_first > 0)
        plat_text_at(row, 0, "<", 0);
    if (inv_first + inv_win < inv_nvis)
        plat_text_at(row, PORT_INV_MARK_R, ">", 0);
    col = 2;
    for (k = 0; k < inv_win; k++) {
        unsigned char id = inv_vis[inv_first + k];
        const char *name = port_item_names + port_item_name_off[id - ITEM_BASE];
        unsigned char len = name_len(name);
        char buf[PORT_COLS + 1];
        unsigned char i;
        for (i = 0; i < len && col + i < PORT_INV_MARK_R; i++)
            buf[i] = name[i];
        buf[i] = 0;
        {
            unsigned char sel = ((inv_first + k) == inv_cur);
            if (col > 1)
                plat_text_at(row, col - 1, sel ? ">" : " ",
                             inv_marker_color(sel));
            plat_text_at(row, col, buf, sel ? 1 : 0);
        }
        col += len + 1;
    }
#if PORT_MARKER_MATCH_CELL
    /* A later item's normal marker can share the selected name's last cell;
       repaint the selection so its highlight survives the full redraw. */
    if (inv_cur != 0xFF)
        inv_mark(inv_cur, 1);
#endif
}

/* Column where visible slot ``idx`` was drawn: walk the one-line layout from
   the window's first item, matching draw_inventory's ``len + 1`` spacing. */
static unsigned char inv_col_at(unsigned char idx)
{
    unsigned char k, col = 2;

    for (k = inv_first; k < idx; k++) {
        const char *name = port_item_names
            + port_item_name_off[inv_vis[k] - ITEM_BASE];
        col += name_len(name) + 1;
    }
    return col;
}

/* Repaint one band item in place (text colour normally, highlight with a '>'
   marker when selected). Unlike draw_inventory this never clears the bar, so
   moving within the window does not blank the whole line. */
void inv_mark(unsigned char idx, unsigned char on)
{
    unsigned char row = PLAT_ROWS - 1;
    unsigned char col = inv_col_at(idx);
    const char *name;
    char buf[PORT_COLS + 1];
    unsigned char i, len;

    PORT_PAGE_DATA();
    name = port_item_names + port_item_name_off[inv_vis[idx] - ITEM_BASE];
    len = name_len(name);
    for (i = 0; i < len && col + i < PORT_INV_MARK_R; i++)
        buf[i] = name[i];
    buf[i] = 0;
    if (col > 1)
        plat_text_at(row, col - 1, on ? ">" : " ", inv_marker_color(on));
    plat_text_at(row, col, buf, on ? 1 : 0);
}

/* Move the band cursor by ``dir``, wrapping at the ends.  When the move stays
   inside the visible window only the two affected names and their markers are
   repainted; when it leaves the window the band is redrawn so the window (and
   its '<'/'>' markers) shifts to keep the selection on screen. */
void inv_step(char dir)
{
    unsigned char prev, old_first;

    if (!inv_nvis)
        return;
    prev = inv_cur;
    old_first = inv_first;
    if (dir > 0)
        inv_cur = (inv_cur + 1 >= inv_nvis) ? 0 : inv_cur + 1;
    else
        inv_cur = (inv_cur == 0) ? inv_nvis - 1 : inv_cur - 1;
    if (inv_cur < inv_first) {
        inv_first = inv_cur;
        inv_win = inv_fit(inv_first);
    } else {
        while (inv_cur >= inv_first + inv_win) {
            inv_first++;
            inv_win = inv_fit(inv_first);
        }
    }
    if (inv_first != old_first) {
        draw_inventory();               /* window shifted: redraw + markers */
    } else {
        inv_mark(prev, 0);
        inv_mark(inv_cur, 1);
    }
}
#endif

/* --------------------------------------------------------------- items */
#if HAVE_INV_BLOB
static const char *inv_str(unsigned char k)
{
    return (const char *)inv_ws
        + (inv_ws[k * 2] | ((unsigned int)inv_ws[k * 2 + 1] << 8));
}

static const unsigned char *desc_next(const unsigned char **pp,
                                      unsigned char *ok)
{
    const unsigned char *s = line_text(*pp, ok);
    const unsigned char *q = s;
    while (*q)
        q++;
    *pp = q + 1;
    return s;
}

#if !PORT_NO_DESC_SCROLL && !PORT_NO_WRAP
static unsigned char desc_rows(unsigned char i)
{
    unsigned char nlines = inv_ws[4 + 2 * N_ITEMS + i];
    unsigned int off = inv_ws[4 + 2 * i]
        | ((unsigned int)inv_ws[5 + 2 * i] << 8);
    const unsigned char *p = inv_ws + off;
    unsigned char j, ok, rows;
    unsigned int total = 0;
    for (j = 0; j < nlines; j++) {
        const unsigned char *s = desc_next(&p, &ok);
        if (!ok)
            continue;
        rows = count_rows((const char *)s, PORT_DESC_WIDTH);
        total += rows;
    }
    return total > 255 ? 255 : (unsigned char)total;
}
#endif

static unsigned char show_desc(unsigned char i, unsigned char row,
                               unsigned char maxrows, unsigned char scroll)
{
    unsigned char nlines = inv_ws[4 + 2 * N_ITEMS + i];
    unsigned int off = inv_ws[4 + 2 * i]
        | ((unsigned int)inv_ws[5 + 2 * i] << 8);
    const unsigned char *p = inv_ws + off;
    unsigned char j, used = 0;
#if PORT_NO_WRAP
    (void)scroll;
    for (j = 0; j < nlines && used < maxrows; j++) {
        unsigned char ok;
        const unsigned char *s = desc_next(&p, &ok);
        if (!ok)
            continue;
        plat_text(row + used, 0, (const char *)s);
        used++;
    }
#else
    {
        char buf[PORT_COLS + 2];
        for (j = 0; j < nlines; j++) {
            unsigned char ok;
            const unsigned char *s = desc_next(&p, &ok);
            if (!ok)
                continue;
            while (*s) {
                text_next_segment((const char **)&s, PORT_DESC_WIDTH, buf);
                if (scroll) {
                    scroll--;
                } else if (used < maxrows) {
                    plat_text(row + used, 0, buf);
                    used++;
                } else {
                    return used;
                }
            }
        }
    }
#endif
    return used;
}

static unsigned char draw_desc(unsigned char i, unsigned char total,
                               unsigned char scroll, unsigned char rows)
{
    unsigned char j, used;
    for (j = 0; j < rows; j++)
        clear_row((unsigned char)(ITEM_TOP + 1 + j));
    if (!rows)
        return 0;
    used = show_desc(i, ITEM_TOP + 1, rows, scroll);
#if !PORT_NO_DESC_SCROLL && !PORT_NO_WRAP
    if (total > rows) {
        if (scroll)
            plat_text_at(ITEM_TOP + 1, PORT_SCROLL_COL, PORT_SCROLL_UP, 0);
        if (scroll + rows < total)
            plat_text_at(ITEM_TOP + rows, PORT_SCROLL_COL, PORT_SCROLL_DOWN, 0);
    }
#else
    (void)total;
    (void)scroll;
#endif
    return used;
}

static unsigned char draw_drop_entry(const char *label, unsigned char row,
                                     unsigned char on)
{
#if PORT_NO_WRAP || PORT_NO_ENTRY_WRAP
    plat_text_at(row, PORT_OPT_INDENT, label, on ? 1 : 0);
    print_option_marker(row, on);
    return 1;
#else
    unsigned char n = print_text_color(row, PORT_OPT_INDENT, label,
                                       PORT_OPT_WIDTH, on ? 1 : 0);
    print_option_marker(row, on);
    return n;
#endif
}

unsigned char drop_screen(unsigned char id)
{
    unsigned char i = id - ITEM_BASE;
    unsigned char sel = 0, nv = 0, nentries = 0, j, row;
    unsigned char first_entry, entry_rows = 0, maxdesc, desc_drawn;
#if !PORT_NO_DESC_SCROLL && !PORT_NO_WRAP
    unsigned char desc_total = 0, desc_scroll = 0;
#endif
    unsigned char entry_row[NOPT_MAX + 2];
    const char *labels[NOPT_MAX + 2];
#if HAVE_ITEM_OPTS
    unsigned char iopt[NOPT_MAX];
    PortItemOptHdr *oh;
#endif
    load_inv();
#if PORT_INV_OVERWRITES_ART && PORT_KEEP_ART
    cur_art = 0xFF;                     /* tiles replaced: redraw on return */
#endif
#if PORT_KEEP_ART || PORT_OVERLAY_MENU
    plat_clear_pane();
#else
    plat_clear();
#endif
    plat_text_at(ITEM_TOP, 0,
                    port_item_names + port_item_name_off[i],
                    PLAT_COLOR_TITLE);
#if HAVE_ITEM_OPTS
    {
        unsigned char nopt = inv_ws[4 + 5 * N_ITEMS + i];
        unsigned int ooff = inv_ws[4 + 3 * N_ITEMS + 2 * i]
            | ((unsigned int)inv_ws[5 + 3 * N_ITEMS + 2 * i] << 8);
        oh = (PortItemOptHdr *)(inv_ws + ooff);
        for (j = 0; j < nopt && nv < NOPT_MAX; j++) {
            PortItemOptHdr *o = &oh[j];
            if (o->scene != SCENE_NONE && o->scene != cur)
                continue;
            if (!opt_visible(inv_ws, o->cond_off, o->ncond, o->pick))
                continue;
            iopt[nv++] = j;
        }
    }
    for (j = 0; j < nv; j++)
        labels[j] = (const char *)(inv_ws + oh[iopt[j]].label_off);
#endif
    nentries = nv;
#if GAME_CARRY > 0
    labels[nentries++] = inv_str(0);    /* Drop */
#endif
    labels[nentries++] = inv_str(1);    /* Back */
#if PORT_NO_WRAP || PORT_NO_ENTRY_WRAP
    entry_rows = nentries;
#else
    /* Option labels wrap on the narrower portable screens; reserve their real
       row counts so the entries (and Back in particular) stay on screen. */
    for (j = 0; j < nentries; j++)
        entry_rows += count_rows(labels[j], PORT_OPT_WIDTH);
#endif
    /* Pin the entries to the bottom of the text pane, leaving the old
       inventory row free on the pinned layouts, and give the description the
       rows above.  The dialog layouts instead start the entries right below
       the description, so a short item screen has no empty gap. */
#if PORT_OVERLAY_MENU
    {
        unsigned char pane = (unsigned char)(ITEM_BOTTOM - ITEM_TOP);
        maxdesc = (entry_rows + 1 < pane)
            ? (unsigned char)(pane - entry_rows - 1) : 0;
    }
#else
    if (entry_rows < (unsigned char)(ITEM_BOTTOM - ITEM_TOP))
        first_entry = (unsigned char)(ITEM_BOTTOM - entry_rows);
    else
        first_entry = (unsigned char)(ITEM_TOP + 1);
    maxdesc = (first_entry > ITEM_TOP + 1)
        ? (unsigned char)(first_entry - ITEM_TOP - 1) : 0;
#endif
#if PORT_NO_DESC_SCROLL || PORT_NO_WRAP
    desc_drawn = draw_desc(i, 0, 0, maxdesc);
#else
    desc_total = maxdesc ? desc_rows(i) : 0;
    desc_drawn = draw_desc(i, desc_total, desc_scroll, maxdesc);
#endif
#if PORT_OVERLAY_MENU
    first_entry = (unsigned char)(ITEM_TOP + 1 + desc_drawn);
#else
    (void)desc_drawn;
#endif
    row = first_entry;
    for (j = 0; j < nentries; j++) {
        entry_row[j] = row;
        row += draw_drop_entry(labels[j], row, j == sel);
    }
    for (;;) {
        unsigned char k = 0;
        do {
            k = plat_read_key();
        } while (!k);
        plat_wait_release();
        if (k == CURSOR_UP) {
#if !PORT_NO_DESC_SCROLL && !PORT_NO_WRAP
            if (sel == 0 && desc_scroll) {
                desc_scroll--;
                draw_desc(i, desc_total, desc_scroll, maxdesc);
            } else
#endif
            if (sel > 0) {
                draw_drop_entry(labels[sel - 1], entry_row[sel - 1], 1);
                draw_drop_entry(labels[sel], entry_row[sel], 0);
                sel--;
            }
            continue;
        }
        if (k == CURSOR_DOWN) {
#if !PORT_NO_DESC_SCROLL && !PORT_NO_WRAP
            if (sel == 0 && maxdesc
                    && desc_scroll + maxdesc < desc_total) {
                desc_scroll++;
                draw_desc(i, desc_total, desc_scroll, maxdesc);
            } else
#endif
            if (sel + 1 < nentries) {
                draw_drop_entry(labels[sel + 1], entry_row[sel + 1], 1);
                draw_drop_entry(labels[sel], entry_row[sel], 0);
                sel++;
            }
            continue;
        }
#if PORT_OVERLAY_MENU
        if (k == CURSOR_MENU)
            return SCENE_NONE;
#endif
        if (k == CURSOR_ENTER) {
#if HAVE_ITEM_OPTS
            if (sel < nv) {
                PortItemOptHdr *o = &oh[iopt[sel]];
#if HAVE_MESSAGES
                if (o->msg_off)
                    show_message((const char *)inv_ws + o->msg_off);
#endif
                opt_apply(o->set, o->unset, o->pick, o->leave, o->clear);
                return o->target;
            }
#endif
#if GAME_CARRY > 0
            if (GAME_CARRY > 0 && sel == nv) {
                flag_set(id, 0);
                return SCENE_NONE;
            }
#endif
            return SCENE_NONE;
        }
    }
}
#endif
