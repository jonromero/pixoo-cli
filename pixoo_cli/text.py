"""Text rendering into static/scrolling pixel frames (Pillow only, no BLE).

Implemented in a later task.
"""

from PIL import Image, ImageDraw, ImageFont


__all__ = [
    "render_text_to_pixels",
    "render_scrolling_frames",
]


def _validate_size(size):
    """Validate that ``size`` is a positive integer.

    Raises:
        ValueError: If ``size`` is not a positive integer.
    """
    if not isinstance(size, int) or size <= 0:
        raise ValueError(f"size must be a positive integer, got {size!r}")


def _threshold_to_binary(img, color, bg_color):
    """Convert a rendered image to pure binary pixels.

    Any pixel that is closer to ``color`` than to ``bg_color`` becomes
    ``color``, otherwise it becomes ``bg_color``.  This removes
    anti-aliasing artifacts from the default bitmap font so that the
    resulting pixel list contains exact colour matches.
    """
    result = []
    r_c, g_c, b_c = color
    r_b, g_b, b_b = bg_color
    for py in range(img.height):
        for px in range(img.width):
            r, g, b = img.getpixel((px, py))
            dist_to_color = (r - r_c) ** 2 + (g - g_c) ** 2 + (b - b_c) ** 2
            dist_to_bg = (r - r_b) ** 2 + (g - g_b) ** 2 + (b - b_b) ** 2
            if dist_to_color < dist_to_bg:
                result.append(color)
            else:
                result.append(bg_color)
    return result


def render_text_to_pixels(text, size, color=(255, 255, 255), bg_color=(0, 0, 0)):
    """Render text onto a square pixel grid.

    Args:
        text: String to render.  Empty text fills the grid with
            ``bg_color``.
        size: Grid edge length in pixels (e.g. 16).
        color: Foreground ``(r, g, b)`` tuple for the text.
        bg_color: Background ``(r, g, b)`` tuple (default black).

    Returns:
        A flat ``list`` of ``(r, g, b)`` tuples, row-major, of length
        ``size * size``.

    Raises:
        ValueError: If ``size`` is not a positive integer.
    """
    _validate_size(size)

    # Render directly at the target grid size.
    # The default bitmap font is a 5x8 pixel font that renders
    # visibly on a 16x16 grid without any scaling.
    img = Image.new("RGB", (size, size), bg_color)
    if text:
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        # Position text at (0, 0) so it fits within the grid.
        draw.text((0, 0), text, font=font, fill=color)

    # Threshold anti-aliased pixels to pure binary (on/off).
    return _threshold_to_binary(img, color, bg_color)


def render_scrolling_frames(text, size, color=(255, 255, 255), bg_color=(0, 0, 0),
                            frame_px=1, delay_ms=100):
    """Render scrolling text frames for a Pixoo display.

    The text scrolls horizontally across the grid, producing a series of
    frames that can be sent sequentially to create a scrolling effect.

    Args:
        text: String to scroll.
        size: Grid edge length in pixels (e.g. 16).
        color: Foreground ``(r, g, b)`` tuple for the text.
        bg_color: Background ``(r, g, b)`` tuple (default black).
        frame_px: Pixels to advance per frame (default 1).
        delay_ms: Milliseconds between frames (default 100).

    Returns:
        A ``list`` of ``(pixels, delay_ms)`` tuples, one per frame.
        ``pixels`` is a flat ``list`` of ``(r, g, b)`` tuples (length
        ``size * size``).

    Raises:
        ValueError: If ``size`` is not a positive integer.
    """
    _validate_size(size)

    if not text:
        # Single frame of pure background.
        return [(list(Image.new("RGB", (size, size), bg_color).getdata()), delay_ms)]

    # Build the full-width bitmap of the text (no wrapping).
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    # Create a full-width image first so we can measure text width.
    full_width = size * 3  # initial estimate; will be recalculated
    full_img = Image.new("RGB", (full_width, size), bg_color)
    draw = ImageDraw.Draw(full_img)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    # Recalculate with correct width: visible window + text + exit buffer.
    full_width = size + text_width + size
    full_img = Image.new("RGB", (full_width, size), bg_color)
    draw = ImageDraw.Draw(full_img)
    draw.text((size, 0), text, font=font, fill=color)

    full_pixels = list(full_img.getdata())

    # Extract sliding windows of width ``size``.
    frames = []
    max_offset = full_width - size  # slide until window is past the text
    offset = 0
    while offset <= max_offset:
        frame_pixels = []
        for py in range(size):
            for px in range(size):
                src_x = offset + px
                if src_x < full_img.width:
                    frame_pixels.append(full_pixels[py * full_img.width + src_x])
                else:
                    frame_pixels.append(bg_color)
        frames.append((frame_pixels, delay_ms))
        offset += frame_px

    return frames
