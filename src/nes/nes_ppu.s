; Buffered PPU-memory writes for the NES runtime (ca65 syntax).
;
; void __cdecl__ nes_ppu_put(unsigned char value, unsigned int addr)
;   Queue one byte for the custom NMI handler, which writes it during vblank
;   and resets the scroll.  The cdecl stack has addr on top, then value.
;   ppubuf_put (cc65 2.18) wants A=value, Y=addr high, X=addr low.

        .include        "zeropage.inc"
        .include        "nes.inc"

        .import         popa, popax, ppubuf_put, ppubuf_flush
        .import         _nes_split_on, _nes_split_idx, _port_nes_split_xy
        .import         _nes_update_lock
        .import         _nes_audio_tick
        .export         _nes_ppu_put, _nes_nmi, _nes_ringcount

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

; unsigned char nes_ringcount(void)
.proc   _nes_ringcount
        lda     ringcount
        rts
.endproc

; NMI handler installed by tools/targets/nes.py in place of the cc65 one.  It
; flushes the ppubuf, keeps background pattern table 0 through the art band and
; switches to table 1 in the last art scanline's HBlank.  The generated table
; compensates for the ppubuf flush length; a locked update uses the empty-queue
; timing and defers the flush.
.proc   _nes_nmi
        pha
        tya
        pha
        txa
        pha

        lda     #1
        sta     VBLANK_FLAG
        inc     tickcount
        bne     @tick
        inc     tickcount+1
@tick:
        lda     _nes_update_lock
        beq     @flush
        lda     #0
        sta     _nes_split_idx
        jmp     @afterflush
@flush:
        lda     ringcount
        sta     _nes_split_idx
        jsr     ppubuf_flush
@afterflush:

        lda     #$20
        sta     PPU_VRAM_ADDR2
        lda     #$00
        sta     PPU_VRAM_ADDR2
        sta     PPU_VRAM_ADDR1
        sta     PPU_VRAM_ADDR1

        lda     #$80            ; NMI on, background table 0
        sta     PPU_CTRL1
        lda     _nes_split_on
        beq     @done

        lda     _nes_split_idx
        asl     a               ; the table holds an (x,y) pair per queue length
        tax
        lda     _port_nes_split_xy+1,x
        tay
        lda     _port_nes_split_xy,x
        tax
@wait:
        dex
        bne     @wait
        dey
        bne     @wait
        lda     #$90            ; text pane uses background table 1
        sta     PPU_CTRL1
@done:
        jsr     _nes_audio_tick
        pla
        tax
        pla
        tay
        pla
        rti
.endproc
