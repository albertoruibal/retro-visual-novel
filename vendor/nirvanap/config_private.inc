; ---------------------------------------------------------------------------
; Minimal private build config for the vendored NIRVANA+ engine.
;
; Trimmed from the z88dk source file
;   libsrc/_DEVELOPMENT/target/zx/config/config_nirvanap.m4
; (generated config_private.inc) down to the symbols NIRVANAP_ENGINE.asm.m4
; references. Only __NIRVANAP_TOTAL_ROWS differs from upstream: this project
; uses 256x80 art filling raced attribute rows 1..10, keeps rows 11..21 for
; standard attributes / printf text and rows 22..23 for the two-line inventory
; band, so the engine must only race attribute rows 1..10.
;
; NOTE: comments here must not contain backtick or apostrophe characters,
; because m4 treats them as quote delimiters and mis-parses the file.
; ---------------------------------------------------------------------------

IFNDEF __CONFIG_Z88DK_INC_
defc   __CONFIG_Z88DK_INC_ = 1

; Spectrum 48/128 (non-Pentagon) raster timing
defc   __SPECTRUM          = 1
defc   __SPECTRUM_PENTAGON = 32

; no wide draw / wide sprites
defc   __NIRVANAP_OPTIONS              = 0
defc   __NIRVANAP_OPTIONS_WIDE_DRAW    = 0x01
defc   __NIRVANAP_OPTIONS_WIDE_SPRITES = 0x02

; Raster-race the bicolor attribute rows (the race starts at row 1); row 0
; stays free for the inventory bar. The art is 256x80 (5 tile rows) and lands
; in rows 1..10; rows 11..23 use standard attributes / printf text. The defc
; feeds z80asm IF; the commented define below feeds the m4 loop macro (m4
; still evaluates it, the leading semicolon is only an asm comment).
defc   __NIRVANAP_TOTAL_ROWS  = 10
defc   __NIRVANAP_HOLE        = 59998
defc   _NIRVANAP_HOLE         = 59998
defc   __NIRVANAP_HOLE_SIZE   = 4263

; default tile/char locations
defc   __NIRVANAP_TILE_IMAGES = 48000
defc   __NIRVANAP_WIDE_IMAGES = 54000
defc   __NIRVANAP_CHAR_TABLE  = 15360

; define(`__NIRVANAP_TOTAL_ROWS', 10)

ENDIF
