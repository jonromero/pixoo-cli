"""argparse subcommands wiring image/text/protocol/ble together.

The main() entry point is implemented in a lazy fashion: the CLI
parser and subcommand handlers are defined here, and the actual work
is delegated to the inner modules (image, text, protocol, ble).

Usage examples
--------------
::

    pixoo-cli text "Hello"
    pixoo-cli text "Hi" --size 32
    pixoo-cli scroll "Scrolling text" --size 16
    pixoo-cli image photo.png --size 32
    pixoo-cli gif anim.gif --size 16
    pixoo-cli discover-gatt

All subcommands accept ``--size N`` (default 16) and ``--rescan``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Optional

from pixoo_cli import ble
from pixoo_cli import config
from pixoo_cli import image as img_module
from pixoo_cli import protocol
from pixoo_cli import text

logger = logging.getLogger(__name__)

# Named color aliases for the CLI (a small subset of CSS basic colors)
NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0),
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "orange": (255, 165, 0),
    "purple": (128, 0, 128),
    "pink": (255, 192, 203),
}


def _parse_color(value: str) -> tuple[int, int, int]:
    """Parse a color string into an (r, g, b) tuple.

    Accepts ``#RRGGBB`` hex strings or basic named colors (case-insensitive).

    Args:
        value: A hex string (``#RRGGBB``) or named color.

    Returns:
        An ``(r, g, b)`` tuple of uint8 values.

    Raises:
        ValueError: If the string is not a valid color.
    """
    value = value.strip()
    if value.startswith("#"):
        hex_str = value.lstrip("#")
        if len(hex_str) != 6:
            raise ValueError(
                f"Invalid color: {value!r} (expected #RRGGBB)"
            )
        try:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
        except ValueError:
            raise ValueError(
                f"Invalid color: {value!r} (expected #RRGGBB)"
            )
        return (r, g, b)

    lower = value.lower()
    if lower in NAMED_COLORS:
        return NAMED_COLORS[lower]

    raise ValueError(f"Unknown color: {value!r}")


async def _pick_device_and_send(
    size: int,
    send_fn,
    *args,
    rescan: bool = False,
    **kwargs,
) -> None:
    """Discover devices, let the user pick, connect, and send payloads.

    Args:
        size: Grid size (e.g. 16).
        send_fn: An async function that takes (client, *args, **kwargs).
        *args, **kwargs: Passed through to *send_fn*.
        rescan: When ``True``, always scan BLE advertisements even if a
            cached device address exists.

    Raises:
        ble.PixooBLEError: If no matching device is found.
    """
    cache_path = config.get_cache_path()
    cached_address = None if rescan else config.read_cached_device(cache_path)

    if cached_address is None:
        devices = await ble.discover_devices()
        address = pick_device(devices)
    else:
        address = cached_address

    async with ble.connect(address) as client:
        await send_fn(client, *args, **kwargs)
        # Cache the address only after a successful send.
        expanded_cache_path = os.path.expanduser(cache_path)
        cache_dir = os.path.dirname(expanded_cache_path)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        with open(expanded_cache_path, "w") as f:
            f.write(address)


def _cmd_text(args: argparse.Namespace) -> None:
    """Handle the ``text`` subcommand."""
    size = args.size
    color = _parse_color(args.color)

    pixels = text.render_text_to_pixels(
        args.text, size, color=color, bg_color=_parse_color(args.bg_color),
    )
    packet = protocol.encode_static_frame(pixels, size)

    async def _send(client: ble.BleakClient) -> None:
        await ble.send_payloads(
            client, config.get_write_char_uuid(), [packet],
        )

    asyncio.run(_pick_device_and_send(size, _send, rescan=args.rescan))


def _cmd_scroll(args: argparse.Namespace) -> None:
    """Handle the ``scroll`` subcommand."""
    size = args.size
    color = _parse_color(args.color)

    frames = text.render_scrolling_frames(
        args.text, size,
        color=color,
        bg_color=_parse_color(args.bg_color),
        frame_px=args.frame_px,
        delay_ms=args.delay_ms,
    )
    packets = protocol.encode_animation_frames(frames, size)

    async def _send(client: ble.BleakClient) -> None:
        await ble.send_payloads(
            client, config.get_write_char_uuid(), packets,
            delay_ms=0,
        )

    asyncio.run(_pick_device_and_send(size, _send, rescan=args.rescan))


def _cmd_image(args: argparse.Namespace) -> None:
    """Handle the ``image`` subcommand."""
    size = args.size
    pixels = img_module.load_and_prepare_image(args.path, size)
    packet = protocol.encode_static_frame(pixels, size)

    async def _send(client: ble.BleakClient) -> None:
        await ble.send_payloads(
            client, config.get_write_char_uuid(), [packet],
        )

    asyncio.run(_pick_device_and_send(size, _send, rescan=args.rescan))


def _cmd_gif(args: argparse.Namespace) -> None:
    """Handle the ``gif`` subcommand."""
    size = args.size
    frame_pairs = img_module.load_gif_frames(args.path, size)

    if not frame_pairs:
        raise ValueError("GIF contains no frames.")

    packets = protocol.encode_animation_frames(frame_pairs, size)

    async def _send(client: ble.BleakClient) -> None:
        await ble.send_payloads(
            client, config.get_write_char_uuid(), packets,
        )

    asyncio.run(_pick_device_and_send(size, _send, rescan=args.rescan))


def _cmd_discover_gatt(args: argparse.Namespace) -> None:
    """Handle the ``discover-gatt`` subcommand."""
    async def _show(client: ble.BleakClient) -> None:
        services = ble.list_gatt_services(client)
        print("Discovered GATT services:")
        for svc_uuid, chars in services:
            print(f"  Service: {svc_uuid}")
            for ch_uuid in chars:
                print(f"    Characteristic: {ch_uuid}")

    asyncio.run(_pick_device_and_send(0, _show, rescan=args.rescan))


def pick_device(devices: list[tuple[str, str]]) -> str:
    """Select a device from a list of discovered devices.

    Args:
        devices: A list of ``(address, name)`` tuples returned by
            :func:`ble.discover_devices`.

    Returns:
        The address string of the selected device.

    Raises:
        IndexError: If *devices* is empty (should not happen —
            :func:`ble.discover_devices` raises before an empty list
            reaches this function).
    """
    if len(devices) == 1:
        return devices[0][0]
    # Multiple devices: print numbered list and prompt.
    print("Multiple devices found:")
    for i, (addr, name) in enumerate(devices, start=1):
        print(f"  {i}. {name} ({addr})")
    while True:
        try:
            choice = int(input("Choose device [1-{}]: ".format(len(devices))))
        except (ValueError, EOFError):
            print("Invalid input.", file=sys.stderr)
            continue
        if 1 <= choice <= len(devices):
            return devices[choice - 1][0]
        print(f"Please enter a number between 1 and {len(devices)}.")


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="pixoo-cli",
        description="Push text, images, or GIFs to a Divoom Pixoo BLE display.",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=config.get_grid_size(),
        help="Grid size (default: %(default)s).",
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        default=False,
        help="Ignore cached device address and rescan.",
    )

    subparsers = parser.add_subparsers(dest="command")

    # text subcommand
    text_parser = subparsers.add_parser(
        "text", help="Display static text on the Pixoo.",
    )
    text_parser.add_argument("text", help="Text string to display.")
    text_parser.add_argument(
        "--color", default="#FFFFFF",
        help="Text color as #RRGGBB or named color (default: #FFFFFF).",
    )
    text_parser.add_argument(
        "--bg-color", default="#000000",
        help="Background color (default: #000000).",
    )

    # scroll subcommand
    scroll_parser = subparsers.add_parser(
        "scroll", help="Scroll text across the Pixoo.",
    )
    scroll_parser.add_argument("text", help="Text string to scroll.")
    scroll_parser.add_argument(
        "--color", default="#FFFFFF",
        help="Text color as #RRGGBB or named color (default: #FFFFFF).",
    )
    scroll_parser.add_argument(
        "--bg-color", default="#000000",
        help="Background color (default: #000000).",
    )
    scroll_parser.add_argument(
        "--frame-px", type=int, default=1,
        help="Pixels to advance per scroll frame (default: 1).",
    )
    scroll_parser.add_argument(
        "--delay-ms", type=int, default=100,
        help="Delay between frames in ms (default: 100).",
    )

    # image subcommand
    image_parser = subparsers.add_parser(
        "image", help="Display a static image on the Pixoo.",
    )
    image_parser.add_argument("path", help="Path to an image file.")

    # gif subcommand
    gif_parser = subparsers.add_parser(
        "gif", help="Display an animated GIF on the Pixoo.",
    )
    gif_parser.add_argument("path", help="Path to a GIF file.")

    # discover-gatt subcommand
    subparsers.add_parser(
        "discover-gatt",
        help="Connect and list GATT services/characteristics.",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    """Parse arguments and dispatch to the appropriate subcommand.

    Args:
        argv: Command-line arguments (default: ``sys.argv[1:]``).

    Raises:
        SystemExit: On error (prints to stderr, exits 1).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Dispatch to subcommand handler.
    handlers = {
        "text": _cmd_text,
        "scroll": _cmd_scroll,
        "image": _cmd_image,
        "gif": _cmd_gif,
        "discover-gatt": _cmd_discover_gatt,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help(sys.stderr)
        sys.exit(1)

    try:
        handler(args)
    except (
        FileNotFoundError,
        ValueError,
        ble.PixooBLEError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
