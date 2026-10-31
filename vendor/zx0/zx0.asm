; ---------------------------------------------------------------------------
; ZX0 decoder by Einar Saukas -- "Standard" version (69 bytes).
;
; Vendored from z88dk libsrc/compress/zx0/z80/dzx0_standard.asm (BSD 3-Clause,
; see LICENSE). This project calls it directly from src/zx/paging.asm, so the
; routine is kept LOCAL to code_user (fixed 0x8000..0xBFFF) and exposed as
; zx0_unpack; it deliberately does not use the z88dk "asm_dzx0_standard"
; symbol to keep it independent of the clib. The CPC target assembles it into
; code_l instead (see the conditional below), because it pages 0x4000.
;
; void zx0_unpack(const void *src, void *dst)
;   HL = source (compressed data), DE = destination. ZX0 is self-terminating,
;   so no length is needed. The decoder uses the stack, which lives in the
;   screen region below 0x8000; the caller only pages 0xC000, so it is safe.
; ---------------------------------------------------------------------------

; Targets that map a RAM bank over 0x4000 while decoding (CPC) assemble this
; with -Ca-DZX0_LOW so the decoder lands in the low code section instead.
IFDEF ZX0_LOW
SECTION code_l
ELSE
SECTION code_user
ENDIF

PUBLIC _zx0_unpack

_zx0_unpack:
        ld      bc, $ffff               ; preserve default offset 1
        push    bc
        inc     bc
        ld      a, $80
dzx0s_literals:
        call    dzx0s_elias             ; obtain length
        ldir                            ; copy literals
        add     a, a                    ; copy from last offset or new offset?
        jr      c, dzx0s_new_offset
        call    dzx0s_elias             ; obtain length
dzx0s_copy:
        ex      (sp), hl                ; preserve source, restore offset
        push    hl                      ; preserve offset
        add     hl, de                  ; calculate destination - offset
        ldir                            ; copy from offset
        pop     hl                      ; restore offset
        ex      (sp), hl                ; preserve offset, restore source
        add     a, a                    ; copy from literals or new offset?
        jr      nc, dzx0s_literals
dzx0s_new_offset:
        call    dzx0s_elias             ; obtain offset MSB
        ex      af, af'
        pop     af                      ; discard last offset
        xor     a                       ; adjust for negative offset
        sub     c
        ret     z                       ; check end marker
        ld      b, a
        ex      af, af'
        ld      c, (hl)                 ; obtain offset LSB
        inc     hl
        rr      b                       ; last offset bit becomes first length bit
        rr      c
        push    bc                      ; preserve new offset
        ld      bc, 1                   ; obtain length
        call    nc, dzx0s_elias_backtrack
        inc     bc
        jr      dzx0s_copy
dzx0s_elias:
        inc     c                       ; interlaced Elias gamma coding
dzx0s_elias_loop:
        add     a, a
        jr      nz, dzx0s_elias_skip
        ld      a, (hl)                 ; load another group of 8 bits
        inc     hl
        rla
dzx0s_elias_skip:
        ret     c
dzx0s_elias_backtrack:
        add     a, a
        rl      c
        rl      b
        jr      dzx0s_elias_loop
; -----------------------------------------------------------------------------
