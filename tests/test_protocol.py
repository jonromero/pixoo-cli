"""Tests for pixoo_cli.protocol: the real Divoom serial/BLE packet format.

Byte layout is cross-checked against three independent reverse-engineering
sources for this exact device (see protocol.py's module docstring), so
these tests assert the documented wire format rather than reimplementing
protocol.py's internals.
"""

import pytest

from pixoo_cli.protocol import (
    CMD_DRAW_ANIM,
    CMD_DRAW_PIC,
    build_packet,
    encode_static_frame,
    encode_animation_frames,
)


def _checksum(data: bytes) -> int:
    """Reference checksum: sum of bytes truncated to uint16."""
    return sum(data) & 0xFFFF


def _decode_image_frame(frame_bytes: bytes, num_pixels: int):
    """Independent decoder for the 0xAA image-frame format.

    Returns (speed_ms, reset, pixels, frame_size) by inverting the
    documented encoding: palette lookup + LSB-first bit-packed indices.
    """
    assert frame_bytes[0] == 0xAA
    frame_size = frame_bytes[1] | (frame_bytes[2] << 8)
    speed_ms = frame_bytes[3] | (frame_bytes[4] << 8)
    reset = frame_bytes[5]
    nb_colors_byte = frame_bytes[6]
    nb_colors = 256 if nb_colors_byte == 0 else nb_colors_byte

    palette_start = 7
    palette_end = palette_start + nb_colors * 3
    palette_bytes = frame_bytes[palette_start:palette_end]
    colors = [
        tuple(palette_bytes[i : i + 3]) for i in range(0, len(palette_bytes), 3)
    ]

    bitwidth = max(1, (nb_colors - 1).bit_length())
    pixel_data = frame_bytes[palette_end:frame_size]

    bit_buffer = 0
    bits_in_buffer = 0
    indices = []
    for byte in pixel_data:
        bit_buffer |= byte << bits_in_buffer
        bits_in_buffer += 8
        while bits_in_buffer >= bitwidth and len(indices) < num_pixels:
            indices.append(bit_buffer & ((1 << bitwidth) - 1))
            bit_buffer >>= bitwidth
            bits_in_buffer -= bitwidth

    pixels = [colors[i] for i in indices]
    return speed_ms, reset, pixels, frame_size


def _make_pixels(size=16, r=0xFF, g=0x00, b=0x00):
    """Uniform pixel list of a single color."""
    return [(r, g, b)] * (size * size)


def _make_checkerboard(size=4):
    """Two-color checkerboard pattern."""
    pixels = []
    for y in range(size):
        for x in range(size):
            pixels.append((255, 0, 0) if (x + y) % 2 == 0 else (0, 0, 255))
    return pixels


def _make_rainbow(size=16):
    """A pixel grid using as many distinct colors as there are pixels."""
    return [(i & 0xFF, (i * 7) & 0xFF, (i * 13) & 0xFF) for i in range(size * size)]


# ---------------------------------------------------------------------------
# build_packet
# ---------------------------------------------------------------------------


