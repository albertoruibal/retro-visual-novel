; SN76489 music glue for the Sega Master System.
;
; void sms_psg_play(void *psg) __smallc;
; void sms_psg_stop(void) __smallc;
; unsigned char sms_detect_region(void) __smallc;
;
; The 0x38 IM1 vector is replaced when a game has songs.  It acknowledges the
; VDP interrupt and advances PSGlib at 50 Hz: every vblank on a PAL console,
; five of every six vblanks on NTSC.  Code lives in the fixed 0x0000..0x7FFF
; region, so a mapped data bank cannot cover it.

SECTION code_user

PUBLIC _sms_psg_play
EXTERN asm_PSGlib_Play

_sms_psg_play:
        ld      hl,2
        add     hl,sp
        ld      a,(hl)
        inc     hl
        ld      h,(hl)
        ld      l,a
        jp      asm_PSGlib_Play

PUBLIC _sms_psg_stop
EXTERN asm_PSGlib_Stop

_sms_psg_stop:
        jp      asm_PSGlib_Stop

PUBLIC _sms_detect_region
EXTERN asm_SMSlib_detect_VDP_type
EXTERN __SMSlib_VDPType

_sms_detect_region:
        call    asm_SMSlib_detect_VDP_type
        ld      a,(__SMSlib_VDPType)
        ld      l,a
        ld      h,0
        ret

PUBLIC _z80_rst_38h
EXTERN asm_PSGlib_Frame
EXTERN _sms_music_enabled
EXTERN _sms_music_region
EXTERN _sms_music_acc

_z80_rst_38h:
        push    af
        push    bc
        push    de
        push    hl
        in      a,(0xBF)            ; acknowledge the VDP interrupt
        rlca
        jr      nc,music_done       ; not a frame interrupt
        ld      a,(_sms_music_enabled)
        or      a
        jr      z,music_done
        ld      a,(_sms_music_region)
        cp      0x80                ; VDP_PAL
        jr      z,music_play        ; 50 Hz console: every frame
        ld      a,(_sms_music_acc)   ; NTSC 60 Hz -> 50 Hz (5 of 6 frames)
        add     a,5
        cp      6
        jr      nc,music_step
        ld      (_sms_music_acc),a
        jr      music_done
music_step:
        sub     6
        ld      (_sms_music_acc),a
music_play:
        call    asm_PSGlib_Frame
music_done:
        pop     hl
        pop     de
        pop     bc
        pop     af
        ei
        reti
