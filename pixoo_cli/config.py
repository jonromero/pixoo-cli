"""Configuration: grid size, BLE UUIDs, device name prefixes, cache path.

All values can be overridden via environment variables so that users can
correct the defaults after running the ``discover-gatt`` diagnostic on
real hardware — no code change is required.

Environment-variable overrides
-------------------------------
``PIXOO_GRID_SIZE``       – integer (default ``16``)
``PIXOO_SERVICE_UUID``    – string (default ``"49535343-fe7d-4ae5-8fa9-9fafd205e455"``)
``PIXOO_WRITE_CHAR_UUID`` – string (default ``"49535343-8841-43f4-a8d4-ecbe34729bb3"``)
``PIXOO_NOTIFY_CHAR_UUID``– string (default ``"49535343-1e4d-4bd9-ba61-23c647249616"``)
``PIXOO_DEVICE_NAME_PREFIXES``
                           – comma-separated string (default ``"Pixoo,DIVOOM"``)
``PIXOO_CACHE_PATH``      – string (default ``"~/.cache/pixoo-cli/last_device"``)
"""

import os
from typing import Optional

# ---------------------------------------------------------------------------
# Defaults (hard-coded fallbacks)
# ---------------------------------------------------------------------------

GRID_SIZE: int = 16

SERVICE_UUID: str = "49535343-fe7d-4ae5-8fa9-9fafd205e455"

WRITE_CHAR_UUID: str = "49535343-8841-43f4-a8d4-ecbe34729bb3"

NOTIFY_CHAR_UUID: str = "49535343-1e4d-4bd9-ba61-23c647249616"

DEVICE_NAME_PREFIXES: list[str] = ["Pixoo", "DIVOOM"]

CACHE_PATH: str = "~/.cache/pixoo-cli/last_device"


# ---------------------------------------------------------------------------
# Public API — read env vars once, cache resolved values
# ---------------------------------------------------------------------------

def get_grid_size() -> int:
    """Return the grid size, from env var ``PIXOO_GRID_SIZE`` if set."""
    raw = os.environ.get("PIXOO_GRID_SIZE")
    if raw is not None:
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError(
                f"PIXOO_GRID_SIZE must be an integer, got {raw!r}"
            ) from exc
    return GRID_SIZE


def get_service_uuid() -> str:
    """Return the GATT service UUID, from env var ``PIXOO_SERVICE_UUID``."""
    return os.environ.get("PIXOO_SERVICE_UUID", SERVICE_UUID)


def get_write_char_uuid() -> str:
    """Return the write characteristic UUID, from env var ``PIXOO_WRITE_CHAR_UUID``."""
    return os.environ.get("PIXOO_WRITE_CHAR_UUID", WRITE_CHAR_UUID)


def get_notify_char_uuid() -> str:
    """Return the notify characteristic UUID, from env var ``PIXOO_NOTIFY_CHAR_UUID``."""
    return os.environ.get("PIXOO_NOTIFY_CHAR_UUID", NOTIFY_CHAR_UUID)


def get_device_name_prefixes() -> list[str]:
    """Return device-name prefixes, from env var ``PIXOO_DEVICE_NAME_PREFIXES``."""
    raw = os.environ.get("PIXOO_DEVICE_NAME_PREFIXES")
    if raw is not None:
        return [p.strip() for p in raw.split(",") if p.strip()]
    return list(DEVICE_NAME_PREFIXES)


def get_cache_path() -> str:
    """Return the cache file path, from env var ``PIXOO_CACHE_PATH``."""
    return os.environ.get("PIXOO_CACHE_PATH", CACHE_PATH)


def read_cached_device(cache_path: Optional[str] = None) -> Optional[str]:
    """Read a previously cached device address from *cache_path*.

    Returns the address string on success, or ``None`` if the file does
    not exist or is empty.

    Args:
        cache_path: Path to the cache file (defaults to
            :data:`CACHE_PATH` expanded via ``os.path.expanduser``).

    Returns:
        The cached BLE address, or ``None`` when no cache exists.
    """
    if cache_path is None:
        cache_path = get_cache_path()
    expanded = os.path.expanduser(cache_path)
    try:
        with open(expanded, "r") as f:
            content = f.read().strip()
            if content:
                return content
    except (FileNotFoundError, OSError):
        pass
    return None


__all__ = [
    "GRID_SIZE",
    "SERVICE_UUID",
    "WRITE_CHAR_UUID",
    "NOTIFY_CHAR_UUID",
    "DEVICE_NAME_PREFIXES",
    "CACHE_PATH",
    "get_grid_size",
    "get_service_uuid",
    "get_write_char_uuid",
    "get_notify_char_uuid",
    "get_device_name_prefixes",
    "get_cache_path",
]
