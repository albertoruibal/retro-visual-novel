; Buffered PPU-memory writes for the NES runtime (ca65 syntax).
;
; void __cdecl__ nes_ppu_put(unsigned char value, unsigned int addr)
;   Queue one byte for the cc65 NMI handler (ppubuf_flush), which writes it
;   during vblank and resets the scroll.  The cdecl stack has addr on top,
;   then value.  ppubuf_put (cc65 2.18) wants A=value, Y=addr high, X=addr low.

        .include        "zeropage.inc"

        .import         popa, popax, ppubuf_put
        .export         _nes_ppu_put

        .segment        "CODE"

.proc   _nes_ppu_put
        jsr     popax           ; A = addr low, X = addr high
        sta     tmp1
        stx     tmp2
        jsr     popa            ; A = value
        ldx     tmp1            ; X = addr low
        ldy     tmp2            ; Y = addr high
        jmp     ppubuf_put
.endproc
