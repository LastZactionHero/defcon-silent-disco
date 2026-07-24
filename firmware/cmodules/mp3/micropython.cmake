# MicroPython USER_C_MODULE: native MP3 decoder (picomp3lib / Helix, fixed-point).
#
# Expects the picomp3lib sources at ./picomp3lib/ (tools/build_firmware.sh clones
# them there).  The Helix codec is pure fixed-point C and needs no Pico SDK; on
# the RP2040 (ARMv6-M) it uses the C multiply fallback in assembly.h (the SMULL
# path is gated on __ARM_ARCH >= 7), so it is Cortex-M0+ safe.

add_library(usermod_mp3 INTERFACE)

set(PICOMP3_SRC ${CMAKE_CURRENT_LIST_DIR}/picomp3lib/src)

target_sources(usermod_mp3 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/mp3_decoder.c
    ${PICOMP3_SRC}/bitstream.c
    ${PICOMP3_SRC}/buffers.c
    ${PICOMP3_SRC}/dct32.c
    ${PICOMP3_SRC}/dequant.c
    ${PICOMP3_SRC}/dqchan.c
    ${PICOMP3_SRC}/huffman.c
    ${PICOMP3_SRC}/hufftabs.c
    ${PICOMP3_SRC}/imdct.c
    ${PICOMP3_SRC}/mp3dec.c
    ${PICOMP3_SRC}/mp3tabs.c
    ${PICOMP3_SRC}/polyphase.c
    ${PICOMP3_SRC}/scalfact.c
    ${PICOMP3_SRC}/stproc.c
    ${PICOMP3_SRC}/subband.c
    ${PICOMP3_SRC}/trigtabs.c
)

target_include_directories(usermod_mp3 INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
    ${PICOMP3_SRC}
)

# Helix has benign warnings; don't let -Werror (if enabled) fail the build.
target_compile_options(usermod_mp3 INTERFACE -Wno-error)

target_link_libraries(usermod INTERFACE usermod_mp3)
