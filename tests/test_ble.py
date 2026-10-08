"""Tests for pixoo_cli.ble: PixooBLEError + discover_devices()."""

import pytest

from pixoo_cli import ble


class TestPixooBLEError:
    """PixooBLEError is a proper Exception subclass."""

    def test_is_exception(self):
        assert issubclass(ble.PixooBLEError, Exception)

    def test_default_message(self):
        err = ble.PixooBLEError("no hardware")
        assert str(err) == "no hardware"


class TestDiscoverDevices:
    """discover_devices scans BLE advertisements and filters by name prefix."""

    @pytest.fixture
    def mock_device(self):
        """Create a bleak.BLEDevice for use in mock setups."""
        from bleak import BLEDevice

        return BLEDevice

    @pytest.mark.asyncio
    async def test_returns_matching_devices(self, mock_device):
        """Mock scanner returns 2 devices; only name-matching ones are returned."""
        from unittest.mock import AsyncMock, patch

        # Create mock BLEDevice instances
        device1 = mock_device("aa:bb:cc:dd:ee:01", "Pixoo16", None)
        device2 = mock_device("aa:bb:cc:dd:ee:02", "DIVOOM Pixel", None)
        device3 = mock_device("aa:bb:cc:dd:ee:03", "SomeOtherDevice", None)

        with patch(
            "pixoo_cli.ble.BleakScanner.discover",
            new=AsyncMock(return_value=[device1, device2, device3]),
        ):
            results = await ble.discover_devices(timeout=1.0)

        assert len(results) == 2
        addresses = {addr for addr, _ in results}
        assert "aa:bb:cc:dd:ee:01" in addresses
        assert "aa:bb:cc:dd:ee:02" in addresses

    @pytest.mark.asyncio
    async def test_filters_non_matching_names(self, mock_device):
        """Devices whose names don't match any prefix are excluded."""
        from unittest.mock import AsyncMock, patch

        device1 = mock_device("aa:bb:cc:dd:ee:01", "Pixoo16", None)
        device2 = mock_device("aa:bb:cc:dd:ee:02", "OtherBrand", None)
        device3 = mock_device("aa:bb:cc:dd:ee:03", "Samsung Speaker", None)

        with patch(
            "pixoo_cli.ble.BleakScanner.discover",
            new=AsyncMock(return_value=[device1, device2, device3]),
        ):
            results = await ble.discover_devices(timeout=1.0)

        assert len(results) == 1
        assert results[0][0] == "aa:bb:cc:dd:ee:01"
        assert results[0][1] == "Pixoo16"

    @pytest.mark.asyncio
    async def test_raises_PixooBLEError_when_no_devices_match(self, mock_device):
        """When no devices match the name prefix, a clear error is raised."""
        from unittest.mock import AsyncMock, patch

        device1 = mock_device("aa:bb:cc:dd:ee:01", "Bluetooth Speaker", None)
        device2 = mock_device("aa:bb:cc:dd:ee:02", "Apple Watch", None)

        with patch(
            "pixoo_cli.ble.BleakScanner.discover",
            new=AsyncMock(return_value=[device1, device2]),
        ):
            with pytest.raises(
                ble.PixooBLEError,
                match="No Pixoo device found",
            ):
                await ble.discover_devices(timeout=1.0)

    @pytest.mark.asyncio
    async def test_single_match_returns_single_device(self, mock_device):
        """When exactly one device matches, it is returned."""
        from unittest.mock import AsyncMock, patch

        device1 = mock_device("aa:bb:cc:dd:ee:02", "Pixoo16", None)

        with patch(
            "pixoo_cli.ble.BleakScanner.discover",
            new=AsyncMock(return_value=[device1]),
        ):
            results = await ble.discover_devices(timeout=1.0)

        assert len(results) == 1
        assert results[0] == ("aa:bb:cc:dd:ee:02", "Pixoo16")

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self, mock_device):
        """Matching is case-insensitive: 'pixoo', 'PIXOO', 'Pixoo' all match."""
        from unittest.mock import AsyncMock, patch

        device1 = mock_device("aa:bb:cc:dd:ee:01", "pixoo16", None)
        device2 = mock_device("aa:bb:cc:dd:ee:02", "PIXOO32", None)
        device3 = mock_device("aa:bb:cc:dd:ee:03", "divoom_pixel", None)

        with patch(
            "pixoo_cli.ble.BleakScanner.discover",
            new=AsyncMock(return_value=[device1, device2, device3]),
        ):
            results = await ble.discover_devices(timeout=1.0)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_custom_prefixes_filter(self, mock_device):
        """Custom prefixes override the default ones."""
        from unittest.mock import AsyncMock, patch

        device1 = mock_device("aa:bb:cc:dd:ee:01", "MyCustomDevice", None)
        device2 = mock_device("aa:bb:cc:dd:ee:02", "Pixoo16", None)

        with patch(
            "pixoo_cli.ble.BleakScanner.discover",
            new=AsyncMock(return_value=[device1, device2]),
        ):
            results = await ble.discover_devices(
                name_prefixes=["MyCustomDevice"], timeout=1.0
            )

        assert len(results) == 1
        assert results[0][0] == "aa:bb:cc:dd:ee:01"
        assert results[0][1] == "MyCustomDevice"

    @pytest.mark.asyncio
    async def test_raises_PixooBLEError_on_scan_failure(self):
        """If BleakScanner raises, discover_devices wraps it in PixooBLEError."""
        from unittest.mock import patch

        with patch(
            "pixoo_cli.ble.BleakScanner.discover",
            side_effect=OSError("No BLE adapter found"),
        ):
            with pytest.raises(
                ble.PixooBLEError, match="BLE scan failed"
            ):
                await ble.discover_devices(timeout=1.0)