class TestBuildPacket:
    """build_packet wraps cmd+args in the FE EF AA 55 BLE command envelope."""

    def test_header_bytes(self):
        pkt = build_packet(0xAB, b"\x01\x02\x03")
        assert pkt[0:4] == bytes([0xFE, 0xEF, 0xAA, 0x55])

    def test_packet_type_byte(self):
        pkt = build_packet(0xAB, b"\x01\x02\x03")
        assert pkt[6] == 0x01

    def test_seq_field(self):
        pkt = build_packet(0xAB, b"", seq=0x11223344)
        assert pkt[7:11] == bytes([0x44, 0x33, 0x22, 0x11])

    def test_seq_defaults_to_zero(self):
        pkt = build_packet(0xAB, b"")
        assert pkt[7:11] == bytes(4)

    def test_cmd_byte_position(self):
        pkt = build_packet(0xAB, b"\x01\x02\x03")
        assert pkt[11] == 0xAB

    def test_length_field(self):
        args = b"\x11\x22\x33\x44"
        pkt = build_packet(0x01, args)
        length = pkt[4] | (pkt[5] << 8)
        # seq(4) + cmd(1) + args + 3
        assert length == 4 + 1 + len(args) + 3

    def test_args_follow_cmd(self):
        args = b"\xDE\xAD\xBE\xEF"
        pkt = build_packet(0x01, args)
        assert pkt[12 : 12 + len(args)] == args

    def test_checksum_is_correct(self):
        args = b"\x01\x02\x03"
        pkt = build_packet(0x05, args, seq=7)
        expected = _checksum(pkt[4:-2])
        stored = pkt[-2] | (pkt[-1] << 8)
        assert stored == expected

    def test_known_good_brightness_packet(self):
        # Captured from a packet the real device executed (brightness 0).
        pkt = build_packet(0x74, b"\x00", seq=3)
        assert pkt == bytes.fromhex("feefaa550900010300000074008100")

    def test_total_packet_length(self):
        args = b"\x00" * 10
        pkt = build_packet(0x01, args)
        # header(4) + length(2) + type(1) + seq(4) + cmd(1) + args(10) + checksum(2)
        assert len(pkt) == 24

    def test_empty_args_allowed(self):
        pkt = build_packet(0x46, b"")
        assert len(pkt) == 14

    def test_invalid_cmd_negative(self):
        with pytest.raises(ValueError, match="cmd must be a uint8"):
            build_packet(-1, b"\x00")

    def test_invalid_cmd_too_large(self):
        with pytest.raises(ValueError, match="cmd must be a uint8"):
            build_packet(256, b"\x00")

    def test_invalid_cmd_string(self):
        with pytest.raises(ValueError, match="cmd must be a uint8"):
            build_packet("hello", b"\x00")

    def test_invalid_seq(self):
        with pytest.raises(ValueError, match="seq must be a uint32"):
            build_packet(0x01, b"", seq=-1)
        with pytest.raises(ValueError, match="seq must be a uint32"):
            build_packet(0x01, b"", seq=1 << 32)

    def test_deterministic(self):
        args = b"\x01\x02\x03"
        assert build_packet(0x01, args) == build_packet(0x01, args)


# ---------------------------------------------------------------------------
# encode_static_frame
# ---------------------------------------------------------------------------


class TestEncodeStaticFrame:
    """encode_static_frame builds a complete CMD_DRAW_PIC packet."""

    def test_returns_bytes(self):
        assert isinstance(encode_static_frame(_make_pixels(16), 16), bytes)

    def test_outer_framing(self):
        pkt = encode_static_frame(_make_pixels(16), 16)
        assert pkt[0:4] == bytes([0xFE, 0xEF, 0xAA, 0x55])
        assert pkt[11] == CMD_DRAW_PIC

    def test_draw_pic_prefix(self):
        pkt = encode_static_frame(_make_pixels(4), 4)
        # args = [00 0A 0A 04] + frame; args start right after the cmd byte
        assert pkt[12:16] == bytes([0x00, 0x0A, 0x0A, 0x04])
        assert pkt[16] == 0xAA  # start of the image frame

    def test_roundtrip_single_color(self):
        pixels = _make_pixels(4, r=0x11, g=0x22, b=0x33)
        pkt = encode_static_frame(pixels, 4)
        frame = pkt[16:-2]  # strip envelope/prefix and checksum
        speed_ms, reset, decoded, _ = _decode_image_frame(frame, 16)
        assert speed_ms == 0
        assert reset == 0x00
        assert decoded == pixels

    def test_roundtrip_checkerboard(self):
        pixels = _make_checkerboard(4)
        pkt = encode_static_frame(pixels, 4)
        frame = pkt[16:-2]
        _, _, decoded, _ = _decode_image_frame(frame, 16)
        assert decoded == pixels

    def test_roundtrip_many_colors(self):
        pixels = _make_rainbow(16)
        pkt = encode_static_frame(pixels, 16)
        frame = pkt[16:-2]
        _, _, decoded, _ = _decode_image_frame(frame, 256)
        assert decoded == pixels

    def test_size_mismatch_raises(self):
        with pytest.raises(ValueError, match="pixels length"):
            encode_static_frame([(0, 0, 0)] * 10, 16)

    def test_invalid_size_raises(self):
        with pytest.raises(ValueError, match="must be a positive int"):
            encode_static_frame([(0, 0, 0)] * 256, 0)


# ---------------------------------------------------------------------------
# encode_animation_frames
# ---------------------------------------------------------------------------


