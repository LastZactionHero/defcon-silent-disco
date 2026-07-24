# `mp3` — native MP3 decoder module (Helix / picomp3lib)

A MicroPython C user-module that adds real-time MP3 decoding to the badge without
leaving MicroPython. The RP2040's Cortex-M0+ decodes MP3 comfortably in
fixed-point (benchmarks: ~34% of one core at 44.1 kHz stereo, ~3× real-time
headroom — no overclock). Files, framing, and I2S output stay in Python; this
module only turns MP3 bytes into 16-bit PCM.

## Files
- `mp3_decoder.c` — the binding (a `Decoder` type with `.decode()` / `.deinit()`).
- `micropython.cmake` — compiles the binding + the Helix codec.
- `picomp3lib/` — the Helix port (cloned by `tools/build_firmware.sh`; not vendored).

## Hardware-verified gotchas (cost a full debugging session — do not regress)

1. **Helix's static buffers MUST be 4-byte aligned.** `buffers.c` declares the
   decoder state as `char` arrays (alignment 1) and casts them to structs. Our
   linker placed them at odd addresses → any word access hard-faulted the
   Cortex-M0+ (deinit and real decoding froze the board; creation survived only
   because `ClearBuffer` is byte-wise). `tools/build_firmware.sh` patches
   `__attribute__((aligned(4)))` onto them after cloning. picomp3lib's own
   examples work by linker luck only. *(Worth an upstream PR.)*
2. **Never forward-declare the type object.** `MP_DEFINE_CONST_OBJ_TYPE` builds
   a const object whose trailing `slots` flexible array is sized by the
   initializer; a preceding tentative definition can truncate it. Keep this file
   shaped like `examples/usercmodule/cexample/examplemodule.c`.
3. **The decoder is effectively a singleton.** Static buffers mean every
   `Decoder()` shares the same state — don't run two decoders concurrently
   (the player never does).

## Why picomp3lib specifically
Stock Helix / minimp3 / dr_mp3 assume a 64-bit multiply (`SMULL`) that the M0+
(ARMv6-M) does not have. [`ikjordan/picomp3lib`](https://github.com/ikjordan/picomp3lib)
carries the Cortex-M0+ fix; its `assembly.h` gates the `SMULL` path on
`__ARM_ARCH >= 7`, so on the RP2040 it uses the C multiply fallback. Do not swap
in an unpatched decoder.

## API
```python
import mp3
dec = mp3.Decoder()
consumed, produced, samprate, channels = dec.decode(in_mv, out_buf)
#   in_mv    : readable MP3 bytes (a memoryview slice of your input buffer)
#   out_buf  : bytearray >= mp3.MAX_FRAME_BYTES (4608)
#   consumed : bytes consumed from the start of in_mv
#   produced : PCM bytes written (0 => need more input, or a bad frame was skipped)
#   samprate : Hz  (valid when produced > 0)
#   channels : 1 or 2  (valid when produced > 0)
dec.deinit()   # or let GC finalize it
```
Sliding-buffer contract:
- `produced > 0` → frame decoded; advance input by `consumed`.
- `produced == 0, consumed > 0` → junk/false-sync skipped; advance and retry.
- `produced == 0, consumed == 0` → need more data (refill; on EOF, stop).

See `../../wavplayer.py` (`_play_mp3_file`) for the reference streaming loop.

## Build
```sh
cd firmware
tools/build_firmware.sh          # -> firmware-mp3.uf2
```
Requires the ARM toolchain (`arm-none-eabi-gcc`, `cmake`, `make`, `git`, `python3`).

## License note
Helix is under the RealNetworks RPSL/RCSL (see the headers in `picomp3lib/src`).
It's cloned at build time rather than vendored here; keep the license headers if
you redistribute a built firmware.
