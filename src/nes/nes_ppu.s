; Buffered PPU-memory writes for the NES runtime (ca65 syntax).
;
; void __cdecl__ nes_ppu_put(unsigned char value, unsigned int addr)
;   Queue one byte for the custom NMI handler, which writes it during vblank
;   and resets the scroll.  The cdecl stack has addr on top, then value.
;   ppubuf_put (cc65 2.18) wants A=value, Y=addr high, X=addr low.

        .include        "zeropage.inc"
        .include        "nes.inc"

        .import         popa, popax, ppubuf_put, ppubuf_flush
        .import         _nes_split_on, _nes_sprite_y, _nes_update_lock
        .export         _nes_ppu_put, _nes_nmi, _nes_init_sprite, _nes_ringcount

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

; void nes_init_sprite(void)
;   Clear OAM and place sprite 0 at the right edge with the collision tile.
.proc   _nes_init_sprite
        lda     #0
        sta     PPU_SPR_ADDR
        ldx     #0
        lda     #$FF
@clear:
        sta     PPU_SPR_IO
        dex
        bne     @clear
        lda     #0
        sta     PPU_SPR_ADDR
        lda     _nes_sprite_y
        sta     PPU_SPR_IO
        lda     #192
        sta     PPU_SPR_IO
        lda     #0
        sta     PPU_SPR_IO
        lda     #248
        sta     PPU_SPR_IO
        rts
.endproc

; NMI handler installed by tools/targets/nes.py in place of the cc65 one.  It
; flushes the ppubuf, uses background pattern table 0 for the title/art band
; and switches to table 1 on the sprite-0 hit at the bottom of the art band.
; A locked menu update defers the flush until the next frame.
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
        bne     @noflush
        jsr     ppubuf_flush
@noflush:

        lda     #$20
        sta     PPU_VRAM_ADDR2
        lda     #$00
        sta     PPU_VRAM_ADDR2
        sta     PPU_VRAM_ADDR1
        sta     PPU_VRAM_ADDR1

        lda     #$88            ; NMI on, sprite table 1, background table 0
        sta     PPU_CTRL1
        lda     _nes_split_on
        beq     @done

        lda     PPU_STATUS      ; clear an old sprite-0 hit
        ldx     #0
        ldy     #$06            ; bounded wait (about 20k cycles)
@wait:
        lda     PPU_STATUS
        and     #$40
        bne     @hit
        dex
        bne     @wait
        dey
        bne     @wait
        jmp     @done           ; no hit: keep table 0 (art stays intact)
@hit:
        lda     #$98            ; text pane uses background table 1
        sta     PPU_CTRL1
@done:
        pla
        tax
        pla
        tay
        pla
        rti
.endproc
