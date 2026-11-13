#ifndef PORT_ADVENTURE_H
#define PORT_ADVENTURE_H

#include <string.h>
#include "port_data.h"
#include "plat.h"

#ifdef PORT_TEXT_MACRO
#define plat_text(row, col, s) plat_text_at(row, col, s, PLAT_COLOR_BODY)
#endif
#ifdef PORT_BOOT_MACRO
#define plat_boot() ((void)0)
#endif

#ifndef PLAT_ROWS
#define PLAT_ROWS 24
#endif
#ifndef PORT_TEXT_TOP
#define PORT_TEXT_TOP 1
#endif
#ifndef PORT_TITLE_ROW
#define PORT_TITLE_ROW 0
#endif
#ifndef PORT_TEXT_WIDTH
#define PORT_TEXT_WIDTH PORT_COLS
#endif
#ifndef PORT_DESC_WIDTH
#define PORT_DESC_WIDTH PORT_COLS
#endif
#ifndef PORT_OPT_WIDTH
#define PORT_OPT_WIDTH (PORT_COLS - 2)
#endif
#ifndef PORT_OPT_INDENT
#define PORT_OPT_INDENT 1
#endif
#ifndef PORT_SIMPLE_OPTIONS
#define PORT_SIMPLE_OPTIONS 0
#endif
#ifndef PORT_KEEP_ART
#define PORT_KEEP_ART 0
#endif
#ifndef PORT_ART_CLEARS_TEXT
#define PORT_ART_CLEARS_TEXT 0
#endif
#ifndef PORT_OVERLAY_MENU
#define PORT_OVERLAY_MENU 0
#endif
#ifndef PORT_NO_TEXT_SCROLL
#define PORT_NO_TEXT_SCROLL 0
#endif
#ifndef PORT_SCROLL_UP
#define PORT_SCROLL_UP "^"
#endif
#ifndef PORT_SCROLL_DOWN
#define PORT_SCROLL_DOWN "v"
#endif
#ifndef PORT_NO_DESC_SCROLL
#define PORT_NO_DESC_SCROLL 0
#endif
#ifndef PORT_NO_WRAP
#define PORT_NO_WRAP 0
#endif
#ifndef PORT_NO_ENTRY_WRAP
#define PORT_NO_ENTRY_WRAP 0
#endif
#ifndef PORT_MARKER_MATCH_CELL
#define PORT_MARKER_MATCH_CELL 0
#endif
#ifndef PORT_MARKER_BODY
#define PORT_MARKER_BODY 0
#endif
#ifndef PORT_ATOMIC_MENU
#define PORT_ATOMIC_MENU 0
#endif
#if PORT_ATOMIC_MENU
unsigned char port_atomic_lock(unsigned char bytes);
void port_atomic_unlock(void);
#endif
#ifndef PORT_SCROLL_COL
#define PORT_SCROLL_COL (PORT_COLS - 1)
#endif
#ifndef PORT_INV_MARK_R
#define PORT_INV_MARK_R (PORT_COLS - 1)
#endif
#ifndef PORT_INV_CONTENT_COLS
#define PORT_INV_CONTENT_COLS (PORT_COLS - 1)
#endif
#ifndef PORT_INV_OVERWRITES_ART
#define PORT_INV_OVERWRITES_ART 0
#endif
#ifndef PORT_EXTERN_WS
#define PORT_EXTERN_WS 0
#endif
#ifndef HAVE_WORDS
#define HAVE_WORDS 0
#endif
#ifndef HAVE_MESSAGES
#define HAVE_MESSAGES 0
#endif
#ifndef PORT_SFX
#define PORT_SFX 0
#endif
#if PORT_SFX
#define SFX(id) plat_sfx(id)
#else
#define SFX(id) ((void)0)
#endif

