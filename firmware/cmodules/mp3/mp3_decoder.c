/*
 * mp3 -- MicroPython native module wrapping the picomp3lib (Helix) MP3 decoder.
 *
 * Thin, allocation-free binding: Python keeps doing file I/O (our patched
 * sdcard.py), framing, and I2S output; this module only turns MP3 bytes into
 * 16-bit PCM.  The heavy math runs in fixed-point C on the Cortex-M0+.
 *
 *   import mp3
 *   dec = mp3.Decoder()
 *   consumed, produced, samprate, channels = dec.decode(in_mv, out_buf)
 *     in_mv    : readable buffer of MP3 bytes (a memoryview slice is fine)
 *     out_buf  : writable bytearray, at least mp3.MAX_FRAME_BYTES (4608) long
 *     consumed : bytes consumed from the START of in_mv
 *     produced : PCM bytes written to out_buf (0 => need more input / skipped)
 *     samprate : Hz of the decoded frame (valid when produced > 0)
 *     channels : 1 or 2         (valid when produced > 0)
 *   dec.deinit()   # or GC handles it
 *
 * decode() contract for the caller's sliding input buffer:
 *   - produced > 0            : a frame was decoded; advance input by `consumed`.
 *   - produced == 0, consumed>0: junk/false-sync skipped; advance and retry.
 *   - produced == 0, consumed==0: need more data (refill input, or EOF => stop).
 */

#include "py/runtime.h"
#include "py/obj.h"

#include "mp3dec.h"   /* picomp3lib/src -- added to include path by the cmake */

/* max PCM per frame: MAX_NGRAN(2) * MAX_NCHAN(2) * MAX_NSAMP(576) * 2 bytes */
#define MP3_MAX_FRAME_BYTES (2 * 2 * 576 * 2)   /* 4608 */

typedef struct _mp3_decoder_obj_t {
    mp_obj_base_t base;
    HMP3Decoder h;
} mp3_decoder_obj_t;

// NOTE: no forward declaration of mp3_decoder_type here!  MP_DEFINE_CONST_OBJ_TYPE
// expands to a const object whose trailing `slots` flexible-array storage is sized
// by its initializer; a preceding tentative definition can pin the object at base
// size, corrupting the slots (make_new happened to work, locals_dict lookups
// hard-faulted).  Verified on hardware; keep this file matching
// examples/usercmodule/cexample/examplemodule.c.

static mp_obj_t mp3_decoder_make_new(const mp_obj_type_t *type,
                                     size_t n_args, size_t n_kw, const mp_obj_t *args) {
    mp_arg_check_num(n_args, n_kw, 0, 0, false);
    mp3_decoder_obj_t *self = mp_obj_malloc_with_finaliser(mp3_decoder_obj_t, type);
    self->h = MP3InitDecoder();
    if (self->h == NULL) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("MP3InitDecoder failed"));
    }
    return MP_OBJ_FROM_PTR(self);
}


static mp_obj_t mp3_decoder_decode(mp_obj_t self_in, mp_obj_t in_obj, mp_obj_t out_obj) {
    mp3_decoder_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->h == NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("decoder closed"));
    }

    mp_buffer_info_t ib, ob;
    mp_get_buffer_raise(in_obj, &ib, MP_BUFFER_READ);
    mp_get_buffer_raise(out_obj, &ob, MP_BUFFER_WRITE);
    if (ob.len < MP3_MAX_FRAME_BYTES) {
        mp_raise_ValueError(MP_ERROR_TEXT("out buffer < MAX_FRAME_BYTES"));
    }

    unsigned char *base = (unsigned char *)ib.buf;
    int total = (int)ib.len;
    int consumed = 0, produced = 0, samprate = 0, channels = 0;

    int off = MP3FindSyncWord(base, total);
    if (off < 0) {
        /* no frame sync in this buffer; drop all but the last byte in case a
         * sync word straddles the next refill boundary */
        consumed = (total > 1) ? (total - 1) : 0;
    } else {
        unsigned char *ptr = base + off;
        int left = total - off;
        int err = MP3Decode(self->h, &ptr, &left, (short *)ob.buf, 0);
        if (err == ERR_MP3_INDATA_UNDERFLOW) {
            /* not enough bytes for a whole frame yet; keep from the sync word on */
            consumed = off;
        } else if (err != ERR_MP3_NONE) {
            /* corrupt/false sync: step one byte past it and resync next call */
            consumed = off + 1;
        } else {
            MP3FrameInfo fi;
            MP3GetLastFrameInfo(self->h, &fi);
            consumed = (int)(ptr - base);      /* junk skipped + frame bytes */
            produced = fi.outputSamps * 2;     /* total samples -> bytes (16-bit) */
            samprate = fi.samprate;
            channels = fi.nChans;
        }
    }

    mp_obj_t t[4];
    t[0] = MP_OBJ_NEW_SMALL_INT(consumed);
    t[1] = MP_OBJ_NEW_SMALL_INT(produced);
    t[2] = MP_OBJ_NEW_SMALL_INT(samprate);
    t[3] = MP_OBJ_NEW_SMALL_INT(channels);
    return mp_obj_new_tuple(4, t);
}
static MP_DEFINE_CONST_FUN_OBJ_3(mp3_decoder_decode_obj, mp3_decoder_decode);

static mp_obj_t mp3_decoder_deinit(mp_obj_t self_in) {
    mp3_decoder_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (self->h != NULL) {
        MP3FreeDecoder(self->h);
        self->h = NULL;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp3_decoder_deinit_obj, mp3_decoder_deinit);

static const mp_rom_map_elem_t mp3_decoder_locals_dict_table[] = {
    { MP_ROM_QSTR(MP_QSTR_decode), MP_ROM_PTR(&mp3_decoder_decode_obj) },
    { MP_ROM_QSTR(MP_QSTR_deinit), MP_ROM_PTR(&mp3_decoder_deinit_obj) },
    { MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&mp3_decoder_deinit_obj) },
};
static MP_DEFINE_CONST_DICT(mp3_decoder_locals_dict, mp3_decoder_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(
    mp3_decoder_type,
    MP_QSTR_Decoder,
    MP_TYPE_FLAG_NONE,
    make_new, mp3_decoder_make_new,
    locals_dict, &mp3_decoder_locals_dict
    );


static const mp_rom_map_elem_t mp3_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_mp3) },
    { MP_ROM_QSTR(MP_QSTR_Decoder), MP_ROM_PTR(&mp3_decoder_type) },
    { MP_ROM_QSTR(MP_QSTR_MAX_FRAME_BYTES), MP_ROM_INT(MP3_MAX_FRAME_BYTES) },
};
static MP_DEFINE_CONST_DICT(mp3_module_globals, mp3_module_globals_table);

const mp_obj_module_t mp3_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mp3_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_mp3, mp3_user_cmodule);
