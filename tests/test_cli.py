"""Tests for pixoo_cli.cli: pick_device() selection helper and error paths."""

import sys
from unittest.mock import AsyncMock, patch

import pytest

from pixoo_cli import cli
from pixoo_cli import ble


class TestPickDevice:
    """pick_device auto-picks, prompts, or raises as appropriate."""

    def test_one_device_returns_address(self):
        """A single device is auto-selected; its address is returned."""
        devices = [("aa:bb:cc:dd:ee:01", "Pixoo16")]
        assert cli.pick_device(devices) == "aa:bb:cc:dd:ee:01"

    def test_multiple_devices_prompts_and_returns_selected(self):
        """Multiple devices print a numbered list; mocked input picks one."""
        devices = [
            ("aa:bb:cc:dd:ee:01", "Pixoo16"),
            ("aa:bb:cc:dd:ee:02", "DIVOOM Pixel"),
            ("aa:bb:cc:dd:ee:03", "Pixoo32"),
        ]

        # Mock input() so the user "selects" device 3 (index 2)
        with patch("builtins.input", return_value="3"):
            result = cli.pick_device(devices)

        assert result == "aa:bb:cc:dd:ee:03"

    def test_multiple_devices_selects_first(self):
        """Selecting 1 from multiple devices returns the first address."""
        devices = [
            ("aa:bb:cc:dd:ee:01", "Pixoo16"),
            ("aa:bb:cc:dd:ee:02", "DIVOOM Pixel"),
        ]

        with patch("builtins.input", return_value="1"):
            result = cli.pick_device(devices)

        assert result == "aa:bb:cc:dd:ee:01"


class TestErrorPaths:
    """Distinct stderr messages for no-device vs connection-failure."""

    def test_no_device_found_stderr(self, capfd, monkeypatch, tmp_path):
        """When no device is found, main() prints a clear error to stderr."""
        # A real cached address would skip discovery and hit real hardware.
        monkeypatch.setenv("PIXOO_CACHE_PATH", str(tmp_path / "last_device"))
        error_msg = (
            "No Pixoo device found — check the device is on and within range."
        )
        with patch.object(
            cli.ble,
            "discover_devices",
            new=AsyncMock(
                side_effect=ble.PixooBLEError(error_msg)
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                cli.main(["text", "hello"])

        assert exc_info.value.code == 1
        captured = capfd.readouterr()
        assert "No Pixoo device found" in captured.err

    def test_connection_failed_stderr(self, capfd):
        """When connection fails, main() prints a connection-error to stderr."""
        conn_error = ble.PixooBLEError(
            "Connection failed for aa:bb:cc:dd:ee:01: "
            "Failed to connect."
        )
        with patch.object(
            cli.ble,
            "discover_devices",
            new=AsyncMock(
                return_value=[("aa:bb:cc:dd:ee:01", "Pixoo16")]
            ),
        ):
            with patch.object(
                cli,
                "pick_device",
                new=lambda devices: ("aa:bb:cc:dd:ee:01", "Pixoo16"),
            ):
                # Create a mock async context manager that raises
                # PixooBLEError during __aenter__.
                cm = AsyncMock()
                cm.__aenter__ = AsyncMock(side_effect=conn_error)
                cm.__aexit__ = AsyncMock(return_value=False)

                with patch.object(
                    cli.ble,
                    "connect",
                    return_value=cm,
                ):
                    with pytest.raises(SystemExit) as exc_info:
                        cli.main(["text", "hello"])

            assert exc_info.value.code == 1
            captured = capfd.readouterr()
            assert "Connection failed" in captured.err
