; ---------------------------------------------------------------------------
; ZX Spectrum Next scene paging and small NextReg helpers.
;
; Source blobs are [u16 compressed length][ZX0 stream] in a 16K Next bank.
; The copy runs with interrupts disabled and maps the source bank at 0xC000;
; bank 0 (the CRT/workspace bank) is restored before the ZX0 decode, which
; runs with interrupts enabled from the resident lower-RAM staging buffer.
; ---------------------------------------------------------------------------

SECTION code_user

PUBLIC _nextreg
PUBLIC _nextreg_get
PUBLIC _paged_next_unpack
PUBLIC _crt_font64
PUBLIC _next_isr_hook

EXTERN _zx0_unpack
EXTERN _ay_vt2_play
EXTERN CRT_FONT_64

defc _stage_ws = $6000

; void nextreg(unsigned int regval) __z88dk_fastcall; H=register, L=value.
_nextreg:
        ld      e,l
        ld      a,h
        ld      bc,$243b
        out     (c),a
        inc     b
        ld      a,e
        out     (c),a
        ret

; unsigned char nextreg_get(unsigned char reg) __z88dk_fastcall; L=register.
_nextreg_get:
        ld      bc,$243b
        ld      a,l
        out     (c),a
        ld      bc,$253b
        in      a,(c)
        ld      l,a
        ret

; unsigned char *crt_font64(void)
_crt_font64:
        ld      hl,CRT_FONT_64
        ret

; IM1 hook: either CALL ay_vt2_play or RET (three bytes).
_next_isr_hook:
        ret
        nop
        nop

; void paged_next_unpack(unsigned int bank, unsigned int src, unsigned int dst)
; sccz80 classic: sp+2=dst, sp+4=src, sp+6=bank.
_paged_next_unpack:
        ld      hl,6
        add     hl,sp
        ld      a,(hl)
        ld      (_paged_bank),a
        ld      hl,4
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)
        ld      (_paged_src),de
        ld      hl,2
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)
        ld      (_paged_dst),de

        di
        call    paged_map_in
        ld      hl,(_paged_src)
        ld      e,(hl)
        inc     hl
        ld      d,(hl)           ; DE = compressed length
        inc     hl               ; HL = stream
        ld      (_paged_stream),hl
        ld      (_paged_rem),de
        ld      bc,(_paged_rem)
        ld      hl,(_paged_stream)
        ld      de,_stage_ws
        ldir
        call    paged_map_out
        ei

        ld      hl,_stage_ws
        ld      de,(_paged_dst)
        jp      _zx0_unpack

; Map (_paged_bank) into 0xC000..0xFFFF: 8K pages bank*2, bank*2+1.
paged_map_in:
        ld      a,(_paged_bank)
        add     a,a
        ld      e,a
        inc     a
        ld      d,a
        ld      a,$56
        ld      bc,$243b
        out     (c),a
        inc     b
        out     (c),e
        ld      a,$57
        dec     b
        out     (c),a
        inc     b
        out     (c),d
        ret

; Restore bank 0 at 0xC000: 8K pages 0 and 1.
paged_map_out:
        ld      a,$56
        ld      bc,$243b
        out     (c),a
        inc     b
        xor     a
        out     (c),a
        ld      a,$57
        dec     b
        out     (c),a
        inc     b
        ld      a,1
        out     (c),a
        ret

_paged_bank:
        defs    1
_paged_src:
        defs    2
_paged_stream:
        defs    2
_paged_dst:
        defs    2
_paged_rem:
        defs    2

; Workspaces in the upper half of bank 0 (0xE000), above the CRT and the
; AY player variables that live in the lower half.
SECTION BANK_0_H

IFNDEF SCENE_WS_SIZE
    defc SCENE_WS_SIZE = 1024
ENDIF
IFNDEF INV_WS_SIZE
    defc INV_WS_SIZE = 1024
ENDIF

PUBLIC _scene_ws
_scene_ws:
        defs    SCENE_WS_SIZE

PUBLIC _inv_ws
_inv_ws:
        defs    INV_WS_SIZE

PUBLIC _next_font
_next_font:
        defs    768


