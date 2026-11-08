; Small C64 hardware helpers (ca65 syntax).
;
; c64_any_key_down scans the whole keyboard matrix with interrupts disabled
; and restores CIA1, so plat_wait_release does not race the KERNAL keyboard
; IRQ.  The C prototype is ``unsigned char c64_any_key_down(void)``.

        .export _c64_any_key_down

        .segment "CODE"

.proc _c64_any_key_down
        php
        sei
        lda     $DC02
        pha
        lda     $DC03
        pha
        lda     $DC00
        pha
        lda     #$FF
        sta     $DC02           ; port A = outputs (columns)
        lda     #$00
        sta     $DC03           ; port B = inputs (rows)
        lda     #$00
        sta     $DC00           ; select every column
        lda     $DC01
        ldx     #0
        cmp     #$FF
        beq     @none
        ldx     #1
@none:
        pla
        sta     $DC00
        pla
        sta     $DC03
        pla
        sta     $DC02
        txa
        plp
        rts
.endproc
