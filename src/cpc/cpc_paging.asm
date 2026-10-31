; CPC bank paging + ZX0 decode.
;
; void cpc_unpack_banked(unsigned int bank, unsigned int off, void *dst);
;
; The CPC 6128 maps one of the extra 16K banks into 0x4000..0x7FFF through
; port 0x7F00 (0xC4..0xC7 = banks 4..7; 0xC0 restores the base map).  The
; decoder and this routine must live below 0x4000, because the paged bank
; replaces that window while they run.  Interrupts stay off for the whole
; page/decode/restore sequence so the firmware ISR never executes from the
; temporarily replaced base RAM.
        SECTION code_l
        PUBLIC  _cpc_unpack_banked
        PUBLIC  _cpc_restore_base
        EXTERN  _zx0_unpack

_cpc_unpack_banked:
        di
        ld      hl,6
        add     hl,sp
        ld      a,(hl)          ; bank number (4..7), last argument
        or      $C0
        ld      c,a
        ld      b,$7F
        out     (c),c           ; same Gate Array write as the CRT loader

        ld      hl,4
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)          ; DE = offset in bank
        ld      hl,$4000
        add     hl,de           ; HL = bank-window source
        push    hl

        ld      hl,4            ; dst is the first argument (sp+2)
        add     hl,sp           ; current sp+4 after the push
        ld      e,(hl)
        inc     hl
        ld      d,(hl)
        pop     hl              ; HL = source, DE = destination

        call    _zx0_unpack

        ld      bc,$7FC0
        out     (c),c           ; restore the base mapping (CRT loader style)
        ei
        ret

; void cpc_restore_base(void);
; Some firmware calls (notably SCR_SET_INK) leave the Gate Array memory
; configuration changed.  Restore the normal 64K map afterwards.
_cpc_restore_base:
        ld      bc,$7FC0
        out     (c),c
        ret
