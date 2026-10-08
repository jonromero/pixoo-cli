"""Tests for pixoo_cli.image: load_image, resize_to_grid, image_to_pixels."""

import pytest

import pixoo_cli
from pixoo_cli import image


def test_package_imports():
    assert hasattr(pixoo_cli, "__version__")


def test_load_image_returns_rgb(tmp_path):
    from PIL import Image

    path = tmp_path / "img.png"
    Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(path)

    img = image.load_image(str(path))
    assert img.mode == "RGB"
    assert img.size == (8, 8)


def test_load_image_missing_path():
    with pytest.raises(FileNotFoundError):
        image.load_image("/nonexistent/path/does_not_exist.png")


def test_load_image_not_an_image(tmp_path):
    path = tmp_path / "not_an_image.png"
    path.write_bytes(b"this is definitely not a png file")
    with pytest.raises(ValueError):
        image.load_image(str(path))


def test_resize_to_grid_returns_square():
    from PIL import Image

    img = Image.new("RGB", (16, 16), (10, 20, 30))
    out = image.resize_to_grid(img, 16)
    assert out.size == (16, 16)
    assert out.mode == "RGB"


def test_resize_to_grid_non_square_input():
    from PIL import Image

    img = Image.new("RGB", (32, 8), (10, 20, 30))
    out = image.resize_to_grid(img, 16)
    assert out.size == (16, 16)
    assert out.mode == "RGB"


def test_resize_to_grid_rejects_bad_size():
    from PIL import Image

    img = Image.new("RGB", (16, 16), (10, 20, 30))
    with pytest.raises(ValueError):
        image.resize_to_grid(img, 0)
    with pytest.raises(ValueError):
        image.resize_to_grid(img, -1)


def test_resize_to_grid_rejects_non_image():
    with pytest.raises(ValueError):
        image.resize_to_grid("not an image", 16)


def test_image_to_pixels_length_and_shape():
    from PIL import Image

    img = Image.new("RGB", (16, 16), (1, 2, 3))
    pixels = image.image_to_pixels(img)

    assert isinstance(pixels, list)
    assert len(pixels) == 16 * 16
    assert all(isinstance(p, tuple) and len(p) == 3 for p in pixels)
    assert all(all(isinstance(c, int) and 0 <= c <= 255 for c in p) for p in pixels)
    assert pixels[0] == (1, 2, 3)


def test_image_to_pixels_row_major_order():
    from PIL import Image

    img = Image.new("RGB", (2, 2))
    img.putpixel((0, 0), (10, 0, 0))
    img.putpixel((1, 0), (0, 10, 0))
    img.putpixel((0, 1), (0, 0, 10))
    img.putpixel((1, 1), (9, 9, 9))

    assert image.image_to_pixels(img) == [
        (10, 0, 0),
        (0, 10, 0),
        (0, 0, 10),
        (9, 9, 9),
    ]


def test_image_to_pixels_converts_non_rgb():
    from PIL import Image

    img = Image.new("L", (3, 3), 128)
    pixels = image.image_to_pixels(img)
    assert len(pixels) == 9
    assert all(p == (128, 128, 128) for p in pixels)


def test_image_to_pixels_rejects_non_image():
    with pytest.raises(ValueError):
        image.image_to_pixels("not an image")


def test_load_and_prepare_image_full_pipeline(tmp_path):
    from PIL import Image

    # Non-square source to exercise the resize step.
    path = tmp_path / "photo.png"
    Image.new("RGB", (48, 12), (200, 100, 50)).save(path)

    pixels = image.load_and_prepare_image(str(path), 16)

    assert isinstance(pixels, list)
    assert len(pixels) == 16 * 16
    assert all(isinstance(p, tuple) and len(p) == 3 for p in pixels)
    assert all(all(isinstance(c, int) and 0 <= c <= 255 for c in p) for p in pixels)


