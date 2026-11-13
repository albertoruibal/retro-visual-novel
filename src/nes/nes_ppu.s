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
        .import         _nes_update_lock, _nes_direct_mode, _nes_pending_enable
        .import         _nes_mmc1_busy
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
;
; While the main thread is doing direct VRAM writes it has rendering off.  The
; tick still runs there (so music does not stall) but the PPU is left alone; a
; pending end_direct is honoured at vblank, when the picture can be enabled
; without starting a partial, scroll-shifted frame.
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
        lda     _nes_direct_mode
        beq     @flush
        lda     _nes_pending_enable
        beq     @audio
        lda     #0
        sta     _nes_pending_enable
        sta     _nes_direct_mode
@flush:
        lda     _nes_update_lock
        beq     @dofush
        lda     #0
        sta     _nes_split_idx
        jmp     @afterflush
@dofush:
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

        lda     #$0A            ; background on, sprites off, no clipping
        sta     PPU_CTRL2
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
@audio:
        ; A main-thread MMC1 register write must not be interrupted by the
        ; song's bank switch; skip one tick instead (the write is short).
        lda     _nes_mmc1_busy
        bne     @skip_audio
        jsr     _nes_audio_tick
@skip_audio:
        pla
        tax
        pla
        tay
        pla
        rti
.endproc
