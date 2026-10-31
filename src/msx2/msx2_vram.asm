; Fast MSX2 Screen 7 VRAM access.
;
; The classic LDIRVM/FILVRM BIOS calls only take a 14-bit address and reset
; R#14, so these routines set R#14 themselves.  Bulk writes go through a
; chunked OTIR loop (21 T-states per byte on the V9938, which needs 15), and
; rectangle clears use the VDP command engine (HMMV) so a full-screen clear
; is done by the VDP instead of by a CPU port loop.
;
; C prototypes (sccz80 smallc):
;   void msx2_vwrite(const unsigned char *src, unsigned int addr,
;                    unsigned int count);
;   void msx2_fill(unsigned int dx, unsigned int dy, unsigned int nx,
;                  unsigned int ny, unsigned char color);
;   void msx2_text(const char *src, unsigned int addr, unsigned char n,
;                  unsigned char mask);   -- 80-column (6-pixel cells)
;   void msx2_text8(const char *src, unsigned int addr, unsigned char n,
;                   unsigned char mask);  -- 64-column (8-pixel cells)

    SECTION bss_user
_vw_rem:    defw 0
_vw_chunk:  defb 0
_mt_src0:   defw 0
_mt_src:    defw 0
_mt_addr:   defw 0
_mt_n:      defb 0
_mt_mask:   defb 0
_mt_dy:     defb 0
_mt_dy2:    defb 0
_mt_cnt:    defb 0
_mt_line:   defs 256

    SECTION code_user
    PUBLIC _msx2_vwrite
    PUBLIC _msx2_fill
    PUBLIC _msx2_text
    PUBLIC _msx2_text8

; ---------------------------------------------------------------- VRAM write
_msx2_vwrite:
    push    ix
    ld      ix, 4
    add     ix, sp
    ld      e, (ix+2)
    ld      d, (ix+3)          ; addr
    ld      l, (ix+4)
    ld      h, (ix+5)          ; source
    ld      a, (ix+0)
    ld      (_vw_rem), a
    ld      a, (ix+1)
    ld      (_vw_rem+1), a
vw_loop:
    ld      a, (_vw_rem+1)
    or      a
    jr      nz, vw_full
    ld      a, (_vw_rem)
    or      a
    jr      z, vw_done
    jr      vw_chunk           ; final chunk is 1..255 bytes
vw_full:
    xor     a                  ; a full 256-byte chunk (B=0)
vw_chunk:
    ld      (_vw_chunk), a
    ld      b, a
    di
    call    msx2_set_addr
    ld      c, $98
    ei
    otir
    ld      a, (_vw_chunk)
    or      a
    jr      nz, vw_finish
    ld      a, (_vw_rem+1)     ; rem -= 256
    dec     a
    ld      (_vw_rem+1), a
    inc     d                  ; addr += 256
    jr      vw_loop
vw_finish:
    xor     a
    ld      (_vw_rem), a
    ld      (_vw_rem+1), a
vw_done:
    pop     ix
    ret

; ------------------------------------------------------------- rect fill
; void msx2_fill(dx, dy, nx, ny, color)  -- HMMV in dots.
_msx2_fill:
    push    ix
    ld      ix, 4
    add     ix, sp
    call    msx2_wait
    di
    ld      a, 36              ; command registers R#36..R#46
    out     ($99), a
    ld      a, 17 + $80        ; R#17 = start register, auto-increment
    out     ($99), a
    ld      c, $9b
    ld      a, (ix+8)          ; DX
    out     (c), a
    ld      a, (ix+9)
    out     (c), a
    ld      a, (ix+6)          ; DY
    out     (c), a
    ld      a, (ix+7)
    out     (c), a
    ld      a, (ix+4)          ; NX
    out     (c), a
    ld      a, (ix+5)
    out     (c), a
    ld      a, (ix+2)          ; NY
    out     (c), a
    ld      a, (ix+3)
    out     (c), a
    ld      a, (ix+0)          ; CLR
    out     (c), a
    xor     a                  ; ARG: DIX=DIY=0
    out     (c), a
    ld      a, $c0             ; HMMV
    out     (c), a
    ei
    call    msx2_wait
    pop     ix
    ret

; ---------------------------------------------------------------- text
; void msx2_text(const char *src, unsigned int addr, unsigned char n,
;                unsigned char mask)
; Draws n glyph cells (6x8 pixels each) in one go.  The expanded white cell
; table turns the inner loop into two table reads and three stores.
    EXTERN _port_font_cells

_msx2_text:
    push    ix
    ld      ix, 4
    add     ix, sp
    ld      a, (ix+2)          ; n
    or      a
    jp      z, mt_done
    ld      (_mt_n), a
    ld      a, (ix+0)          ; mask
    ld      (_mt_mask), a
    ld      l, (ix+6)          ; src
    ld      h, (ix+7)
    ld      (_mt_src0), hl
    ld      (_mt_src), hl
    ld      l, (ix+4)          ; addr
    ld      h, (ix+5)
    ld      (_mt_addr), hl
    xor     a
    ld      (_mt_dy), a
mt_row:
    ld      hl, (_mt_src0)
    ld      (_mt_src), hl
    ld      a, (_mt_dy)
    add     a, a
    ld      (_mt_dy2), a
    ld      de, _mt_line
    ld      a, (_mt_n)
    ld      (_mt_cnt), a
