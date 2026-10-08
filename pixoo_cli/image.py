"""Image decoding into pixel grids (Pillow only, no BLE)."""

import os

from PIL import Image, UnidentifiedImageError


__all__ = [
    "load_image",
    "resize_to_grid",
    "image_to_pixels",
    "load_and_prepare_image",
    "load_gif_frames",
]


def load_image(path):
    """Open a single-frame image and return it as RGB.

    Args:
        path: Path to an image file (PNG, JPG, GIF frame, ...).

    Returns:
        A ``PIL.Image.Image`` in ``"RGB"`` mode.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file cannot be decoded as an image.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Image file not found: {path}")
    try:
        with Image.open(path) as im:
            return im.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Cannot decode image: {path}") from exc


def _validate_size(size):
    """Validate that ``size`` is a positive integer.

    Raises:
        ValueError: If ``size`` is not a positive integer.
    """
    if not isinstance(size, int) or size <= 0:
        raise ValueError(f"size must be a positive integer, got {size!r}")


def resize_to_grid(img, size):
    """Resize an image to exactly ``size`` x ``size`` pixels.

    Uses ``NEAREST`` resampling to keep pixelated graphics sharp.

    Args:
        img: A ``PIL.Image.Image`` (any mode).
        size: Grid edge length in pixels (e.g. 16).

    Returns:
        A new ``PIL.Image.Image`` in ``"RGB"`` mode with dimensions
        ``size`` x ``size``.

    Raises:
        ValueError: If ``size`` is not a positive integer.
    """
    _validate_size(size)
    if not isinstance(img, Image.Image):
        raise ValueError(f"Expected a PIL Image, got {type(img).__name__}")
    return img.resize((size, size), Image.NEAREST)


def image_to_pixels(img):
    """Convert an image to a flat list of ``(r, g, b)`` tuples.

    The list is row-major: ``(0, 0)``, ``(1, 0)``, ..., ``(size-1, 0)``,
    ``(0, 1)``, ...

    If the image is not in ``"RGB"`` mode, it is converted first.

    Args:
        img: A ``PIL.Image.Image`` (any mode).

    Returns:
        A ``list`` of ``len(img.width) * len(img.height)`` ``(r, g, b)``
        tuples.

    Raises:
        ValueError: If ``img`` is not a PIL Image.
    """
    if not isinstance(img, Image.Image):
        raise ValueError("Expected a PIL Image, got " + type(img).__name__)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return list(img.getdata())


def load_and_prepare_image(path, size):
    """Load an image, resize to grid, and flatten to pixels.

    Convenience pipeline that calls ``load_image`` ->
    ``resize_to_grid`` -> ``image_to_pixels``.

    Args:
        path: Path to an image file.
        size: Grid edge length in pixels.

    Returns:
        A flat ``list`` of ``(r, g, b)`` tuples (length ``size * size``).

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file cannot be decoded or ``size`` is invalid.
    """
    img = load_image(path)
    return image_to_pixels(resize_to_grid(img, size))


def load_gif_frames(path, size):
    """Extract all frames from a GIF and return as (pixels, delay_ms) pairs.

    Each frame is resized to exactly ``size`` x ``size`` pixels and
    flattened into a row-major list of ``(r, g, b)`` tuples.  The
    per-frame delay (in milliseconds) is read from the GIF's
    ``duration`` metadata.  If no delay is present, 100 ms is
    used as a default.

    Args:
        path: Path to a GIF file.
        size: Grid edge length in pixels (e.g. 16 for a Pixoo-16).

    Returns:
        A ``list`` of ``(pixels, delay_ms)`` tuples, one per frame.
        ``pixels`` is a ``list`` of ``size * size`` ``(r, g, b)``
        tuples, row-major.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file is not a valid GIF or ``size`` is not
            a positive integer.
    """
    _validate_size(size)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"GIF file not found: {path}")

    try:
        with Image.open(path) as im:
            if im.format != "GIF":
                raise ValueError(f"Not a GIF file: {path}")
            frames = []
            frame_idx = 0
            while True:
                resized = resize_to_grid(im.convert("RGB"), size)
                pixels = image_to_pixels(resized)

                # Extract delay from the GIF's disposal/delay extension.
                delay = im.info.get("duration", 100)
                if delay is None or delay <= 0:
                    delay = 100

                frames.append((pixels, int(delay)))

                try:
                    im.seek(frame_idx + 1)
                except EOFError:
                    break
                frame_idx += 1

            return frames
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"Cannot decode GIF: {path}") from exc