class TestEncodeAnimationFrames:
    """encode_animation_frames packs frames into chunked CMD_DRAW_ANIM packets."""

    def test_empty_frames_returns_empty_list(self):
        assert encode_animation_frames([], 4) == []

    def test_single_small_frame_one_packet(self):
        frames = [(_make_pixels(4, r=255), 1000)]
        packets = encode_animation_frames(frames, 4)
        assert len(packets) == 1
        pkt = packets[0]
        assert pkt[0:4] == bytes([0xFE, 0xEF, 0xAA, 0x55])
        assert pkt[11] == CMD_DRAW_ANIM

    def test_chunk_header_matches_single_frame(self):
        frames = [(_make_pixels(4, r=255), 1000)]
        packets = encode_animation_frames(frames, 4)
        args = packets[0][12:-2]
        total_lo, total_hi, chunk_index = args[0], args[1], args[2]
        total_size = total_lo | (total_hi << 8)
        assert chunk_index == 0
        assert total_size == len(args) - 3  # whole blob fit in one chunk

    def test_multiple_frames_combined_into_blob(self):
        frames = [
            (_make_pixels(4, r=255), 100),
            (_make_pixels(4, g=255), 200),
            (_make_pixels(4, b=255), 300),
        ]
        packets = encode_animation_frames(frames, 4)
        # Three small 4x4 frames easily fit under the 200-byte chunk limit.
        assert len(packets) == 1
        args = packets[0][12:-2]
        total_size = args[0] | (args[1] << 8)
        assert total_size == len(args) - 3

    def test_large_animation_splits_into_multiple_chunks(self):
        # Many distinct colors per frame maximizes frame size (big palette),
        # and enough frames pushes the combined blob over the 200-byte
        # per-chunk limit.
        frames = [(_make_rainbow(16), 100) for _ in range(3)]
        packets = encode_animation_frames(frames, 16)
        assert len(packets) > 1

        total_sizes = set()
        reassembled = bytearray()
        for i, pkt in enumerate(packets):
            assert pkt[0:4] == bytes([0xFE, 0xEF, 0xAA, 0x55])
            assert pkt[11] == CMD_DRAW_ANIM
            assert int.from_bytes(pkt[7:11], "little") == i  # seq
            args = pkt[12:-2]
            total_lo, total_hi, chunk_index = args[0], args[1], args[2]
            total_sizes.add(total_lo | (total_hi << 8))
            assert chunk_index == i
            reassembled += args[3:]

        # All chunks of one animation report the same total blob size,
        # and the chunks concatenate back into exactly that many bytes.
        assert len(total_sizes) == 1
        assert len(reassembled) == total_sizes.pop()

    def test_different_delays_change_packet_bytes(self):
        frame = _make_pixels(4, r=128)
        fast = encode_animation_frames([(frame, 10)], 4)
        slow = encode_animation_frames([(frame, 2000)], 4)
        assert fast != slow
        assert len(fast) == len(slow)

    def test_invalid_size_raises(self):
        with pytest.raises(ValueError, match="must be a positive int"):
            encode_animation_frames([([(0, 0, 0)] * 256, 100)], 0)

    def test_frame_mismatched_length_raises(self):
        with pytest.raises(ValueError, match="frame 0: pixels length"):
            encode_animation_frames([([(0, 0, 0)] * 10, 100)], 16)

    def test_mismatched_frame_in_list_raises(self):
        good = [(0, 0, 0)] * 256
        bad = [(0, 0, 0)] * 100
        with pytest.raises(ValueError, match="frame 1: pixels length"):
            encode_animation_frames([(good, 100), (bad, 100)], 16)

    def test_negative_delay_raises(self):
        with pytest.raises(ValueError, match="delay_ms"):
            encode_animation_frames([([(0, 0, 0)] * 256, -1)], 16)

    def test_delay_too_large_raises(self):
        with pytest.raises(ValueError, match="delay_ms"):
            encode_animation_frames([([(0, 0, 0)] * 256, 65536)], 16)

    def test_valid_boundary_delays(self):
        frame = [(0, 0, 0)] * 256
        encode_animation_frames([(frame, 0)], 16)
        encode_animation_frames([(frame, 65535)], 16)
