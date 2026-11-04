#include "port.h"

unsigned char name_len(const char *s)
{
    unsigned char n = 0;
    while (s[n] && n < PORT_COLS)
        n++;
    return n;
}

#if (!PORT_OVERLAY_MENU && !PORT_SIMPLE_OPTIONS) || PORT_OVERLAY_MENU \
        || !PORT_NO_ENTRY_WRAP
/* Print ``s`` at (row,col), wrapping at ``width`` columns.  Returns rows used. */
unsigned char print_text_color(unsigned char row, unsigned char col,
                                      const char *s, unsigned char width,
                                      unsigned char color)
{
    unsigned char start = row;
    unsigned int guard = 0;
    char buf[PORT_COLS + 2];
    while (*s && row < PLAT_ROWS) {
        if (++guard > 200)
            break;
        unsigned char n = 0, last = 0, i;
        while (s[n] && n < width) {
            if (s[n] == ' ')
                last = n;
            n++;
        }
        if (s[n] && last)
            n = last;
        if (!n)
            n = 1;
        for (i = 0; i < n; i++)
            buf[i] = s[i];
        buf[n] = 0;
        plat_text_at(row, col, buf, color);
        s += n;
        while (*s == ' ')
            s++;
        row++;
    }
    return (unsigned char)(row - start);
}
#endif

#if !PORT_NO_WRAP || HAVE_MESSAGES
/* Take the next wrapped segment of ``s`` (same rules as print_text). */
void text_next_segment(const char **ps, unsigned char width, char *buf)
{
    const char *s = *ps;
    unsigned char n = 0, last = 0, i;
    while (s[n] && n < width) {
        if (s[n] == ' ')
            last = n;
        n++;
    }
    if (s[n] && last)
        n = last;
    if (!n)
        n = 1;
    for (i = 0; i < n; i++)
        buf[i] = s[i];
    buf[n] = 0;
    s += n;
    while (*s == ' ')
        s++;
    *ps = s;
}

#if !PORT_NO_WRAP && ((!PORT_OVERLAY_MENU && !PORT_SIMPLE_OPTIONS) \
        || PORT_OVERLAY_MENU || !PORT_NO_DESC_SCROLL || !PORT_NO_ENTRY_WRAP)
unsigned char count_rows(const char *s, unsigned char width)
{
    char buf[PORT_COLS + 2];
    unsigned char n = 0;
    unsigned int guard = 0;
    while (*s) {
        if (++guard > 200)
            break;
        text_next_segment(&s, width, buf);
        n++;
    }
    return n;
}
#endif
#endif

