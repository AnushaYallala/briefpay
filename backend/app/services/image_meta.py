"""What an uploaded file really is. We never trust a file name or a Content-Type: the bytes must start like a JPEG, PNG or WebP,
and the header must give a sane size. No image library is used: only the few header bytes we need are read, and the pixels are
never decoded here. Anything else (SVG, GIF, HTML pretending to be an image, truncated files) is refused.
"""
import struct
from dataclasses import dataclass

MAX_SIDE = 12_000
MAX_PIXELS = 50_000_000
MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


@dataclass(frozen=True)
class ImageInfo:
    format: str          # jpg | png | webp
    width: int
    height: int

    @property
    def mime(self) -> str:
        return MIME[self.format]


def _sane(fmt: str, w: int, h: int) -> ImageInfo | None:
    if 0 < w <= MAX_SIDE and 0 < h <= MAX_SIDE and w * h <= MAX_PIXELS:
        return ImageInfo(fmt, w, h)
    return None


def _png(b: bytes) -> ImageInfo | None:
    if len(b) < 33 or b[:8] != b"\x89PNG\r\n\x1a\n" or b[12:16] != b"IHDR":
        return None
    w, h = struct.unpack(">II", b[16:24])
    return _sane("png", w, h)


def _jpeg(b: bytes) -> ImageInfo | None:
    if len(b) < 4 or b[:2] != b"\xff\xd8":
        return None
    i, n = 2, len(b)
    while i + 4 <= n:
        if b[i] != 0xFF:
            return None
        while i < n and b[i] == 0xFF:      # fill bytes
            i += 1
        if i >= n:
            return None
        marker = b[i]
        i += 1
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:   # markers without a length
            continue
        if marker == 0xD9 or i + 2 > n:
            return None
        (length,) = struct.unpack(">H", b[i:i + 2])
        if length < 2:
            return None
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):    # start of frame
            if i + 7 > n:
                return None
            h, w = struct.unpack(">HH", b[i + 3:i + 7])
            return _sane("jpg", w, h)
        i += length
    return None


def _webp(b: bytes) -> ImageInfo | None:
    if len(b) < 30 or b[:4] != b"RIFF" or b[8:12] != b"WEBP":
        return None
    kind = b[12:16]
    if kind == b"VP8 ":
        if b[23:26] != b"\x9d\x01\x2a":
            return None
        w, h = struct.unpack("<HH", b[26:30])
        return _sane("webp", w & 0x3FFF, h & 0x3FFF)
    if kind == b"VP8L":
        if b[20] != 0x2F:
            return None
        bits = struct.unpack("<I", b[21:25])[0]
        return _sane("webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    if kind == b"VP8X":
        w = int.from_bytes(b[24:27], "little") + 1
        h = int.from_bytes(b[27:30], "little") + 1
        return _sane("webp", w, h)
    return None


def sniff(data: bytes) -> ImageInfo | None:
    """The real format and size, or None if this is not an acceptable image."""
    if not isinstance(data, (bytes, bytearray)):
        return None
    data = bytes(data[:65536]) if len(data) > 65536 and data[:2] != b"\xff\xd8" else bytes(data)
    return _png(data) or _jpeg(data) or _webp(data)
