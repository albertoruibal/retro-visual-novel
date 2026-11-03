; ---------------------------------------------------------------------------
; ZX Spectrum Next IM1 interrupt hook for the shared AY VT2 player.
; ---------------------------------------------------------------------------

SECTION code_user

PUBLIC _next_isr_install
EXTERN _next_isr_hook

_next_isr_install:
        di
        ld      a,$c3                  ; jp _next_isr
        ld      ($0038),a
        ld      hl,_next_isr
        ld      ($0039),hl
        im      1
        ei
        ret

PUBLIC _next_isr
_next_isr:
        push    af
        push    bc
        push    de
        push    hl
        push    ix
        push    iy
        ld      hl,($5c78)             ; FRAMES
        inc     hl
        ld      ($5c78),hl
        call    _next_isr_hook
        pop     iy
        pop     ix
        pop     hl
        pop     de
        pop     bc
        pop     af
        ei
        reti