void render_text(void)
{
    PortSceneHdr *sc = (PortSceneHdr *)scene_ws;
#if HAVE_WORDS
    PortWordHdr *words = (PortWordHdr *)(scene_ws + sc->words_off);
#endif
    unsigned char i, vrow = 0;
    word_count = 0;

#if PORT_NO_WRAP
    /* Platforms that pre-wrap their stored lines draw them directly; the
       editor/build supplies rows that already fit the target width. */
    if (text_fresh)
        text_fresh = 0;
    else
        for (i = 0; i < text_rows; i++)
            clear_row(text_top + i);
    for (unsigned char r = 0; r < 8; r++) {
        const unsigned char *s;
        unsigned char visible;
        if (!sc->text_off[r])
            continue;
        s = (const unsigned char *)scene_ws + sc->text_off[r];
        s = line_text(s, &visible);
        if (!visible)
            continue;
        if (vrow >= text_scroll && vrow < text_scroll + text_rows)
            plat_text(text_top + vrow - text_scroll, 0,
                      (const char *)s);
#if HAVE_WORDS
        {
            unsigned char wi;
            for (wi = 0; wi < sc->nwords && wi < WORD_MAX; wi++) {
                PortWordHdr *wh = &words[wi];
                if (wh->line != r || flag_get(wh->flag))
                    continue;
                if (word_count < WORD_MAX
                        && vrow >= text_scroll
                        && vrow < text_scroll + text_rows) {
                    unsigned char idx = word_count++;
                    word_sel[idx] = wi;
                    word_row[idx] = vrow;
                    word_col[idx] = wh->col;
                    word_len[idx] = wh->len;
                    word_ptr[idx] = (const char *)s + wh->col;
                    word_prev[idx] = wh->col
                        ? ((const char *)s)[wh->col - 1] : 0;
                }
            }
        }
#endif
        vrow++;
    }
    text_total = vrow;
#else
    char buf[PORT_COLS + 2];
    unsigned int guard = 0;
    if (text_fresh)
        text_fresh = 0;
    else
        for (i = 0; i < text_rows; i++)
            clear_row(text_top + i);
    for (unsigned char r = 0; r < 8; r++) {
        const unsigned char *s, *line_start;
        unsigned char visible, pos = 0;
        if (!sc->text_off[r])
            continue;
        s = (const unsigned char *)scene_ws + sc->text_off[r];
        s = line_text(s, &visible);
        if (!visible)
            continue;
        line_start = s;
        while (*s) {
            const unsigned char *before = s;
            unsigned char consumed;
            if (++guard > 300)
                break;
            text_next_segment((const char **)&s, PORT_TEXT_WIDTH, buf);
            consumed = (unsigned char)((const unsigned char *)s - before);
#if HAVE_WORDS
            {
                unsigned char wi;
                for (wi = 0; wi < sc->nwords && wi < WORD_MAX; wi++) {
                    PortWordHdr *wh = &words[wi];
                    if (wh->line != r || flag_get(wh->flag))
                        continue;
                    if (wh->col >= pos && wh->col < pos + consumed
                            && word_count < WORD_MAX
#if PORT_NO_TEXT_SCROLL
                            && vrow >= text_scroll
                            && vrow < text_scroll + text_rows
#endif
                            ) {
                        unsigned char idx = word_count++;
                        word_sel[idx] = wi;
                        word_row[idx] = vrow;
                        word_col[idx] = (unsigned char)(wh->col - pos);
                        word_len[idx] = wh->len;
                        word_ptr[idx] = (const char *)line_start + wh->col;
                        word_prev[idx] = wh->col
                            ? ((const char *)line_start)[wh->col - 1] : 0;
                    }
                }
            }
#endif
            pos += consumed;
            if (vrow >= text_scroll && vrow < text_scroll + text_rows)
                plat_text(text_top + vrow - text_scroll, 0, buf);
            vrow++;
            if (vrow == 255) {
                s = (const unsigned char *)"";
                break;
            }
        }
    }
    text_total = vrow;
#endif

#if HAVE_WORDS
    {
        char buf[PORT_COLS + 2];
        for (i = 0; i < word_count; i++) {
            if (word_row[i] >= text_scroll
                    && word_row[i] < text_scroll + text_rows) {
                unsigned char n = word_len[i];
                unsigned char maxn = PORT_TEXT_WIDTH - word_col[i];
                unsigned char j;
                if (n > maxn)
                    n = maxn;
                for (j = 0; j < n; j++)
                    buf[j] = word_ptr[i][j];
                buf[n] = 0;
                plat_text_at(text_top + word_row[i] - text_scroll,
                             word_col[i], buf, 1);
            }
        }
    }
#endif
}

#if !PORT_NO_TEXT_SCROLL
/* Draw the scroll markers only while the text actually overflows the pane.
   They are drawn after the pinned options so the right-hand column stays
   visible on every target. */
void draw_scroll_markers(void)
{
    if (!scroll_max)
        return;
    if (text_scroll)
        plat_text(text_top, PORT_SCROLL_COL, PORT_SCROLL_UP);
    if (text_scroll < scroll_max)
        plat_text(text_top + text_rows - 1, PORT_SCROLL_COL, PORT_SCROLL_DOWN);
}
#endif

void print_option_marker(unsigned char row, unsigned char selected)
{
    plat_text_at(row, 0, selected ? ">" : " ", selected ? 1 : 0);
}

#if !PORT_OVERLAY_MENU
#if !PORT_SIMPLE_OPTIONS
unsigned char print_option(unsigned char row, const char *label,
                                  unsigned char selected)
{
    unsigned char color = selected ? 1 : 0;
    unsigned char n = print_text_color(row, PORT_OPT_INDENT, label,
                                       PORT_OPT_WIDTH, color);
    print_option_marker(row, selected);
    return n;
}
#endif

#if PORT_SIMPLE_OPTIONS
void print_option_simple(unsigned char row, const char *label,
                                unsigned char selected)
{
    char buf[PORT_COLS + 1];
    unsigned char n = 0, color = selected ? 1 : 0;
    while (label[n] && n < PORT_OPT_WIDTH && n < PORT_COLS - PORT_OPT_INDENT) {
        buf[n] = label[n];
        n++;
    }
    buf[n] = 0;
    print_option_marker(row, selected);
    plat_text_at(row, PORT_OPT_INDENT, buf, color);
}
#endif
#endif

void clear_row(unsigned char row)
{
    plat_clear_row(row);
}
