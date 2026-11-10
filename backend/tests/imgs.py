"""Tiny real images built in code (headers are all the app reads, but these are valid files)."""
import struct
import zlib


def png(w=4, h=3) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x10\x20\x30" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def jpeg(w=40, h=30, exif_bytes=0) -> bytes:
    app1, left = b"", exif_bytes                      # a segment holds at most 65533 bytes: a big EXIF block is several
    while left > 0:
        n = min(left, 60_000)
        app1 += b"\xff\xe1" + struct.pack(">H", n + 2) + b"E" * n
        left -= n
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + app1 + sof + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x00\xff\xd9"


def webp_lossy(w=64, h=48) -> bytes:
    body = b"\x00\x00\x00" + b"\x9d\x01\x2a" + struct.pack("<HH", w, h) + b"\x00" * 10
    return b"RIFF" + struct.pack("<I", 4 + 8 + len(body)) + b"WEBP" + b"VP8 " + struct.pack("<I", len(body)) + body


def webp_lossless(w=64, h=48) -> bytes:
    bits = (w - 1) | ((h - 1) << 14)
    body = b"\x2f" + struct.pack("<I", bits) + b"\x00" * 6
    return b"RIFF" + struct.pack("<I", 4 + 8 + len(body)) + b"WEBP" + b"VP8L" + struct.pack("<I", len(body)) + body


def webp_extended(w=640, h=480) -> bytes:
    body = b"\x00\x00\x00\x00" + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little") + b"\x00" * 4
    return b"RIFF" + struct.pack("<I", 4 + 8 + len(body)) + b"WEBP" + b"VP8X" + struct.pack("<I", len(body)) + body


def png_header(w, h) -> bytes:
    """Only the signature and the IHDR chunk: all the app reads, without allocating a huge picture."""
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr) & 0xFFFFFFFF)
