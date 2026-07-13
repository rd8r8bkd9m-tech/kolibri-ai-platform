"""Strict, dependency-free validation for raster image artifact bytes.

File extensions, provider metadata, and model prose are never treated as
proof that an image exists.  This module accepts only bounded PNG, JPEG, or
WebP bytes with a decodable positive canvas size.
"""

from __future__ import annotations

from dataclasses import dataclass
import zlib


DEFAULT_MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_DIMENSION = 32_768
MAX_IMAGE_PIXELS = 100_000_000


class InvalidImageBytes(ValueError):
    """The supplied bytes are not a supported, bounded raster image."""


@dataclass(frozen=True)
class ImageDetails:
    mime_type: str
    extension: str
    width: int
    height: int


def _validate_dimensions(width: int, height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise InvalidImageBytes("image_dimensions_invalid")
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise InvalidImageBytes("image_dimensions_exceed_limit")
    if width * height > MAX_IMAGE_PIXELS:
        raise InvalidImageBytes("image_pixel_count_exceeds_limit")
    return width, height


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 33 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    dimensions: tuple[int, int] | None = None
    saw_image_data = False
    saw_end = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise InvalidImageBytes("png_chunk_truncated")
        chunk_length = int.from_bytes(data[offset : offset + 4], "big")
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + chunk_length
        if chunk_end > len(data):
            raise InvalidImageBytes("png_chunk_truncated")
        payload = data[offset + 8 : offset + 8 + chunk_length]
        expected_crc = int.from_bytes(data[offset + 8 + chunk_length : chunk_end], "big")
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
            raise InvalidImageBytes("png_chunk_crc_invalid")
        if offset == 8:
            if chunk_type != b"IHDR" or chunk_length != 13:
                raise InvalidImageBytes("png_ihdr_invalid")
            dimensions = _validate_dimensions(
                int.from_bytes(payload[0:4], "big"),
                int.from_bytes(payload[4:8], "big"),
            )
        elif chunk_type == b"IDAT":
            saw_image_data = True
        elif chunk_type == b"IEND":
            if chunk_length != 0 or chunk_end != len(data):
                raise InvalidImageBytes("png_iend_invalid")
            saw_end = True
            break
        offset = chunk_end
    if dimensions is None or not saw_image_data or not saw_end:
        raise InvalidImageBytes("png_structure_incomplete")
    return dimensions


_JPEG_START_OF_FRAME = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        return None
    if not data.endswith(b"\xff\xd9"):
        raise InvalidImageBytes("jpeg_end_marker_missing")

    offset = 2
    while offset < len(data) - 1:
        if data[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1
        if marker in {0x01, *range(0xD0, 0xDA)}:
            continue
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(data):
            raise InvalidImageBytes("jpeg_segment_truncated")
        segment_length = int.from_bytes(data[offset : offset + 2], "big")
        if segment_length < 2 or offset + segment_length > len(data):
            raise InvalidImageBytes("jpeg_segment_invalid")
        if marker in _JPEG_START_OF_FRAME:
            if segment_length < 7:
                raise InvalidImageBytes("jpeg_frame_invalid")
            height = int.from_bytes(data[offset + 3 : offset + 5], "big")
            width = int.from_bytes(data[offset + 5 : offset + 7], "big")
            return _validate_dimensions(width, height)
        if marker == 0xDA:
            break
        offset += segment_length
    raise InvalidImageBytes("jpeg_dimensions_missing")


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 20 or not (
        data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    ):
        return None
    declared_size = int.from_bytes(data[4:8], "little") + 8
    if declared_size != len(data):
        raise InvalidImageBytes("webp_container_size_invalid")
    chunk = data[12:16]
    if chunk == b"VP8X":
        if len(data) < 30:
            raise InvalidImageBytes("webp_vp8x_truncated")
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return _validate_dimensions(width, height)
    if chunk == b"VP8L":
        if len(data) < 25 or data[20] != 0x2F:
            raise InvalidImageBytes("webp_vp8l_invalid")
        packed = int.from_bytes(data[21:25], "little")
        width = (packed & 0x3FFF) + 1
        height = ((packed >> 14) & 0x3FFF) + 1
        return _validate_dimensions(width, height)
    if chunk == b"VP8 ":
        if len(data) < 30 or data[23:26] != b"\x9d\x01\x2a":
            raise InvalidImageBytes("webp_vp8_invalid")
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return _validate_dimensions(width, height)
    raise InvalidImageBytes("webp_chunk_unsupported")


def inspect_image_bytes(
    data: bytes,
    *,
    max_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
) -> ImageDetails:
    """Return verified media details or raise :class:`InvalidImageBytes`."""

    if not data:
        raise InvalidImageBytes("image_bytes_empty")
    if len(data) > max_bytes:
        raise InvalidImageBytes("image_bytes_exceed_limit")

    dimensions = _png_dimensions(data)
    if dimensions:
        return ImageDetails("image/png", ".png", *dimensions)
    dimensions = _jpeg_dimensions(data)
    if dimensions:
        return ImageDetails("image/jpeg", ".jpg", *dimensions)
    dimensions = _webp_dimensions(data)
    if dimensions:
        return ImageDetails("image/webp", ".webp", *dimensions)
    raise InvalidImageBytes("image_format_unsupported")
