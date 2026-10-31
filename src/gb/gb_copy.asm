; Raw banked-blob copy for the Game Boy Color runtime.
;
; void port_unpack(const void *src, void *dst);
;   The selected MBC1 bank maps at 0x4000; src points at a [u16 length][blob]
;   record there.  This routine stays in the fixed bank so the copy survives
;   the caller's bank switch.
SECTION code_driver

PUBLIC _port_unpack

_port_unpack:
        ld      hl,4
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)          ; DE = src
        ld      hl,2
        add     hl,sp
        ld      a,(hl)
        inc     hl
        ld      h,(hl)
        ld      l,a             ; HL = dst
        ld      a,(de)
        inc     de
        ld      c,a
        ld      a,(de)
        inc     de
        ld      b,a
        ld      a,b
        or      c
        ret     z
copy:
        ld      a,(de)
        ld      (hl),a
        inc     de
        inc     hl
        dec     bc
        ld      a,b
        or      c
        jr      nz,copy
        ret
