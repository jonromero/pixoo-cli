"""Pixel frames -> Divoom Pixoo (16x16, Bluetooth-only) packet bytes.

The commands and image format are Divoom's own serial protocol, as
recovered by community reverse-engineering (https://github.com/
steevithak/Pixoo, https://github.com/andreas-mausch/divoom-ditoo-pro-
controller, https://github.com/RomRider/node-divoom-timebox-evo).

The outer packet is NOT the one those projects use. Over BLE this device
(Anyka AK1052D, model 1052D) silently ignores the classic ``01 ... 02``
serial frame and only executes commands wrapped in this envelope, which
was found by probing real hardware (see docs/how-we-cracked-it.md)::

    [FE EF AA 55] [LENGTH (2 bytes, LE)] [0x01] [SEQ (4 bytes, LE)]
    [CMD] [ARGS] [CHECKSUM (2 bytes, LE)]

Where:
    LENGTH   = len(SEQ + CMD + ARGS) + 3
    CHECKSUM = sum of (LENGTH bytes + 0x01 + SEQ + CMD + ARGS), truncated
               to uint16
    SEQ      = packet sequence number, echoed back by the device in its
               transport ack (``04 33 55 <SEQ>``)

Static image (``CMD_DRAW_PIC`` = 0x44), ARGS = ``00 0A 0A 04`` + an image
frame. Animation (``CMD_DRAW_ANIM`` = 0x49) concatenates one image frame
per animation frame, then splits that blob into <=200-byte chunks, each
sent as its own outer packet with a ``[total_len_lo, total_len_hi,
chunk_index]`` header.

Image frame format (used by both still images and each animation frame)::

    [0xAA] [FRAME_SIZE (2 bytes, LE)] [SPEED_MS (2 bytes, LE)] [RESET (1 byte)]
    [NUM_COLORS (1 byte, 0 means 256)] [PALETTE: 3 bytes RGB per color]
    [PIXEL_DATA: palette-index per pixel, packed LSB-first at
     ceil(log2(num_colors)) bits per pixel]

    FRAME_SIZE = 7 + len(PALETTE) + len(PIXEL_DATA) (counts the whole frame,
    including its own 0xAA/FRAME_SIZE bytes)
"""

__all__ = [
    "build_packet",
    "encode_static_frame",
    "encode_animation_frames",
]

CMD_DRAW_PIC = 0x44
CMD_DRAW_ANIM = 0x49

_HEADER = bytes([0xFE, 0xEF, 0xAA, 0x55])
_PACKET_TYPE_COMMAND = 0x01

_DRAW_PIC_PREFIX = bytes([0x00, 0x0A, 0x0A, 0x04])
_ANIMATION_CHUNK_SIZE = 200


def _checksum(data: bytes) -> int:
    """Sum of *data* truncated to an unsigned 16-bit value."""
    return sum(data) & 0xFFFF


def build_packet(cmd: int, args: bytes = b"", seq: int = 0) -> bytes:
    """Wrap *cmd* and *args* in the BLE command envelope.

    Args:
        cmd: Command byte.
        args: Command-specific argument bytes (may be empty).
        seq: Packet sequence number (uint32), echoed in the device's ack.

    Returns:
        The complete packet: header, little-endian length, packet type,
        little-endian sequence number, cmd, args, little-endian checksum.

    Raises:
        ValueError: If ``cmd`` is not a valid uint8 or ``seq`` is not a
            valid uint32.
    """
    if not isinstance(cmd, int) or isinstance(cmd, bool) or not (0 <= cmd <= 0xFF):
        raise ValueError(f"cmd must be a uint8, got {cmd!r}")
    if not isinstance(seq, int) or isinstance(seq, bool) or not (0 <= seq <= 0xFFFFFFFF):
        raise ValueError(f"seq must be a uint32, got {seq!r}")

    payload = seq.to_bytes(4, "little") + bytes([cmd]) + args
    length = len(payload) + 3
    body = bytes([length & 0xFF, (length >> 8) & 0xFF, _PACKET_TYPE_COMMAND]) + payload
    checksum = _checksum(body)

    return _HEADER + body + bytes([checksum & 0xFF, (checksum >> 8) & 0xFF])


def _validate_size(size: int) -> None:
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ValueError(f"size must be a positive int, got {size!r}")


def _validate_frame(frame: list[tuple[int, int, int]], size: int, label: str) -> None:
    expected = size * size
    if len(frame) != expected:
        raise ValueError(
            f"{label}: pixels length {len(frame)} != expected {expected} for size {size}"
        )


