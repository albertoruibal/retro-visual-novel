; NES music + UI sound-effect tick (ca65 syntax).
;
; Called from the custom NMI after the PPU split logic.  Everything here runs
; from the fixed bank: the music reader briefly maps a song bank at $8000 and
; restores bank 0 before returning, and the SFX sequencer overlays short
; pulse-2 notes on top of the song.  The code never calls C: a C function would
; clobber the main thread's zero-page temporaries and soft stack.
;
; Music state lives in nes_music.c so the main thread can start/stop a song.
; The song stream command format is defined by tools/nesmusic.py.

        .import         _nes_music_playing, _nes_music_bank
        .import         _nes_music_off, _nes_music_wait, _nes_music_div
        .import         _nes_music_sh_vol, _nes_music_sh_lo
        .import         _nes_music_sh_hi, _nes_music_sh_valid
        .import         _nes_sfx_request
        .import         _nes_prg_bank

        .export         _nes_audio_tick

.segment "ZEROPAGE"
music_ptr:      .res 2
sfx_ptr:        .res 2

.segment "BSS"
audio_tmp:      .res 1
audio_reg:      .res 1
audio_value:    .res 1
sfx_active:     .res 1
sfx_wait:       .res 1
sfx_restore:    .res 1
sfx_reg:        .res 1
sfx_value:      .res 1
sfx_delay:      .res 1

.segment "CODE"

.proc _nes_audio_tick
        jsr     sfx_tick
        jsr     sfx_restore_music
        jsr     music_tick
        rts
.endproc

; ---------------------------------------------------------------- UI sounds
; Sequence format: (APU offset, value, NMI frames) tuples, terminated by
; $FF.  A zero frame count applies the next tuple in the same tick.
sfx_tick:
        lda     sfx_active
        bne     @active
        lda     _nes_sfx_request
        beq     @done
        sec
        sbc     #1
        sta     _nes_sfx_request
        asl     a
        tax
        lda     sfx_table,x
        sta     sfx_ptr
        lda     sfx_table+1,x
        sta     sfx_ptr+1
        lda     #1
        sta     sfx_active
        lda     #0
        sta     sfx_wait
@active:
        lda     sfx_wait
        beq     @process
        dec     sfx_wait
        rts
@process:
        ldy     #0
        lda     (sfx_ptr),y
        cmp     #$FF
        beq     @end
        sta     sfx_reg
        iny
        lda     (sfx_ptr),y
        sta     sfx_value
        iny
        lda     (sfx_ptr),y
        sta     sfx_delay
        clc
        lda     sfx_ptr
        adc     #3
        sta     sfx_ptr
        bcc     @apply
        inc     sfx_ptr+1
@apply:
        ldx     sfx_reg
        lda     sfx_value
        jsr     sfx_write
        lda     sfx_delay
        sta     sfx_wait
        beq     @process
        rts
@end:
        lda     #0
        sta     sfx_active
        lda     #1
        sta     sfx_restore
@done:
        rts

sfx_write:
        cpx     #$04
        beq     @ctrl
        cpx     #$06
        beq     @lo
        cpx     #$07
        beq     @hi
        rts
@ctrl:
        sta     $4004
        rts
@lo:
        sta     $4006
        rts
@hi:
        sta     $4007
        rts

; Restore the music's pulse-2 state after an SFX, or silence pulse 2 when no
; song is playing.  Runs before music_tick so a fresh music write wins.
sfx_restore_music:
        lda     sfx_restore
        beq     @done
        lda     sfx_active
        bne     @done
        lda     #0
        sta     sfx_restore
        lda     _nes_music_playing
        beq     @silence
        lda     _nes_music_sh_valid
        beq     @silence
        lda     _nes_music_sh_vol
        sta     $4004
        lda     _nes_music_sh_lo
        sta     $4006
        lda     _nes_music_sh_hi
        sta     $4007
        rts
@silence:
        lda     #$30
        sta     $4004
        lda     #0
        sta     $4006
        sta     $4007
@done:
        rts

; ------------------------------------------------------------------- music
music_tick:
        lda     _nes_music_playing
        bne     @playing
        jmp     @done
@playing:
        lda     _nes_music_div
        clc
        adc     #5
        sta     _nes_music_div
        cmp     #6
        bcs     @div_ok
        jmp     @done
@div_ok:
        sec
        sbc     #6
        sta     _nes_music_div
        lda     _nes_music_wait
        beq     @process
        dec     _nes_music_wait
        rts
@process:
        lda     _nes_music_off
        sta     music_ptr
        lda     _nes_music_off+1
        ora     #$80            ; the song bank is mapped at $8000
        sta     music_ptr+1
        lda     _nes_music_bank
        jsr     _nes_prg_bank
@loop:
        jsr     audio_read
        cmp     #0
        beq     @end
        cmp     #1
        beq     @end
        cmp     #$80
        bcs     @wait
        cmp     #$20
        bcc     @loop
        sec
        sbc     #$20
        sta     audio_reg
        jsr     audio_read
        ldx     audio_reg
        jsr     audio_write
        jmp     @loop
