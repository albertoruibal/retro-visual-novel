; Reliable CPC ink setter.
;
; void cpc_set_ink(unsigned int pen, unsigned int color);
;
; The z88dk cpc_set_palette/cpc_SetInk wrappers differ subtly in their
; argument shuffling for the callee convention.  This calls the firmware
; SCR_SET_INK jumpblock directly with the documented registers:
;   A = pen, B = first colour, C = second colour
; The colour is a firmware grey-scale index 0..26 (black..bright white).
;
; SCR_SET_INK leaves the Gate Array memory configuration changed, so restore
; the normal 64K map before returning: callers (notably plat_draw_art) may be
; linked above 0x4000 where the firmware's extra bank would hide the code.
        SECTION code_l
        PUBLIC  _cpc_set_ink
        EXTERN  firmware

_cpc_set_ink:
        ld      hl,4
        add     hl,sp
        ld      a,(hl)          ; pen (first C argument)
        ld      hl,2
        add     hl,sp
        ld      c,(hl)          ; colour (second C argument)
        ld      b,c
        call    firmware
        defw    $BC32           ; scr_set_ink
        ld      bc,$7FC0
        out     (c),c           ; back to the base 64K mapping
        ret
