"""Tests for pixoo_cli.text: render_text_to_pixels, render_scrolling_frames."""

import pytest

import pixoo_cli.text as text_module


class TestRenderTextToPixels:
    """Tests for render_text_to_pixels."""

    def test_returns_list_of_tuples(self):
        """Output is a list of (r, g, b) tuples."""
        pixels = text_module.render_text_to_pixels("A", size=16)
        assert isinstance(pixels, list)
        assert all(isinstance(p, tuple) for p in pixels)

    def test_output_length_equals_size_squared(self):
        """Output length equals size * size."""
        for size in [8, 16, 32]:
            pixels = text_module.render_text_to_pixels("Hi", size=size)
            assert len(pixels) == size * size

    def test_at_least_one_pixel_matches_color(self):
        """At least one pixel matches the foreground color."""
        pixels = text_module.render_text_to_pixels("X", size=16, color=(255, 0, 0))
        assert (255, 0, 0) in pixels

    def test_non_empty_text_contains_foreground(self):
        """Non-empty text renders at least one foreground pixel."""
        for t in ["A", "Hi", "Hello", "123"]:
            pixels = text_module.render_text_to_pixels(t, size=16)
            assert (255, 255, 255) in pixels, f"No white pixel for text={t!r}"

    def test_empty_text_is_all_background(self):
        """Empty text renders only background colour."""
        pixels = text_module.render_text_to_pixels("", size=16)
        assert all(p == (0, 0, 0) for p in pixels)

    def test_custom_background_color(self):
        """Custom background colour is used."""
        pixels = text_module.render_text_to_pixels(
            "", size=16, bg_color=(100, 150, 200)
        )
        assert all(p == (100, 150, 200) for p in pixels)

    def test_size_validation(self):
        """Invalid size raises ValueError."""
        with pytest.raises(ValueError, match="size must be a positive integer"):
            text_module.render_text_to_pixels("A", size=0)
        with pytest.raises(ValueError, match="size must be a positive integer"):
            text_module.render_text_to_pixels("A", size=-1)
        with pytest.raises(ValueError, match="size must be a positive integer"):
            text_module.render_text_to_pixels("A", size=16.5)

    def test_tuple_shape_is_rgb(self):
        """Each tuple has exactly 3 uint8 values."""
        pixels = text_module.render_text_to_pixels("A", size=16)
        for p in pixels:
            assert len(p) == 3
            assert all(0 <= v <= 255 for v in p)

    def test_larger_grid_works(self):
        """Works on larger grid sizes."""
        pixels = text_module.render_text_to_pixels("Hi", size=32)
        assert len(pixels) == 32 * 32
        assert (255, 255, 255) in pixels

    def test_custom_color_values(self):
        """Custom (r, g, b) values are respected."""
        pixels = text_module.render_text_to_pixels(
            "A", size=16, color=(255, 128, 64)
        )
        assert (255, 128, 64) in pixels


class TestRenderScrollingFrames:
    """Tests for render_scrolling_frames."""

    def test_returns_list_of_tuples(self):
        """Output is a list of (pixels, delay) tuples."""
        frames = text_module.render_scrolling_frames("A", size=16)
        assert isinstance(frames, list)

    def test_frames_have_two_elements(self):
        """Each frame is (pixel_list, int_delay)."""
        frames = text_module.render_scrolling_frames("A", size=16)
        for frame in frames:
            pixels, delay = frame
            assert isinstance(pixels, list)
            assert isinstance(delay, int)

    def test_pixel_length_equals_size_squared(self):
        """Each frame's pixel list length equals size * size."""
        frames = text_module.render_scrolling_frames("A", size=16)
        for pixels, _ in frames:
            assert len(pixels) == 16 * 16

    def test_delay_is_positive(self):
        """Delay per frame is a positive integer."""
        frames = text_module.render_scrolling_frames("A", size=16)
        for _, delay in frames:
            assert delay > 0

    def test_multiple_frames_for_long_text(self):
        """Longer text produces more frames than short text."""
        short_frames = text_module.render_scrolling_frames("A", size=16)
        long_frames = text_module.render_scrolling_frames("Hello World", size=16)
        assert len(long_frames) > len(short_frames)

    def test_size_validation(self):
        """Invalid size raises ValueError."""
        with pytest.raises(ValueError, match="size must be a positive integer"):
            text_module.render_scrolling_frames("A", size=0)