class TestConnect:
    """connect(address) is an async context manager wrapping BleakClient."""

    @pytest.mark.asyncio
    async def test_failing_client_raises_PixooBLEError_with_address(self):
        """When BleakClient.__aenter__ raises, connect() wraps it in
        PixooBLEError and the message contains the address."""
        from unittest.mock import AsyncMock, patch

        test_address = "aa:bb:cc:dd:ee:ff"

        with patch(
            "pixoo_cli.ble.BleakClient",
            side_effect=OSError("Connection refused"),
        ):
            with pytest.raises(
                ble.PixooBLEError, match=f"Connection failed for {test_address}"
            ):
                async with ble.connect(test_address):
                    pass  # Should not reach here

    @pytest.mark.asyncio
    async def test_successful_connect_yields_client(self):
        """A successful connect yields the BleakClient to the caller."""
        from unittest.mock import AsyncMock, patch

        mock_client = AsyncMock()
        mock_client.is_connected = True

        with patch(
            "pixoo_cli.ble.BleakClient", return_value=mock_client
        ):
            async with ble.connect("aa:bb:cc:dd:ee:01") as client:
                assert client is mock_client
                mock_client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_caller_exception_passes_through(self):
        """Exceptions raised in the caller's body are not relabeled."""
        from unittest.mock import AsyncMock, patch

        mock_client = AsyncMock()
        mock_client.is_connected = True

        with patch(
            "pixoo_cli.ble.BleakClient", return_value=mock_client
        ):
            with pytest.raises(RuntimeError, match="caller error"):
                async with ble.connect("aa:bb:cc:dd:ee:01"):
                    raise RuntimeError("caller error")


