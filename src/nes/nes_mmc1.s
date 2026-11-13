; MMC1 (mapper 1) helpers for the NES runtime (ca65 syntax).
;
; The cartridge is 32KB PRG (banks 0 and 1: bank 0 at $8000, bank 1 fixed at
; $C000), 8KB CHR ROM banks, and 8KB PRG RAM at $6000.  MMC1 registers are
; written serially, least-significant bit first, to an address in the
; register's range ($8000 control, $A000 CHR0, $C000 CHR1, $E000 PRG).

        .export _nes_chr_bank
        .export _nes_prg_bank
        .export _nes_mmc1_init
        .export _nes_mmc1_busy

        .segment "BSS"
; Set while the main thread is clocking a register into the MMC1 serial port.
; The NMI song player must not start its own five-write sequence in the middle
; of one, so it skips a tick when this is non-zero.
_nes_mmc1_busy: .res 1

        .segment "CODE"

; void nes_chr_bank(unsigned char bank)
.proc _nes_chr_bank
        pha
        lda     #1
        sta     _nes_mmc1_busy
        pla
        asl     a               ; 8KB CHR mode: register bit 0 is ignored
        ldx     #5
@l:     pha
        and     #$01
        sta     $A000
        pla
        lsr     a
        dex
        bne     @l
        lda     #0
        sta     _nes_mmc1_busy
        rts
.endproc


; void nes_prg_bank(unsigned char bank)
;   Select one 16K PRG bank at $8000.  MMC1 mode 3 keeps the last bank fixed
;   at $C000, so this is safe from code in the fixed bank.
.proc _nes_prg_bank
        pha
        lda     #1
        sta     _nes_mmc1_busy
        pla
        ldx     #5
@l:     pha
        and     #$01
        sta     $E000
        pla
        lsr     a
        dex
        bne     @l
        lda     #0
        sta     _nes_mmc1_busy
        rts
.endproc

; void nes_mmc1_init(void)
.proc _nes_mmc1_init
        lda     #1
        sta     _nes_mmc1_busy
        lda     #$0C            ; horizontal mirroring, fix last bank, 8K CHR
        ldx     #5
@ctl:   pha
        and     #$01
        sta     $8000
        pla
        lsr     a
        dex
        bne     @ctl
        lda     #$00            ; PRG bank 0, PRG RAM enabled
        ldx     #5
@prg:   pha
        and     #$01
        sta     $E000
        pla
        lsr     a
        dex
        bne     @prg
        lda     #$00
        jmp     _nes_chr_bank
.endproc
