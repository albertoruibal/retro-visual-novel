; ---------------------------------------------------------------------------
; paged scene fetch for the 128K adventure.
;
; A blob lives compressed (ZX0) inside a paged RAM bank (mapped at 0xC000),
; prefixed by a u16 little-endian length of the compressed stream. Only the
; short page+copy is done with interrupts disabled; the ZX0 decode itself runs
; with interrupts ENABLED from an always-resident staging buffer, so the AY
; player (NIRVANA+ ISR hook) keeps running and the raster race is never paused
; for long.
;
; The paged copy must not hold interrupts across a frame boundary: the
; NIRVANA+ ISR rewrites each bicolor attribute 4 times per frame (once per
; 2-line group), so a single missed race frame leaves the wrong value in
; attribute RAM and the band flashes for one frame. paged_unpack therefore
; syncs to the frame interrupt (halt) and copies at most STAGE_CHUNK bytes per
; frame, so the ISR is never delayed. It then calls the vendored decoder
; (_zx0_unpack, vendor/zx0/zx0.asm) into the caller's workspace with interrupts
; enabled. The decoder and the ISR both use registers/stack that the ISR fully
; preserves, so interrupting the decode is safe.
;
; _stage_ws lives at 0x6000 in the free lower RAM above the screen/system
; variables and below the stack; it is NOT part of the linked fixed region.
; ---------------------------------------------------------------------------

SECTION code_user

PUBLIC _paged_unpack
PUBLIC _crt_font64

EXTERN _zx0_unpack
EXTERN CRT_FONT_64

; unsigned char *crt_font64(void)
; Returns the writeable CRT 4x8 font table so the accent glyphs can be patched
; in place instead of shipping a second 768-byte font in the home bank.
_crt_font64:
        ld      hl,CRT_FONT_64
        ret

; The staging buffer must hold the largest compressed blob (tools/gen_scenes.py
; asserts this). STAGE_CHUNK is the most bytes copied per frame: ~24K T with
; contention, well under the >24K T the tallest band (art_lines=16) leaves free
; each frame.
defc  _stage_ws   = $6000
defc  STAGE_CHUNK = 1024

; void paged_unpack(unsigned int bank, unsigned int src, unsigned int dst)
;
; sccz80 classic pushes args left-to-right, so from the stack pointer:
;     sp+2 = dst (int), sp+4 = src (int), sp+6 = bank (int)
; src is the logical address of the length-prefixed compressed blob inside the
; paged bank (0xC000+off); dst is the workspace to decompress into.
_paged_unpack:
        ld      hl,6
        add     hl,sp
        ld      a,(hl)                  ; bank (low byte)
        ld      (_paged_newbank),a

        ld      hl,4
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)                  ; DE = src
        ld      (_paged_src),de

        ld      hl,2
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)                  ; DE = dst
        ld      (_paged_dst),de

        ld      hl,_stage_ws
        ld      (_paged_stage),hl

        ; --- frame 1: read the u16 length and copy the first chunk ----------
        halt                            ; wait for the ISR, then run a full frame
        di
        call    paged_page_in
        ld      hl,(_paged_src)
        ld      e,(hl)
        inc     hl
        ld      d,(hl)                  ; DE = compressed length
        inc     hl
        ld      (_paged_src),hl
        ld      (_paged_rem),de
        call    paged_chunk
        call    paged_page_out
        ei

        ; --- remaining chunks, one per frame --------------------------------
paged_loop:
        ld      hl,(_paged_rem)
        ld      a,h
        or      l
        jr      z,paged_done
        halt
        di
        call    paged_page_in
        call    paged_chunk
        call    paged_page_out
        ei
        jr      paged_loop

paged_done:
        ; decode from the resident staging buffer (interrupts enabled)
        ld      hl,_stage_ws
        ld      de,(_paged_dst)
        jp      _zx0_unpack

; Copy min(remaining, STAGE_CHUNK) bytes from (_paged_src) to (_paged_stage),
; advancing both and decrementing _paged_rem. Runs with the bank paged in.
paged_chunk:
        ld      de,(_paged_rem)
        ld      a,d
        cp      STAGE_CHUNK >> 8
        jr      c,paged_short           ; rem < STAGE_CHUNK
        ld      bc,STAGE_CHUNK
        jr      paged_have
paged_short:
        ld      b,d
        ld      c,e
paged_have:
        ld      hl,(_paged_src)
        ld      de,(_paged_stage)
        push    bc
        ldir
        pop     bc
        ld      (_paged_src),hl
        ld      (_paged_stage),de
        ld      hl,(_paged_rem)
        ld      a,l
        sub     c
        ld      l,a
        ld      a,h
        sbc     a,b
        ld      h,a
        ld      (_paged_rem),hl
        ret

paged_page_in:
        ld      a,(23388)               ; BANKM
        ld      (_paged_oldbank),a
        and     $f8
        ld      hl,_paged_newbank
        or      (hl)
        ld      (23388),a
        ld      bc,$7ffd
        out     (c),a
        ret

paged_page_out:
        ld      a,(_paged_oldbank)
        ld      (23388),a
        ld      bc,$7ffd
        out     (c),a
        ret

; scratch (below 0xC000)
_paged_oldbank:
        defs    1
_paged_newbank:
        defs    1
_paged_src:
        defs    2
_paged_stage:
        defs    2
_paged_rem:
        defs    2
_paged_dst:
        defs    2

; Scene records (header + strings) are decompressed here before rendering.
; SCENE_WS_SIZE is the largest raw scene blob this game ships (tools/gen_scenes.py
; emits it and tools/build.py passes it with -Ca-D), so a small game does not
; reserve the old fixed 1K slot in the crowded fixed region.
IFNDEF SCENE_WS_SIZE
    defc SCENE_WS_SIZE = 1024
ENDIF
PUBLIC _scene_ws
_scene_ws:
        defs    SCENE_WS_SIZE

; Art blobs (tile map[8*L] + 48-byte btiles, L = `# Game art_lines`) are
; decompressed here before the tiles are drawn. Kept separate from _scene_ws so a
; scene's strings survive while its art is drawn (and vice versa). Both live in
; the fixed region below 0xC000: bank 0 is resident while the decoder writes
; them, so the fixed region is the only always-mapped place for them.
; Single-buffered: the picture lives in the screen bitmap once drawn, so the next
; one is decoded straight over this buffer (the engine points the ISR's sprite
; slots at a blank tile meanwhile). ART_WS_SIZE is sized per game by
; tools/gen_scenes.py (the largest art or inventory blob) and passed by
; tools/build.py with -Ca-D; 4096 is the 256x80-band fallback (80 + 80*48 = 3920
; rounded up) used only when the symbol is absent.
IFNDEF ART_WS_SIZE
    defc ART_WS_SIZE = 4096
ENDIF
PUBLIC _art_ws
_art_ws:
        defs    ART_WS_SIZE
