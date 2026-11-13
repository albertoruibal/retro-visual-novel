; Game Boy Color UI sound effects.
;
; The shared engine calls _plat_sfx() (in gb_music.c), which records a request
; here.  The vblank handler calls _gb_sfx_tick(), which overlays a short
; pulse-2 sequence on the music.  Pulse-2 registers are snapshotted when the
; effect starts and restored when it ends, so a song resumes cleanly.
;
; A sequence step is one byte: bits 7..5 select an NR23 value from _sfx_note,
; bits 2..0 hold the number of extra frames.  0xFF ends the effect.
SECTION code_driver

PUBLIC _gb_sfx_tick
EXTERN _gb_sfx_req
EXTERN _gb_sfx_ptr
EXTERN _gb_sfx_wait
EXTERN _gb_sfx_sh_vol
EXTERN _gb_sfx_sh_lo
EXTERN _gb_sfx_sh_hi
EXTERN _gb_audio_ensure_on

_gb_sfx_tick:
        ld      a,(_gb_sfx_ptr+1)
        or      a
        jr      nz,sfx_active
        ld      a,(_gb_sfx_req)
        or      a
        ret     z
        dec     a
        ld      e,a
        ld      d,0
        ld      hl,_sfx_off
        add     hl,de
        ld      a,(hl)
        ld      hl,_sfx_data
        add     a,l
        ld      l,a
        ld      a,0
        adc     a,h
        ld      h,a
        ld      (_gb_sfx_ptr),hl
        xor     a
        ld      (_gb_sfx_req),a
        ld      (_gb_sfx_wait),a
        call    _gb_audio_ensure_on
        ldh     a,(0x17)
        ld      (_gb_sfx_sh_vol),a
        ldh     a,(0x18)
        ld      (_gb_sfx_sh_lo),a
        ldh     a,(0x19)
        ld      (_gb_sfx_sh_hi),a
        ld      a,0xF0
        ldh     (0x17),a
        ld      a,0x87
        ldh     (0x19),a
sfx_active:
        ld      a,(_gb_sfx_wait)
        or      a
        jr      z,sfx_step
        dec     a
        ld      (_gb_sfx_wait),a
        ret
sfx_step:
        ld      hl,(_gb_sfx_ptr)
        ld      a,(hl+)
        ld      (_gb_sfx_ptr),hl
        cp      0xFF
        jr      z,sfx_finish
        ld      b,a
        and     0x07
        ld      (_gb_sfx_wait),a
        ld      a,b
        swap    a
        rrca
        and     0x07
        ld      hl,_sfx_note
        add     a,l
        ld      l,a
        ld      a,0
        adc     a,h
        ld      h,a
        ld      a,(hl)
        ldh     (0x18),a
        ret
sfx_finish:
        xor     a
        ld      (_gb_sfx_ptr),a
        ld      (_gb_sfx_ptr+1),a
        ld      a,(_gb_sfx_sh_vol)
        ldh     (0x17),a
        ld      a,(_gb_sfx_sh_lo)
        ldh     (0x18),a
        ld      a,(_gb_sfx_sh_hi)
        ldh     (0x19),a
        ret

_sfx_note:
        defb    0x6B, 0x83, 0x9C, 0xC8, 0xBA
_sfx_off:
        defb    0, 2, 5, 8, 12, 16
_sfx_data:
        defb    0x01, 0xFF
        defb    0x22, 0x42, 0xFF
        defb    0x42, 0x22, 0xFF
        defb    0x01, 0x21, 0x42, 0xFF
        defb    0x41, 0x21, 0x02, 0xFF
        defb    0x63, 0x83, 0xFF

