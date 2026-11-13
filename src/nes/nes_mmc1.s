; MMC1 (mapper 1) helpers for the NES runtime (ca65 syntax).
;
; The cartridge is 32KB PRG (banks 0 and 1: bank 0 at $8000, bank 1 fixed at
; $C000), 8KB CHR ROM banks, and 8KB PRG RAM at $6000.  MMC1 registers are
; written serially, least-significant bit first, to an address in the
; register's range ($8000 control, $A000 CHR0, $C000 CHR1, $E000 PRG).

        .export _nes_chr_bank
        .export _nes_prg_bank
        .export _nes_mmc1_init

        .segment "CODE"

; void nes_chr_bank(unsigned char bank)
.proc _nes_chr_bank
        asl     a               ; 8KB CHR mode: register bit 0 is ignored
        ldx     #5
@l:     pha
        and     #$01
        sta     $A000
        pla
        lsr     a
        dex
        bne     @l
        rts
.endproc


; void nes_prg_bank(unsigned char bank)
;   Select one 16K PRG bank at $8000.  MMC1 mode 3 keeps the last bank fixed
;   at $C000, so this is safe from code in the fixed bank.
.proc _nes_prg_bank
        ldx     #5
@l:     pha
        and     #$01
        sta     $E000
        pla
        lsr     a
        dex
        bne     @l
        rts
.endproc

; void nes_mmc1_init(void)
.proc _nes_mmc1_init
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