def test_load_and_prepare_image_stretches_to_grid(tmp_path):
    from PIL import Image

    path = tmp_path / "dot.png"
    img = Image.new("L", (8, 8))
    # Top-left 2x2 block white: averaging into the 4x4 grid keeps it white.
    for x in range(2):
        for y in range(2):
            img.putpixel((x, y), 255)
    img.save(path)

    pixels = image.load_and_prepare_image(str(path), 4)
    assert len(pixels) == 16
    # The white source block stretches to the top-left grid pixel.
    assert pixels[0] == (255, 255, 255)
    assert pixels[-1] == (0, 0, 0)


def test_load_and_prepare_image_missing_path():
    with pytest.raises(FileNotFoundError):
        image.load_and_prepare_image("/nonexistent/path/nope.png", 16)


def test_load_and_prepare_image_bad_size(tmp_path):
    from PIL import Image

    path = tmp_path / "img.png"
    Image.new("RGB", (8, 8)).save(path)
    with pytest.raises(ValueError):
        image.load_and_prepare_image(str(path), 0)


def test_load_gif_frames_returns_two_frames(tmp_path):
    """Build a 2-frame temp GIF and assert 2 entries with correct pixel length."""
    from PIL import Image

    # Create a 2-frame GIF
    frames = []
    for color in [(255, 0, 0), (0, 255, 0)]:
        im = Image.new("RGB", (16, 16), color)
        frames.append(im)

    gif_path = str(tmp_path / "test2frame.gif")
    frames[0].save(
        gif_path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
    )

    result = image.load_gif_frames(gif_path, 16)

    assert isinstance(result, list)
    assert len(result) == 2

    # Each entry is (pixels, delay_ms)
    for pixels, delay_ms in result:
        assert isinstance(pixels, list)
        assert len(pixels) == 16 * 16
        assert all(isinstance(p, tuple) and len(p) == 3 for p in pixels)
        assert isinstance(delay_ms, int)
        assert delay_ms > 0


def test_load_gif_frames_pixel_values(tmp_path):
    """Verify frame 0 is red and frame 1 is green."""
    from PIL import Image

    frames = []
    for color in [(255, 0, 0), (0, 255, 0)]:
        im = Image.new("RGB", (16, 16), color)
        frames.append(im)

    gif_path = str(tmp_path / "test_values.gif")
    frames[0].save(
        gif_path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=50,
        loop=0,
    )

    result = image.load_gif_frames(gif_path, 16)
    assert len(result) == 2

    pixels0, delay0 = result[0]
    pixels1, delay1 = result[1]

    # Frame 0: all pixels should be red (255, 0, 0)
    assert all(p == (255, 0, 0) for p in pixels0)
    # Frame 1: all pixels should be green (0, 255, 0)
    assert all(p == (0, 255, 0) for p in pixels1)
    # Delays should be positive integers
    assert delay0 > 0
    assert delay1 > 0


def test_load_gif_frames_rejects_bad_path():
    with pytest.raises(FileNotFoundError):
        image.load_gif_frames("/nonexistent/path/nope.gif", 16)


def test_load_gif_frames_rejects_non_gif(tmp_path):
    path = tmp_path / "not_a_gif.gif"
    path.write_bytes(b"this is not a real gif file at all")
    with pytest.raises(ValueError):
        image.load_gif_frames(str(path), 16)


def test_load_gif_frames_resizes_non_square(tmp_path):
    """GIF frames of non-square size should be resized to the requested grid."""
    from PIL import Image

    frames = []
    for color in [(100, 100, 100), (200, 200, 200)]:
        im = Image.new("RGB", (32, 8), color)
        frames.append(im)

    gif_path = str(tmp_path / "nonsquare.gif")
    frames[0].save(
        gif_path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=75,
        loop=0,
    )

    result = image.load_gif_frames(gif_path, 16)
    assert len(result) == 2
    for pixels, _ in result:
        assert len(pixels) == 16 * 16