@wait:
        and     #$7F
        sta     _nes_music_wait
        jmp     @exit
@end:
        lda     #0
        sta     _nes_music_playing
        sta     _nes_music_sh_valid
        lda     #$30
        sta     $4000
        lda     #0
        sta     $4008
        lda     #$30
        sta     $400C
        lda     sfx_active
        bne     @exit
        lda     #$30
        sta     $4004
@exit:
        lda     music_ptr
        sta     _nes_music_off
        lda     music_ptr+1
        and     #$3F            ; back to a 0..$3FFF offset within the bank
        sta     _nes_music_off+1
        lda     #0
        jsr     _nes_prg_bank
@done:
        rts

; Read one stream byte, advancing the pointer and switching to the next PRG
; bank when the 16K window wraps.  Returns the byte in A.
audio_read:
        ldy     #0
        lda     (music_ptr),y
        sta     audio_tmp
        inc     music_ptr
        bne     @check
        inc     music_ptr+1
@check:
        lda     music_ptr+1
        cmp     #$C0
        bcc     @done
        lda     #0
        sta     music_ptr
        lda     #$80
        sta     music_ptr+1
        inc     _nes_music_bank
        lda     _nes_music_bank
        jsr     _nes_prg_bank
@done:
        lda     audio_tmp
        rts

; Write A to the APU register selected by X (offset from $4000).  Pulse-2
; writes update the shadow used to resume the song after an SFX, and are held
; back while an SFX owns the channel.
audio_write:
        sta     audio_value
        cpx     #$00
        beq     @p1ctrl
        cpx     #$02
        beq     @p1lo
        cpx     #$03
        beq     @p1hi
        cpx     #$04
        beq     @p2ctrl
        cpx     #$06
        beq     @p2lo
        cpx     #$07
        beq     @p2hi
        cpx     #$08
        beq     @trictrl
        cpx     #$0A
        beq     @trilo
        cpx     #$0B
        beq     @trihi
        cpx     #$0C
        beq     @noisectrl
        cpx     #$0E
        beq     @noiseper
        cpx     #$0F
        beq     @noisehi
        rts
@p1ctrl:
        lda     audio_value
        sta     $4000
        rts
@p1lo:
        lda     audio_value
        sta     $4002
        rts
@p1hi:
        lda     audio_value
        sta     $4003
        rts
@p2ctrl:
        lda     audio_value
        sta     _nes_music_sh_vol
        lda     #1
        sta     _nes_music_sh_valid
        lda     sfx_active
        bne     @done
        lda     audio_value
        sta     $4004
        rts
@p2lo:
        lda     audio_value
        sta     _nes_music_sh_lo
        lda     #1
        sta     _nes_music_sh_valid
        lda     sfx_active
        bne     @done
        lda     audio_value
        sta     $4006
        rts
@p2hi:
        lda     audio_value
        sta     _nes_music_sh_hi
        lda     #1
        sta     _nes_music_sh_valid
        lda     sfx_active
        bne     @done
        lda     audio_value
        sta     $4007
        rts
@trictrl:
        lda     audio_value
        sta     $4008
        rts
@trilo:
        lda     audio_value
        sta     $400A
        rts
@trihi:
        lda     audio_value
        sta     $400B
        rts
@noisectrl:
        lda     audio_value
        sta     $400C
        rts
@noiseper:
        lda     audio_value
        sta     $400E
        rts
@noisehi:
        lda     audio_value
        sta     $400F
@done:
        rts

; Pulse-2 SFX sequences.  Values: duty 2 + length halt + constant volume.
; The last tuple silences the channel; sfx_restore then puts the music back.
; The table lives in bank 0: the NMI starts with bank 0 mapped and reads it
; before the music tick can switch in a song bank.
.segment "RODATA"
sfx_table:
        .word   sfx_move, sfx_confirm, sfx_back, sfx_pick, sfx_drop, sfx_error
sfx_move:
        .byte   $04, $BF, 1, $06, $7E, 0, $07, $F8, 1, $04, $30, 1, $FF
sfx_confirm:
        .byte   $04, $BF, 0, $06, $6A, 0, $07, $F8, 2
        .byte   $06, $54, 0, $07, $F8, 2, $04, $30, 1, $FF
sfx_back:
        .byte   $04, $BF, 0, $06, $54, 0, $07, $F8, 2
        .byte   $06, $6A, 0, $07, $F8, 2, $04, $30, 1, $FF
sfx_pick:
        .byte   $04, $BF, 0, $06, $7E, 0, $07, $F8, 1
        .byte   $06, $6A, 0, $07, $F8, 1, $06, $54, 0, $07, $F8, 2
        .byte   $04, $30, 1, $FF
sfx_drop:
        .byte   $04, $BF, 0, $06, $54, 0, $07, $F8, 1
        .byte   $06, $6A, 0, $07, $F8, 1, $06, $7E, 0, $07, $F8, 2
        .byte   $04, $30, 1, $FF
sfx_error:
        .byte   $04, $BF, 0, $06, $2F, 0, $07, $FA, 3
        .byte   $06, $3B, 0, $07, $FA, 3, $04, $30, 1, $FF
