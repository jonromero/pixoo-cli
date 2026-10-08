#!/usr/bin/env python3
"""Which packet format does my Pixoo speak?

Connects to a Pixoo, listens on its notify characteristic, and sends the
same "brightness 10%" command twice: once in the classic ``01 ... 02``
frame, once in the ``FE EF AA 55`` envelope. Brightness is restored
after each try. Whichever format gets a command reply (and dims the
screen) is the one your device understands.

Usage:
    ./tools/probe.py              # scan for a Pixoo
    ./tools/probe.py ADDRESS      # or connect to a known address
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from bleak import BleakClient  # noqa: E402

from pixoo_cli import ble, config  # noqa: E402
from pixoo_cli.protocol import build_packet  # noqa: E402

CMD_SET_BRIGHTNESS = 0x74


def classic_packet(cmd: int, args: bytes) -> bytes:
    """The ``01 LEN CMD ARGS CHECKSUM 02`` frame other projects document."""
    length = len(args) + 3
    body = bytes([length & 0xFF, length >> 8, cmd]) + args
    checksum = sum(body) & 0xFFFF
    return b"\x01" + body + bytes([checksum & 0xFF, checksum >> 8, 0x02])


def describe(reply: bytes) -> str:
    """Decode a ``01 LEN 04 CMD 55 ... 02`` reply into something readable."""
    if len(reply) >= 6 and reply[0] == 0x01 and reply[3] == 0x04:
        cmd = reply[4]
        if cmd == 0x33:
            return f"transport ack (seq {reply[6:10].hex()}) - packet received"
        return f"command reply for 0x{cmd:02x} - command executed"
    return "unknown"


async def main() -> None:
    if len(sys.argv) > 1:
        address = sys.argv[1]
    else:
        print("Scanning...")
        address, name = (await ble.discover_devices())[0]
        print(f"Found {name} at {address}")

    async with BleakClient(address, timeout=20) as client:
        replies: list[bytes] = []

        def on_notify(_char, data: bytearray) -> None:
            replies.append(bytes(data))
            print(f"    <- {bytes(data).hex()}  ({describe(bytes(data))})")

        await client.start_notify(config.get_notify_char_uuid(), on_notify)
        await asyncio.sleep(1)

        results = {}
        for label, make in [
            ("classic 01...02", lambda b: classic_packet(CMD_SET_BRIGHTNESS, bytes([b]))),
            ("FE EF AA 55 envelope", lambda b: build_packet(CMD_SET_BRIGHTNESS, bytes([b]))),
        ]:
            replies.clear()
            packet = make(10)
            print(f"\n{label}: dimming to 10% for 3s")
            print(f"    -> {packet.hex()}")
            await client.write_gatt_char(config.get_write_char_uuid(), packet, response=True)
            await asyncio.sleep(3)
            executed = any(r[3:4] == b"\x04" and r[4] != 0x33 for r in replies)
            await client.write_gatt_char(config.get_write_char_uuid(), make(100), response=True)
            await asyncio.sleep(2)
            results[label] = executed

    print("\nResult:")
    for label, executed in results.items():
        print(f"  {label:22} {'WORKS' if executed else 'no command reply'}")
    if not any(results.values()):
        print("\nNeither format got a command reply. Please open an issue with this output.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ble.PixooBLEError as exc:
        sys.exit(str(exc))
