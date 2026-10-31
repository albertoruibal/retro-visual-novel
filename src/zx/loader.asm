; ---------------------------------------------------------------------------
; Startup bank loader for the 128K adventure.
;
; The BASIC loader loads the NIRVANAP+ engine (@56323) and main binary
; (@32768), then USRs into the game. main() calls load_banks() before starting
; the engine ISR: it walks _scene_bank_list and, for each bank that is not
; already resident (checked via a signature byte), reads one headerless 16K
; tape block into 0xC000 using the ROM LD-BYTES routine.
;
; A .sna snapshot already has every bank resident (and no tape to read), so the
; signature check makes load_banks() return immediately there.
;
; Runs before NIRVANAP is started, so ROM IM1 and the ROM loader are still in
; place. Code/stack are in the fixed 0x8000 region, so paging 0xC000 is safe.
; ---------------------------------------------------------------------------

SECTION code_user
PUBLIC _load_banks
EXTERN _scene_bank_list

BANK_MAGIC: equ   0x5C

_load_banks:
        ld      hl,_scene_bank_list
next:
        ld      a,(hl)
        inc     hl
        cp      0xFF
        jr      z,done
        push    hl                      ; save list pointer
        call    bank_present            ; A = bank; Z if already resident
        ld      c,a
        jr      z,skip
        ld      ix,0xC000               ; destination
        ld      de,0x4000               ; length
        call    load_block
skip:
        pop     hl
        jr      next
done:
        ld      a,16                    ; back to home bank 0
        ld      (23388),a
        ld      bc,32765
        out     (c),a
        ret

; A = bank number. Pages it in and compares byte 0 with BANK_MAGIC.
; Returns Z if the bank already holds our data (A = bank number either way).
bank_present:
        ld      e,a
        or      16
        di
        ld      (23388),a
        ld      bc,32765
        out     (c),a
        ld      a,(0xC000)
        cp      BANK_MAGIC
        push    af
        ld      a,16
        ld      (23388),a
        ld      bc,32765
        out     (c),a
        ei
        pop     af
        ld      a,e
        ret

; Read one headerless 16K tape data block into (IX) after paging bank C.
load_block:
        ld      a,c
        or      16
        di
        res     4,(iy+1)                ; disable +2A/+3 motor timer
        ld      (23388),a
        ld      bc,32765
        out     (c),a
        ei
        ld      hl,(23613)
        push    hl
        ld      hl,lb1
        push    hl
        ld      (23613),sp
        ld      a,255                   ; expect a data block
        scf                             ; load
        call    1366                    ; ROM LD-BYTES (0x0556)
lb1:
        pop     hl
        pop     hl
        ld      (23613),hl
        ret
