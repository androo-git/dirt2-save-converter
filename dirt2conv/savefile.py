"""Reader/writer for the DiRT 2 per-object save stream (both console and PC).

Xbox 360 (big-endian), header 12 bytes::

    0x00 u32  checksum = sum of BE u32 words of bytes[0x0C:]  (mod 2^32)
    0x04 u32  version  = 0x0000026E
    0x08 u32  length   = file_size - 12
    0x0C ..   chunk stream

PC (little-endian), header 28 bytes::

    0x00 u32  0x00000018              (header size following this word, minus 4)
    0x04 u32  checksum = sum of LE u32 words of bytes[0x1C:]  (mod 2^32)
    0x08 u32  version  = 0x0000026F
    0x0C u32  length   = file_size - 28
    0x10 u32  "marker" (looks like an uninitialised stack pointer, e.g. 0x17A6F0EC)
    0x14 u32  0x7FFFFFFF
    0x18 u32  0x00000000
    0x1C ..   chunk stream

Chunk stream = repeated ``[u32 size][size bytes AES-256-ECB ciphertext]``
(size is 0x400 in every observed file, endian matches the platform).

The cipher is AES-256 in ECB mode with a fixed key, found as a hex string in
dirt2_game.exe at file offset 0xF57DC8 (rijndael-api-fst makeKey() takes the
key as ASCII hex). The "16-byte XOR key" used previously was just
AES_enc(key, 0^16): zero plaintext blocks happened to decode correctly, every
other block did not.

The decrypted plaintext is native-endian serialised game data (360 = BE,
PC = LE), so the payload must be re-serialised per object, not just
re-wrapped.
"""

import struct
from dataclasses import dataclass, field
from typing import List

from .aes import AesEcb

AES_KEY = bytes.fromhex(
    "BF238E52208261B11FB50901E78E45AC4660153565F09295305484E1F05166EC")
_CIPHER = AesEcb(AES_KEY)

CHUNK_SIZE = 0x400

VERSION_360 = 0x0000026E
VERSION_PC = 0x0000026F
MARKER_DEFAULT = 0x17A6F0EC
MARKER_SYSTEMFILE = 0x00000000
SYSTEMFILE_NAME = "systemfile"


class SaveFileError(Exception):
    pass


@dataclass
class SaveFile:
    payload: bytes                       # decrypted plaintext (all chunks concatenated)
    version: int = VERSION_PC
    marker: int = MARKER_DEFAULT
    chunk_sizes: List[int] = field(default_factory=list)


def _sum_words(data: bytes, endian: str) -> int:
    n = len(data) // 4 * 4
    return sum(struct.unpack(f"{endian}{n // 4}I", data[:n])) & 0xFFFFFFFF


def decode_chunks(stream: bytes, endian: str):
    out, sizes, i = [], [], 0
    while i < len(stream):
        if i + 4 > len(stream):
            raise SaveFileError("truncated chunk header")
        n = struct.unpack_from(endian + "I", stream, i)[0]
        i += 4
        body = stream[i:i + n]
        if len(body) != n or n % 16:
            raise SaveFileError(f"bad chunk size {n:#x} at {i - 4:#x}")
        out.append(_CIPHER.decrypt(body))
        sizes.append(n)
        i += n
    return b"".join(out), sizes


def encode_chunks(payload: bytes, endian: str, sizes=None) -> bytes:
    if not sizes:
        if len(payload) % CHUNK_SIZE:
            raise SaveFileError("payload is not a multiple of the chunk size")
        sizes = [CHUNK_SIZE] * (len(payload) // CHUNK_SIZE)
    if sum(sizes) != len(payload):
        raise SaveFileError("chunk sizes do not match payload length")
    out, i = bytearray(), 0
    for n in sizes:
        out += struct.pack(endian + "I", n)
        out += _CIPHER.encrypt(payload[i:i + n])
        i += n
    return bytes(out)


def parse_360(data: bytes) -> SaveFile:
    if len(data) < 0x10:
        raise SaveFileError("file too small for a 360 save stream")
    stored, version, length = struct.unpack_from(">III", data, 0)
    if length != len(data) - 12:
        raise SaveFileError(f"360 length field {length} != {len(data) - 12}")
    calc = _sum_words(data[0x0C:], ">")
    if calc != stored:
        raise SaveFileError(f"360 checksum mismatch: stored {stored:08X} computed {calc:08X}")
    payload, sizes = decode_chunks(data[0x0C:], ">")
    return SaveFile(payload=payload, version=version, marker=0, chunk_sizes=sizes)


def build_360(sf: SaveFile) -> bytes:
    stream = encode_chunks(sf.payload, ">", sf.chunk_sizes)
    out = bytearray(struct.pack(">III", 0, sf.version or VERSION_360, len(stream)))
    out += stream
    struct.pack_into(">I", out, 0, _sum_words(out[0x0C:], ">"))
    return bytes(out)


def parse_pc(data: bytes) -> SaveFile:
    if len(data) < 0x20:
        raise SaveFileError("file too small for a PC save stream")
    _, stored, version, length, marker = struct.unpack_from("<IIIII", data, 0)
    if length != len(data) - 28:
        raise SaveFileError(f"PC length field {length} != {len(data) - 28}")
    calc = _sum_words(data[0x1C:], "<")
    if calc != stored:
        raise SaveFileError(f"PC checksum mismatch: stored {stored:08X} computed {calc:08X}")
    payload, sizes = decode_chunks(data[0x1C:], "<")
    return SaveFile(payload=payload, version=version, marker=marker, chunk_sizes=sizes)


def build_pc(sf: SaveFile) -> bytes:
    stream = encode_chunks(sf.payload, "<", sf.chunk_sizes)
    out = bytearray(struct.pack("<IIIIIII", 0x18, 0, sf.version or VERSION_PC,
                                len(stream), sf.marker, 0x7FFFFFFF, 0))
    out += stream
    struct.pack_into("<I", out, 0x04, _sum_words(out[0x1C:], "<"))
    return bytes(out)


def marker_for(logical_name: str) -> int:
    if logical_name.lower() == SYSTEMFILE_NAME:
        return MARKER_SYSTEMFILE
    return MARKER_DEFAULT