mt_char:
    ld      hl, (_mt_src)
    ld      a, (hl)
    inc     hl
    ld      (_mt_src), hl
    cp      32
    jr      c, mt_blank
    cp      128
    jr      nc, mt_blank
    sub     32
    ld      l, a
    ld      h, 0
    add     hl, hl
    add     hl, hl
    add     hl, hl
    add     hl, hl
    ld      a, (_mt_dy2)
    add     a, l
    ld      l, a
    ld      bc, _port_font_cells
    add     hl, bc
    ld      a, (_mt_mask)
    and     (hl)
    ld      (de), a
    inc     de
    inc     hl
    ld      a, (_mt_mask)
    and     (hl)
    ld      (de), a
    inc     de
    xor     a
    ld      (de), a
    inc     de
    jr      mt_next
mt_blank:
    xor     a
    ld      (de), a
    inc     de
    ld      (de), a
    inc     de
    ld      (de), a
    inc     de
mt_next:
    ld      a, (_mt_cnt)
    dec     a
    ld      (_mt_cnt), a
    jr      nz, mt_char
    ld      de, (_mt_addr)
    ld      a, (_mt_dy)
    add     a, d                ; addr += dy * 256
    ld      d, a
    ld      a, (_mt_n)
    ld      b, a
    add     a, a
    add     a, b
    ld      b, a                ; count = n * 3 (otir uses B, C is the port)
    ld      hl, _mt_line
    di
    call    msx2_set_addr
    ld      c, $98
    ei
    otir
    ld      a, (_mt_dy)
    inc     a
    ld      (_mt_dy), a
    cp      8
    jp      nz, mt_row
mt_done:
    pop     ix
    ret

; void msx2_text8(const char *src, unsigned int addr, unsigned char n,
;                 unsigned char mask)
; Draws n 8x8 glyph cells (four bytes per row) into Screen 7.
_msx2_text8:
    push    ix
    ld      ix, 4
    add     ix, sp
    ld      a, (ix+2)          ; n
    or      a
    jp      z, me_done
    ld      (_mt_n), a
    ld      a, (ix+0)          ; mask
    ld      (_mt_mask), a
    ld      l, (ix+6)          ; src
    ld      h, (ix+7)
    ld      (_mt_src0), hl
    ld      l, (ix+4)          ; addr
    ld      h, (ix+5)
    ld      (_mt_addr), hl
    xor     a
    ld      (_mt_dy), a
me_row:
    ld      hl, (_mt_src0)
    ld      (_mt_src), hl
    ld      a, (_mt_dy)
    add     a, a
    add     a, a
    ld      (_mt_dy2), a
    ld      de, _mt_line
    ld      a, (_mt_n)
    ld      (_mt_cnt), a
me_char:
    ld      hl, (_mt_src)
    ld      a, (hl)
    inc     hl
    ld      (_mt_src), hl
    cp      32
    jr      c, me_blank
    cp      128
    jr      nc, me_blank
    sub     32
    ld      l, a
    ld      h, 0
    add     hl, hl
    add     hl, hl
    add     hl, hl
    add     hl, hl
    add     hl, hl
    ld      a, (_mt_dy2)
    add     a, l
    ld      l, a
    ld      bc, _port_font_cells
    add     hl, bc
    ld      a, (_mt_mask)
    and     (hl)
    ld      (de), a
    inc     de
    inc     hl
    ld      a, (_mt_mask)
    and     (hl)
    ld      (de), a
    inc     de
    inc     hl
    ld      a, (_mt_mask)
    and     (hl)
    ld      (de), a
    inc     de
    inc     hl
    ld      a, (_mt_mask)
    and     (hl)
    ld      (de), a
    inc     de
    jr      me_next
me_blank:
    xor     a
    ld      (de), a
    inc     de
    ld      (de), a
    inc     de
    ld      (de), a
    inc     de
    ld      (de), a
    inc     de
me_next:
    ld      a, (_mt_cnt)
    dec     a
    ld      (_mt_cnt), a
    jr      nz, me_char
    ld      de, (_mt_addr)
    ld      a, (_mt_dy)
    add     a, d                ; addr += dy * 256
    ld      d, a
    ld      a, (_mt_n)
    add     a, a
    add     a, a
    ld      b, a                ; count = n * 4 (otir uses B, C is the port)
    ld      hl, _mt_line
    di
    call    msx2_set_addr
    ld      c, $98
    ei
    otir
    ld      a, (_mt_dy)
    inc     a
    ld      (_mt_dy), a
    cp      8
    jp      nz, me_row
me_done:
    pop     ix
    ret

; Wait for the VDP command engine (CE in S#2) to finish.
msx2_wait:
    ld      a, 2
    di
    out     ($99), a           ; select S#2
    ld      a, 15 + $80
    out     ($99), a
msx2_wait_loop:
    in      a, ($99)
    rra
    jr      c, msx2_wait_loop
    xor     a                  ; restore S#0
    out     ($99), a
    ld      a, 15 + $80
    ei
    out     ($99), a
    ret

; DE = 17-bit VRAM address.  Set R#14 = D >> 6 and the 14-bit write address.
msx2_set_addr:
    ld      a, d
    rlca
    rlca
    and     3
    out     ($99), a
    ld      a, $8e
    out     ($99), a
    ld      a, e
    out     ($99), a
    ld      a, d
    and     $3f
    or      $40
    out     ($99), a
    ret
