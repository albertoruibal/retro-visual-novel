; CPC 464 art/song loader.
;
; void cpc_disk_unpack(unsigned int bank, unsigned int off,
;                      void *dst, void *buf);
; void cpc_disk_unpack_slow(unsigned int bank, unsigned int off,
;                           void *dst, void *buf);
;
; The 464 has no extra 16K banks, so the compressed art/song blobs are stored
; in the GAME.Bn files on the disk (written by appmake from the BANK_n
; sections).  Both routines open the bank file, read its [u16 compressed
; length][zx0 stream] payload at ``off`` into the caller's buffer and decode it
; to dst.
;
; ``cpc_disk_unpack`` uses CAS_IN_DIRECT for speed: the whole bank file is read
; into the screen (which the caller has already blanked), the wanted blob is
; copied to the buffer, and then decoded over the screen.  It is only safe
; while the screen is about to be redrawn.
;
; ``cpc_disk_unpack_slow`` uses CAS_IN_CHAR, so it never touches screen memory.
; It is used for songs, which must not disturb the picture when the player
; toggles music or a scene keeps the same art.
        SECTION code_l
        PUBLIC  _cpc_disk_unpack
        PUBLIC  _cpc_disk_unpack_slow
        EXTERN  _zx0_unpack
        EXTERN  firmware
        INCLUDE "target/cpc/def/cpcfirm.def"

; Set up the filename/offsets and open GAME.B<bank>.
; A = bank number.  Returns carry set when the file could not be opened.
disk_prepare:
        and     $0F
        add     a,'0'
        cp      '9'+1
        jr      c,disk_name_ok
        add     a,7
disk_name_ok:
        ld      (disk_name_end),a
        ld      hl,0
        ld      (disk_len),hl

        ld      a,0
        call    firmware
        defw    cas_noisy         ; suppress tape/disk messages

        ld      de,(disk_stream)  ; 2K stream buffer for CAS_IN_OPEN
        ld      hl,disk_name
        ld      b,7
        call    firmware
        defw    cas_in_open
        ret

disk_restore:
        ld      bc,$7FC0
        out     (c),c             ; firmware may leave the Gate Array map changed
        ret

disk_decode:
        ld      hl,(disk_len)
        ld      a,h
        or      l
        ret     z
        ld      hl,(disk_buf)
        inc     hl
        inc     hl
        ld      de,(disk_dst)
        jp      _zx0_unpack

disk_fail_close:
        call    firmware
        defw    cas_in_close
disk_fail:
        call    disk_restore
        ret

; Fast path: the whole bank is read into the blank screen at 0xC000.
_cpc_disk_unpack:
        ; sccz80 arguments: buf=sp+2, dst=sp+4, off=sp+6, bank=sp+8
        ld      hl,2
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)
        ld      (disk_buf),de

        ld      hl,4
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)
        ld      (disk_dst),de

        ld      hl,6
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)
        ld      (disk_off),de

        ld      hl,$C000
        ld      (disk_stream),hl  ; the screen is about to be overwritten
        ld      hl,8
        add     hl,sp
        ld      a,(hl)            ; bank number (2..7)
        call    disk_prepare
        jp      nc,disk_fail

        ld      hl,$C000
        call    firmware
        defw    cas_in_direct
        jp      nc,disk_fail_close

        call    firmware
        defw    cas_in_close
        call    disk_restore

        ; The whole bank is now at 0xC000.  Copy the wanted blob's payload
        ; (after its u16 length) into the caller's buffer.
        ld      hl,(disk_off)
        ld      de,$C000
        add     hl,de
        ld      e,(hl)
        inc     hl
        ld      d,(hl)            ; DE = compressed length
        ld      (disk_len),de

        ld      hl,(disk_off)
        ld      de,$C002
        add     hl,de             ; HL = 0xC000 + off + 2
        ld      de,(disk_buf)
        inc     de
        inc     de                ; DE = buf + 2
        ld      bc,(disk_len)
        ldir
        jp      disk_decode

; Slow path: character-by-character, leaving screen memory alone.
_cpc_disk_unpack_slow:
        ; sccz80 arguments: buf=sp+2, dst=sp+4, off=sp+6, bank=sp+8
        ld      hl,2
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)
        ld      (disk_buf),de

        ld      hl,4
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)
        ld      (disk_dst),de

        ld      hl,6
        add     hl,sp
        ld      e,(hl)
        inc     hl
        ld      d,(hl)
        ld      (disk_off),de

        ld      hl,(disk_dst)
        ld      (disk_stream),hl  ; song workspace, never the visible screen
        ld      hl,8
        add     hl,sp
        ld      a,(hl)
        call    disk_prepare
        jp      nc,disk_fail

disk_skip:
        ld      hl,(disk_off)
        ld      a,h
        or      l
        jr      z,disk_read_len
        call    firmware
        defw    cas_in_char
        jr      c,disk_skip_byte
        cp      $1A                ; binary data can contain the CP/M EOF byte
        jp      nz,disk_fail_close
disk_skip_byte:
        ld      hl,(disk_off)
        dec     hl
        ld      (disk_off),hl
        jp      disk_skip

disk_read_len:
        call    firmware
        defw    cas_in_char
        jr      c,disk_len_low
        cp      $1A
        jp      nz,disk_fail_close
disk_len_low:
        ld      hl,(disk_buf)
        ld      (hl),a
        call    firmware
        defw    cas_in_char
        jr      c,disk_len_high
        cp      $1A
        jp      nz,disk_fail_close
disk_len_high:
        ld      hl,(disk_buf)
        inc     hl
        ld      (hl),a

        ld      hl,(disk_buf)
        ld      e,(hl)
        inc     hl
        ld      d,(hl)
        ld      (disk_len),de

        ld      hl,(disk_buf)
        inc     hl
        inc     hl
        ld      (disk_ptr),hl
        ld      hl,(disk_len)
        ld      (disk_count),hl

disk_read_loop:
        ld      hl,(disk_count)
        ld      a,h
        or      l
        jr      z,disk_read_done
        call    firmware
        defw    cas_in_char
        jr      c,disk_read_byte
        cp      $1A
        jp      nz,disk_fail_close
disk_read_byte:
        ld      hl,(disk_ptr)
        ld      (hl),a
        inc     hl
        ld      (disk_ptr),hl
        ld      hl,(disk_count)
        dec     hl
        ld      (disk_count),hl
        jp      disk_read_loop

disk_read_done:
        call    firmware
        defw    cas_in_close
        call    disk_restore
        jp      disk_decode

disk_buf:       defw 0
disk_dst:       defw 0
disk_stream:    defw 0
disk_off:       defw 0
disk_len:       defw 0
disk_ptr:       defw 0
disk_count:     defw 0
disk_name:      defb 'G','A','M','E','.','B'
disk_name_end:  defb '0'
