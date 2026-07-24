"""
Minimal robust RIFF/WAVE parser for PCM 16-bit files (MicroPython v1.28, rp2).

Handles: unknown chunks (LIST/fact/JUNK), odd-size chunk padding, data chunk not
at byte 44, streaming size sentinels (0/0xFFFFFFFF), oversized data sizes, and
WAVE_FORMAT_EXTENSIBLE (0xFFFE) fmt of size 40.  Returns a dict; raises WavError
on non-PCM / non-16-bit / malformed input.
"""

import struct


class WavError(Exception):
    pass


def parse_wav(path):
    with open(path, "rb") as f:
        riff = f.read(12)
        if len(riff) < 12:
            raise WavError("file too short for RIFF header")
        if riff[0:4] != b"RIFF":
            raise WavError("not a RIFF file")
        if riff[8:12] != b"WAVE":
            raise WavError("not a WAVE file")
        # riff[4:8] (overall size) intentionally ignored (streaming writers lie).

        f.seek(0, 2)               # whence 2 = end (literal; os.SEEK_* not on rp2)
        file_size = f.tell()
        f.seek(12, 0)              # first sub-chunk

        fmt = None
        data_offset = None
        data_size = None

        while True:
            hdr = f.read(8)
            if len(hdr) < 8:       # clean EOF at a chunk boundary
                break
            chunk_id = hdr[0:4]
            (chunk_size,) = struct.unpack("<I", hdr[4:8])
            pad = chunk_size & 1   # RIFF chunks are word-aligned

            if chunk_id == b"fmt ":
                body = f.read(chunk_size)
                if len(body) < 16:
                    raise WavError("fmt chunk too short")
                (audio_format, num_channels, sample_rate,
                 byte_rate, block_align, bits_per_sample) = struct.unpack("<HHIIHH", body[0:16])
                if audio_format == 0xFFFE:      # WAVE_FORMAT_EXTENSIBLE
                    if len(body) >= 26:
                        (audio_format,) = struct.unpack("<H", body[24:26])
                    else:
                        raise WavError("EXTENSIBLE fmt missing SubFormat")
                if audio_format != 1:
                    raise WavError("unsupported audioFormat %d (need PCM=1)" % audio_format)
                if bits_per_sample != 16:
                    raise WavError("unsupported bitsPerSample %d (need 16)" % bits_per_sample)
                fmt = {
                    "audio_format": audio_format,
                    "num_channels": num_channels,
                    "sample_rate": sample_rate,
                    "byte_rate": byte_rate,
                    "block_align": block_align,
                    "bits_per_sample": bits_per_sample,
                }
                if pad:
                    f.seek(pad, 1)

            elif chunk_id == b"data":
                data_offset = f.tell()
                remaining = file_size - data_offset
                if chunk_size == 0xFFFFFFFF or chunk_size > remaining:
                    data_size = remaining
                else:
                    data_size = chunk_size
                if fmt is not None:
                    break
                # rare: data before fmt -> skip real (padded) span, keep looking
                f.seek(data_offset + chunk_size + pad, 0)

            else:
                f.seek(chunk_size + pad, 1)   # skip unknown chunk (+ pad byte)

        if fmt is None:
            raise WavError("no 'fmt ' chunk found")
        if data_offset is None:
            raise WavError("no 'data' chunk found")

        block = fmt["block_align"] or (fmt["num_channels"] * 2)
        fmt["data_offset"] = data_offset
        fmt["data_size"] = data_size
        fmt["block_align"] = block
        fmt["num_frames"] = data_size // block
        return fmt
