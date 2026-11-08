/*
 * Standard ZX0 decoder for the 6502 targets (Commodore 64, NES and Oric Atmos).
 *
 * This is a small C port of ``gen_scenes.zx0_decompress`` (the same standard
 * stream that ``z88dk-zx0`` emits and the vendored Z80 decoder reads).  It
 * deliberately uses no zero page and no assembly: the 6502 targets link this
 * file directly and call ``port_unpack(src, dst)`` for the scene, inventory
 * and (on the C64) art blobs.  The stream is self-terminating.
 */
#define READ_BYTE() (last_byte = *src++)
#define READ_BIT() \
    (backtrack ? (backtrack = 0, (unsigned char)(last_byte & 1)) : \
     ((bit_mask >>= 1) != 0 \
      ? (unsigned char)((bit_value & bit_mask) ? 1 : 0) \
      : (bit_mask = 128, bit_value = *src++, \
         (unsigned char)((bit_value & bit_mask) ? 1 : 0))))
#define READ_ELIAS(value) \
    do { \
        (value) = 1; \
        while (!READ_BIT()) \
            (value) = (unsigned int)(((value) << 1) | READ_BIT()); \
    } while (0)
#define COPY_MATCH(offset, length) \
    do { \
        unsigned int _n = (length); \
        while (_n) { \
            *dst = *(dst - (offset)); \
            dst++; \
            _n--; \
        } \
    } while (0)

void port_unpack(const void *src_, void *dst_)
{
    const unsigned char *src = (const unsigned char *)src_;
    unsigned char *dst = (unsigned char *)dst_;
    unsigned char bit_mask = 0, bit_value = 0, backtrack = 0, last_byte = 0;
    unsigned int last_offset = 1, n;
    unsigned char state = 0;          /* 0 literals, 1 last offset, 2 new offset */

    for (;;) {
        if (state == 0) {
            READ_ELIAS(n);
            while (n--)
                *dst++ = READ_BYTE();
            state = (unsigned char)(READ_BIT() ? 2 : 1);
        } else if (state == 1) {
            READ_ELIAS(n);
            COPY_MATCH(last_offset, n);
            state = (unsigned char)(READ_BIT() ? 2 : 0);
        } else {
            READ_ELIAS(last_offset);
            if (last_offset == 256)
                return;
            last_offset = (unsigned int)(((last_offset - 1) << 7) + 128
                                         - (READ_BYTE() >> 1));
            backtrack = 1;
            READ_ELIAS(n);
            COPY_MATCH(last_offset, n + 1);
            state = (unsigned char)(READ_BIT() ? 2 : 0);
        }
    }
}

#undef READ_BYTE
#undef READ_BIT
#undef READ_ELIAS
#undef COPY_MATCH
