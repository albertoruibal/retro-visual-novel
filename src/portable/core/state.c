#include "port.h"

#if !PORT_EXTERN_WS
unsigned char scene_ws[PORT_SCENE_WS];
#if HAVE_INV_BLOB
unsigned char inv_ws[PORT_INV_WS];
#endif
#endif
unsigned char flags[NFLAGS];
unsigned char cur;
#if PORT_KEEP_ART
/* Art already on screen (0xFF = none). A scene change that reuses the same art
   clears only the title/text pane, so the platform does not decode it again. */
unsigned char cur_art = 0xFF;
#endif
unsigned char opt_idx[NOPT_MAX];
unsigned char inv_vis[N_ITEMS + 1];
unsigned char inv_nvis;
#if !PORT_OVERLAY_MENU
unsigned char opt_row[NOPT_MAX];
unsigned char opt_nrows[NOPT_MAX];
unsigned char inv_first;
unsigned char inv_win;
unsigned char inv_cur = 0xFF;
#endif
unsigned char text_top = PORT_TEXT_TOP;
unsigned char text_rows;
unsigned char text_total;
unsigned char text_scroll;
unsigned char scroll_max;
unsigned char text_fresh;
unsigned char word_count;
#if HAVE_WORDS
unsigned char word_sel[WORD_MAX];
unsigned char word_row[WORD_MAX];
unsigned char word_col[WORD_MAX];
unsigned char word_len[WORD_MAX];
const char *word_ptr[WORD_MAX];
unsigned char word_prev[WORD_MAX];
#endif
