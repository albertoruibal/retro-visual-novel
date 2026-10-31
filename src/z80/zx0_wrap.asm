; C-callable wrapper around the vendored ZX0 decoder.
; void port_unpack(const void *src, void *dst);
SECTION code_user
PUBLIC _port_unpack
EXTERN _zx0_unpack

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
        ex      de,hl           ; HL = src, DE = dst
        jp      _zx0_unpack
