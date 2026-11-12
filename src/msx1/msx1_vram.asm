; MSX1 (TMS9918A) VRAM writes for Graphics II (SCREEN 2).
;
; The TMS9918 has a 14-bit VRAM address and no VDP command engine.  All text
; and art updates are small enough that a byte-at-a-time port loop is fast
; enough, and keeping these helpers in a few routines avoids exposing the
; address latch to the C compiler.
;
; C prototypes (sccz80 smallc):
;   void msx1_vwrite(const unsigned char *src, unsigned int addr,
;                    unsigned int count);
;   void msx1_fill(unsigned int addr, unsigned char value, unsigned int count);
;   void msx1_text(const char *src, unsigned int pnt, unsigned int ct,
;                  unsigned char n, unsigned char color);

    SECTION code_user
    PUBLIC _msx1_vwrite
    PUBLIC _msx1_fill
    PUBLIC _msx1_text
    PUBLIC _msx1_set_reg

; DE = 14-bit VRAM address, ready for a write.
msx1_set_addr:
    di
    ld      a, e
    out     ($99), a
    ld      a, d
    and     $3f
    or      $40
    out     ($99), a
    ei
    ret

; ---------------------------------------------------------- register write
; void msx1_set_reg(unsigned char reg, unsigned char value)
_msx1_set_reg:
    push    ix
    ld      ix, 4
    add     ix, sp
    di
    ld      a, (ix+0)          ; value
    out     ($99), a
    ld      a, (ix+2)          ; register
    or      $80
    out     ($99), a
    ei
    pop     ix
    ret

; ---------------------------------------------------------------- block write
_msx1_vwrite:
    push    ix
    ld      ix, 4
    add     ix, sp
    ld      l, (ix+4)
    ld      h, (ix+5)          ; source
    ld      e, (ix+2)
    ld      d, (ix+3)          ; destination
    ld      c, (ix+0)
    ld      b, (ix+1)          ; count
    call    msx1_set_addr
    ld      a, b
    or      c
    jr      z, vw_done
vw_loop:
    ld      a, (hl)
    out     ($98), a
    inc     hl
    dec     bc
    ld      a, b
    or      c
    jr      nz, vw_loop
vw_done:
    pop     ix
    ret

; ------------------------------------------------------------------ fill
_msx1_fill:
    push    ix
    ld      ix, 4
    add     ix, sp
    ld      e, (ix+4)
    ld      d, (ix+5)          ; destination
    ld      a, (ix+2)          ; value
    ld      l, a
    ld      c, (ix+0)
    ld      b, (ix+1)          ; count
    call    msx1_set_addr
    ld      a, b
    or      c
    jr      z, fl_done
fl_loop:
    ld      a, l
    out     ($98), a
    dec     bc
    ld      a, b
    or      c
    jr      nz, fl_loop
fl_done:
    pop     ix
    ret

 ; ------------------------------------------------------------------ text
; Draw n glyphs at the name-table address PNT and fill their colour-table
; cells at CT with one ink/paper byte.
_msx1_text:
    push    ix
    ld      ix, 4
    add     ix, sp
    ld      a, (ix+2)          ; n
    or      a
    jp      z, tx_done
    ld      l, (ix+8)
    ld      h, (ix+9)          ; src
    ld      e, (ix+6)
    ld      d, (ix+7)          ; name table
    ld      c, a
    call    msx1_set_addr
    ld      b, c
tx_name:
    ld      a, (hl)
    inc     hl
    cp      32
    jr      c, tx_blank
    cp      128
    jr      nc, tx_blank
    sub     32
    jr      tx_put
tx_blank:
    xor     a
tx_put:
    out     ($98), a
    dec     b
    jr      nz, tx_name
    ; colour table: n*8 copies of the ink/paper byte
    ld      a, (ix+2)
    ld      l, a
    ld      h, 0
    add     hl, hl
    add     hl, hl
    add     hl, hl          ; BC = n*8
    ld      b, h
    ld      c, l
    ld      e, (ix+4)
    ld      d, (ix+5)
    call    msx1_set_addr
    ld      a, (ix+0)       ; ink/paper byte
    ld      l, a
    ld      a, b
    or      c
    jr      z, tx_done
tx_colour:
    ld      a, l
    out     ($98), a
    dec     bc
    ld      a, b
    or      c
    jr      nz, tx_colour
tx_done:
    pop     ix
    ret
