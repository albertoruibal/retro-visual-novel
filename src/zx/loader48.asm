; ---------------------------------------------------------------------------
; Startup loader for the non-paged Spectrum 48K adventure.
;
; Unlike src/zx/loader.asm there is no bank switching: the compressed scene
; store is one headerless tape block read into lower RAM at FLAT_DATA_ADDR
; (0x6000). Art and inventory are linked into the main image. The top 1 KB of
; lower RAM is left for the stack (REGISTER_SP is set to 0x7FFE by the build),
; so the ROM LD-BYTES routine and its interrupt cannot overwrite the data.
;
; Runs before the game starts, so the ROM IM1 handler and the ROM loader are
; still in place.
; ---------------------------------------------------------------------------

SECTION code_user
PUBLIC _load_banks

_load_banks:
        ld      ix,FLAT_DATA_ADDR
        ld      de,FLAT_DATA_SIZE
        ld      hl,(23613)              ; save ERR_SP
        push    hl
        ld      hl,lb_done
        push    hl
        ld      (23613),sp
        ld      a,255                   ; expect a data block
        scf                             ; load
        call    1366                    ; ROM LD-BYTES (0x0556)
lb_done:
        pop     hl
        pop     hl
        ld      (23613),hl
        ret