class TestSendPayloads:
    """send_payloads() writes pixel frames to the device."""

    @pytest.mark.asyncio
    async def test_writes_all_payloads_to_characteristic(self):
        """Each encoded payload is written to the GATT characteristic."""
        from unittest.mock import AsyncMock, patch

        from pixoo_cli.config import WRITE_CHAR_UUID

        payloads = [b"\x01\x02\x03", b"\x04\x05\x06", b"\x07\x08\x09"]
        write_char_uuid = WRITE_CHAR_UUID

        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_client.write_gatt_char = AsyncMock(return_value=None)

        with patch(
            "pixoo_cli.ble.BleakClient", return_value=mock_client
        ):
            async with ble.connect("aa:bb:cc:dd:ee:01") as client:
                await ble.send_payloads(client, write_char_uuid, payloads)

        assert mock_client.write_gatt_char.call_count == 3
        calls = mock_client.write_gatt_char.call_args_list
        for i, call in enumerate(calls):
            assert call[0][0] == write_char_uuid
            assert call[0][1] == payloads[i]

    @pytest.mark.asyncio
    async def test_uses_write_char_uuid_from_config(self):
        """send_payloads uses the provided write_char_uuid parameter."""
        from unittest.mock import AsyncMock, patch

        payloads = [b"\x01\x02\x03"]
        custom_uuid = "0000fff3-0000-1000-8000-00805f9b34fb"

        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_client.write_gatt_char = AsyncMock(return_value=None)

        with patch(
            "pixoo_cli.ble.BleakClient", return_value=mock_client
        ):
            async with ble.connect("aa:bb:cc:dd:ee:01") as client:
                await ble.send_payloads(client, custom_uuid, payloads)

        call_uuid = mock_client.write_gatt_char.call_args[0][0]
        assert call_uuid == custom_uuid

    @pytest.mark.asyncio
    async def test_empty_payloads_noop(self):
        """An empty payloads list results in no writes."""
        from unittest.mock import AsyncMock, patch

        from pixoo_cli.config import WRITE_CHAR_UUID

        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_client.write_gatt_char = AsyncMock(return_value=None)

        with patch(
            "pixoo_cli.ble.BleakClient", return_value=mock_client
        ):
            async with ble.connect("aa:bb:cc:dd:ee:01") as client:
                await ble.send_payloads(client, WRITE_CHAR_UUID, [])

        mock_client.write_gatt_char.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_PixooBLEError_on_write_failure(self):
        """A write_gatt_char failure is wrapped in PixooBLEError."""
        from unittest.mock import AsyncMock, patch

        from pixoo_cli.config import WRITE_CHAR_UUID

        payloads = [b"\x01\x02\x03"]
        write_char_uuid = WRITE_CHAR_UUID

        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_client.write_gatt_char = AsyncMock(
            side_effect=Exception("GATT error")
        )

        with patch(
            "pixoo_cli.ble.BleakClient", return_value=mock_client
        ):
            with pytest.raises(
                ble.PixooBLEError, match="Write to GATT characteristic failed"
            ):
                async with ble.connect("aa:bb:cc:dd:ee:01") as client:
                    await ble.send_payloads(client, write_char_uuid, payloads)


class TestListGattServices:
    """list_gatt_services(client) -> list of (service_uuid, [char_uuid])."""

    @pytest.mark.asyncio
    async def test_returns_service_char_tuples(self):
        """Mock client.services yields services with characteristic UUIDs."""
        from unittest.mock import AsyncMock, PropertyMock, patch

        # Build a mock services collection that mimics BleakGATTServiceCollection
        mock_char1 = AsyncMock()
        mock_char1.uuid = "00001"
        mock_char2 = AsyncMock()
        mock_char2.uuid = "00002"

        mock_service1 = AsyncMock()
        mock_service1.uuid = "0000fff1"
        mock_service1.characteristics = [mock_char1, mock_char2]

        mock_service2 = AsyncMock()
        mock_service2.uuid = "0000fff2"
        mock_service2.characteristics = [AsyncMock(uuid="00003")]

        mock_services = [mock_service1, mock_service2]

        mock_client = AsyncMock()
        mock_client.is_connected = True
        type(mock_client).services = PropertyMock(return_value=mock_services)

        with patch(
            "pixoo_cli.ble.BleakClient", return_value=mock_client
        ):
            async with ble.connect("aa:bb:cc:dd:ee:01") as client:
                result = ble.list_gatt_services(client)

        assert len(result) == 2
        assert result[0][0] == "0000fff1"
        assert result[0][1] == ["00001", "00002"]
        assert result[1][0] == "0000fff2"
        assert result[1][1] == ["00003"]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_services(self):
        """A device with no services returns an empty list."""
        from unittest.mock import AsyncMock, PropertyMock, patch

        mock_client = AsyncMock()
        mock_client.is_connected = True
        type(mock_client).services = PropertyMock(return_value=[])

        with patch(
            "pixoo_cli.ble.BleakClient", return_value=mock_client
        ):
            async with ble.connect("aa:bb:cc:dd:ee:01") as client:
                result = ble.list_gatt_services(client)

        assert result == []

    @pytest.mark.asyncio
    async def test_raises_PixooBLEError_on_service_discovery_failure(self):
        """If services property raises, it is wrapped in PixooBLEError."""
        from unittest.mock import AsyncMock, PropertyMock, patch

        mock_client = AsyncMock()
        mock_client.is_connected = True
        type(mock_client).services = PropertyMock(
            side_effect=Exception("not discovered")
        )

        with patch(
            "pixoo_cli.ble.BleakClient", return_value=mock_client
        ):
            with pytest.raises(
                ble.PixooBLEError, match="Service discovery failed"
            ):
                async with ble.connect("aa:bb:cc:dd:ee:01") as client:
                    ble.list_gatt_services(client)
