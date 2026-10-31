; VRAM copy for the Game Boy Color runtime.
;
; void gb_vram_copy(void *dst, const void *src, unsigned int n) __smallc;
;   Waits for a safe LCD mode before each byte, so it is safe both with the
;   LCD off (init, large art uploads) and on (text rows).
SECTION code_driver

PUBLIC _gb_vram_copy

_gb_vram_copy:
        push    bc
        push    de
        push    hl
        ld      hl,8
        add     hl,sp
        ld      c,(hl)
        inc     hl
        ld      b,(hl)          ; BC = n
        ld      hl,12
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)          ; DE = dst
        ld      hl,10
        add     hl,sp
        ld      a,(hl)
        inc     hl
        ld      h,(hl)
        ld      l,a             ; HL = src
loop:
        ld      a,b
        or      c
        jr      z,done
wait:
        ldh     a,(0x41)        ; STAT
        and     0x03
        cp      0x02
        jr      nc,wait         ; wait while OAM/VRAM transfer
        ld      a,(hl+)
        ld      (de),a
        inc     de
        dec     bc
        jr      loop
done:
        pop     hl
        pop     de
        pop     bc
        ret