def _build_palette(
    pixels: list[tuple[int, int, int]],
) -> tuple[list[tuple[int, int, int]], list[int]]:
    """Split *pixels* into a deduplicated color palette and index list."""
    colors: list[tuple[int, int, int]] = []
    index_of: dict[tuple[int, int, int], int] = {}
    indices: list[int] = []
    for pixel in pixels:
        idx = index_of.get(pixel)
        if idx is None:
            idx = len(colors)
            index_of[pixel] = idx
            colors.append(pixel)
        indices.append(idx)
    return colors, indices


def _pack_pixel_indices(indices: list[int], bitwidth: int) -> bytes:
    """Bit-pack palette *indices* LSB-first at *bitwidth* bits each."""
    bit_buffer = 0
    bits_in_buffer = 0
    out = bytearray()
    for idx in indices:
        bit_buffer |= idx << bits_in_buffer
        bits_in_buffer += bitwidth
        while bits_in_buffer >= 8:
            out.append(bit_buffer & 0xFF)
            bit_buffer >>= 8
            bits_in_buffer -= 8
    if bits_in_buffer > 0:
        out.append(bit_buffer & 0xFF)
    return bytes(out)


def _encode_image_frame(
    pixels: list[tuple[int, int, int]], speed_ms: int = 0, reset: int = 0x00
) -> bytes:
    """Encode one 0xAA-prefixed image/animation frame (palette + pixel data)."""
    colors, indices = _build_palette(pixels)
    nb_colors = len(colors)
    bitwidth = max(1, (nb_colors - 1).bit_length())

    palette_bytes = b"".join(bytes(color) for color in colors)
    pixel_bytes = _pack_pixel_indices(indices, bitwidth)

    frame_size = 7 + len(palette_bytes) + len(pixel_bytes)
    nb_colors_byte = 0 if nb_colors >= 256 else nb_colors

    header = bytes(
        [
            0xAA,
            frame_size & 0xFF,
            (frame_size >> 8) & 0xFF,
            speed_ms & 0xFF,
            (speed_ms >> 8) & 0xFF,
            reset & 0xFF,
            nb_colors_byte,
        ]
    )
    return header + palette_bytes + pixel_bytes


def encode_static_frame(pixels: list[tuple[int, int, int]], size: int) -> bytes:
    """Encode a single static image as a complete ``CMD_DRAW_PIC`` packet.

    Args:
        pixels: A flat list of (r, g, b) tuples, row-major, length size*size.
        size: Grid dimension (e.g. 16 for a 16x16 grid).

    Returns:
        A ``bytes`` object ready to be written to the BLE characteristic.

    Raises:
        ValueError: If pixels length != size*size or size is invalid.
    """
    _validate_size(size)
    _validate_frame(pixels, size, "pixels")

    frame = _encode_image_frame(pixels, speed_ms=0, reset=0x00)
    return build_packet(CMD_DRAW_PIC, _DRAW_PIC_PREFIX + frame)


def encode_animation_frames(
    frames: list[tuple[list[tuple[int, int, int]], int]], size: int
) -> list[bytes]:
    """Encode an animation (scrolling text, GIF, multi-frame) as packets.

    All frames are concatenated into a single image-frame blob, then split
    into <=200-byte chunks (the device's receive-buffer limit); each chunk
    is sent as its own ``CMD_DRAW_ANIM`` packet carrying the overall blob
    length and the chunk's index, so the device can reassemble it.

    Args:
        frames: A list of ``(pixels, delay_ms)`` tuples. ``pixels`` is a
            flat list of (r, g, b) tuples, row-major, length size*size.
            ``delay_ms`` is this frame's display time in milliseconds.
        size: Grid dimension (e.g. 16 for a 16x16 grid).

    Returns:
        A list of ``bytes`` packets to be written, in order, to the BLE
        characteristic.

    Raises:
        ValueError: If size is invalid, any frame has the wrong pixel
            count, or any delay is out of range.
    """
    _validate_size(size)
    if not frames:
        return []

    blob = bytearray()
    for i, (pixels, delay_ms) in enumerate(frames):
        _validate_frame(pixels, size, f"frame {i}")
        if not isinstance(delay_ms, int) or isinstance(delay_ms, bool) or not (
            0 <= delay_ms <= 0xFFFF
        ):
            raise ValueError(f"frame {i}: delay_ms must be 0..65535, got {delay_ms!r}")
        blob += _encode_image_frame(pixels, speed_ms=delay_ms, reset=0x00)

    total_size = len(blob)
    packets: list[bytes] = []
    for chunk_index, offset in enumerate(range(0, total_size, _ANIMATION_CHUNK_SIZE)):
        chunk = bytes(blob[offset : offset + _ANIMATION_CHUNK_SIZE])
        header = bytes([total_size & 0xFF, (total_size >> 8) & 0xFF, chunk_index & 0xFF])
        packets.append(build_packet(CMD_DRAW_ANIM, header + chunk, seq=chunk_index))

    return packets
