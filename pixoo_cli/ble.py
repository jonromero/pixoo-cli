"""BLE discovery, connection, and payload sending via bleak.

Implements ``PixooBLEError`` for all BLE-layer exceptions, and
``discover_devices()`` which scans for nearby Pixoo devices by name
prefix and returns a list of ``(address, name)`` tuples.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from bleak import BleakClient, BleakScanner

from pixoo_cli import config

logger = logging.getLogger(__name__)

# Fallback GATT write chunk size when the connection's negotiated ATT MTU
# is unavailable (e.g. not yet connected, or a non-bleak test double).
# 20 bytes is the default ATT MTU minus the 3-byte write-command header.
_DEFAULT_WRITE_CHUNK_SIZE = 20


class PixooBLEError(Exception):
    """Base exception for all Pixoo BLE-layer errors."""


async def discover_devices(
    name_prefixes: Optional[list[str]] = None,
    timeout: float = 5.0,
) -> list[tuple[str, str]]:
    """Scan for BLE devices whose name matches any *name_prefixes*.

    Parameters
    ----------
    name_prefixes :
        List of case-insensitive substrings to match against device names.
        Defaults to :data:`config.DEVICE_NAME_PREFIXES` (``["Pixoo", "DIVOOM"]``).
    timeout :
        Seconds to scan for devices before giving up.

    Returns
    -------
    list[tuple[str, str]]
        A list of ``(address, name)`` tuples for every device whose name
        contains (case-insensitive) any of the *name_prefixes*.

    Raises
    ------
    PixooBLEError
        If the scan itself fails (e.g. BLE hardware not available).
    """
    if name_prefixes is None:
        name_prefixes = config.get_device_name_prefixes()

    try:
        devices = await BleakScanner.discover(
            timeout=timeout,
            service_uuids=None,
            scanning_mode="active",
        )

    except Exception as exc:
        raise PixooBLEError(f"BLE scan failed: {exc}") from exc

    matched: list[tuple[str, str]] = []
    for device in devices:
        device_name: Optional[str] = device.name
        if device_name is None:
            continue
        if any(
            prefix.lower() in device_name.lower()
            for prefix in name_prefixes
        ):
            matched.append((device.address, device_name))

    if not matched:
        raise PixooBLEError(
            "No Pixoo device found — check the device is on and "
            "within range."
        )

    return matched


@asynccontextmanager
async def connect(
    address: str,
) -> AsyncIterator[BleakClient]:
    """Context manager that connects to a Pixoo device by BLE address.

    Parameters
    ----------
    address :
        The BLE MAC address (or UUID) of the target device.

    Yields
    ------
    BleakClient
        A connected ``BleakClient`` instance.

    Raises
    ------
    PixooBLEError
        If the connection attempt fails for any reason (address does not
        exist, BLE adapter unavailable, device not in range, etc.).
    """
    try:
        client = BleakClient(address)
        await client.connect()
    except Exception as exc:
        raise PixooBLEError(
            f"Connection failed for {address}: {exc}"
        ) from exc
    try:
        yield client
    finally:
        await client.disconnect()


async def send_payloads(
    client: BleakClient,
    write_char_uuid: str,
    payloads: list[bytes],
    delay_ms: int = 0,
) -> None:
    """Write a list of encoded pixel-frame payloads to the device.

    Parameters
    ----------
    client :
        A connected ``BleakClient`` instance (from :func:`connect`).
    write_char_uuid :
        The GATT characteristic UUID to write to.
    payloads :
        A list of encoded frame bytes, each produced by
        :func:`protocol.encode_static_frame` or
        :func:`protocol.encode_animation_frames`.
    delay_ms :
        Milliseconds to wait between each payload write.  Default 0.

    Raises
    ------
    PixooBLEError
        If writing to the GATT characteristic fails.

    Notes
    -----
    Each payload is itself split into chunks no larger than the
    connection's negotiated ATT MTU. The Pixoo's BLE characteristic is a
    transparent UART bridge, so splitting a packet across multiple GATT
    writes is transparent to the device (it just reassembles the raw
    byte stream) — but writing more than ``mtu - 3`` bytes in a single
    GATT write exceeds what the link can carry and drops the connection.
    Writes are acknowledged (write-with-response) so none are dropped.
    """
    mtu = getattr(client, "mtu_size", None)
    chunk_size = mtu - 3 if isinstance(mtu, int) and mtu > 3 else _DEFAULT_WRITE_CHUNK_SIZE

    for payload in payloads:
        try:
            for offset in range(0, len(payload), chunk_size):
                await client.write_gatt_char(
                    write_char_uuid,
                    payload[offset : offset + chunk_size],
                    # Acknowledged writes: unacknowledged ones get dropped
                    # when sent back-to-back (multi-packet animations never
                    # complete) or when we disconnect right after sending.
                    response=True,
                )
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)
        except Exception as exc:
            raise PixooBLEError(
                f"Write to GATT characteristic failed: {exc}"
            ) from exc


def list_gatt_services(
    client: BleakClient,
) -> list[tuple[str, list[str]]]:
    """Return the GATT services and their characteristic UUIDs.

    Parameters
    ----------
    client :
        A connected ``BleakClient`` instance (from :func:`connect`).

    Returns
    -------
    list[tuple[str, list[str]]]
        A list of ``(service_uuid, [char_uuid, ...])`` tuples for every
        discovered GATT service on the device.

    Raises
    ------
    PixooBLEError
        If service discovery has not been performed yet (device not
        connected) or any other BLE error occurs.
    """
    try:
        services = client.services
    except Exception as exc:
        raise PixooBLEError(
            f"Service discovery failed: {exc}"
        ) from exc

    result: list[tuple[str, list[str]]] = []
    for service in services:
        char_uuids = [
            str(characteristic.uuid)
            for characteristic in service.characteristics
        ]
        result.append((str(service.uuid), char_uuids))

    return result


__all__ = [
    "PixooBLEError",
    "discover_devices",
    "connect",
    "send_payloads",
    "list_gatt_services",
]