#if PORT_KEEP_ART || PORT_OVERLAY_MENU
#define ITEM_TOP PORT_TEXT_TOP
#else
#define ITEM_TOP 0
#endif
#ifndef PORT_ITEM_BOTTOM
#if PORT_OVERLAY_MENU
#define PORT_ITEM_BOTTOM PLAT_ROWS
#else
#define PORT_ITEM_BOTTOM (PLAT_ROWS - 1)
#endif
#endif
#define ITEM_BOTTOM PORT_ITEM_BOTTOM

#define NOPT_MAX 6
#define WORD_MAX 8
#define NFLAGS 32
#define CURSOR_UP 1
#define CURSOR_DOWN 2
#define CURSOR_ENTER 3
#define CURSOR_LEFT 6
#define CURSOR_RIGHT 7
#define CURSOR_MENU PORT_KEY_MENU

#ifdef PORT_DATA_BANK
#define PORT_PAGE_DATA() plat_set_bank(PORT_DATA_BANK)
#else
#define PORT_PAGE_DATA() ((void)0)
#endif

extern void port_unpack(const void *src, void *dst) __smallc;

#if PORT_EXTERN_WS
extern unsigned char scene_ws[];
#if HAVE_INV_BLOB
extern unsigned char inv_ws[];
#endif
#else
extern unsigned char scene_ws[PORT_SCENE_WS];
#if HAVE_INV_BLOB
extern unsigned char inv_ws[PORT_INV_WS];
#endif
#endif
extern unsigned char flags[NFLAGS];
extern unsigned char cur;
extern unsigned char cur_art;
extern unsigned char opt_idx[NOPT_MAX];
extern unsigned char inv_vis[N_ITEMS + 1];
extern unsigned char inv_nvis;
extern unsigned char opt_row[NOPT_MAX];
extern unsigned char opt_nrows[NOPT_MAX];
extern unsigned char inv_first;
extern unsigned char inv_win;
extern unsigned char inv_cur;
extern unsigned char text_top;
extern unsigned char text_rows;
extern unsigned char text_total;
extern unsigned char text_scroll;
extern unsigned char scroll_max;
extern unsigned char text_fresh;
extern unsigned char word_count;
#if HAVE_WORDS
extern unsigned char word_sel[WORD_MAX];
extern unsigned char word_row[WORD_MAX];
extern unsigned char word_col[WORD_MAX];
extern unsigned char word_len[WORD_MAX];
extern const char *word_ptr[WORD_MAX];
extern unsigned char word_prev[WORD_MAX];
#endif

unsigned char flag_get(unsigned char id);
void flag_set(unsigned char id, unsigned char v);
void reset_game(void);
unsigned char opt_visible(const unsigned char *blob, unsigned int cond_off,
                          unsigned char ncond, unsigned char pick);
void opt_apply(unsigned char set_, unsigned char unset, unsigned char pick,
               unsigned char leave, unsigned char clear);
void load_scene(unsigned char id);
#if HAVE_INV_BLOB
void load_inv(void);
#endif
const unsigned char *line_text(const unsigned char *s, unsigned char *visible);

unsigned char name_len(const char *s);
unsigned char print_text_color(unsigned char row, unsigned char col,
                               const char *s, unsigned char width,
                               unsigned char color);
void text_next_segment(const char **ps, unsigned char width, char *buf);
unsigned char count_rows(const char *s, unsigned char width);
void render_text(void);
void draw_scroll_markers(void);
void print_option_marker(unsigned char row, unsigned char selected);
#if !PORT_OVERLAY_MENU
unsigned char print_option(unsigned char row, const char *label,
                           unsigned char selected);
#if PORT_SIMPLE_OPTIONS
void print_option_simple(unsigned char row, const char *label,
                         unsigned char selected);
#endif
#endif
void clear_row(unsigned char row);
#if HAVE_MESSAGES
void show_message(const char *text);
#endif

void collect_items(void);
void draw_inventory(void);
void inv_mark(unsigned char idx, unsigned char on);
void inv_step(char dir);
#if HAVE_INV_BLOB
unsigned char drop_screen(unsigned char id);
#endif

unsigned char collect_options(void);
unsigned char show_scene(unsigned char id);
unsigned char choose_option(unsigned char navail);

#endif
