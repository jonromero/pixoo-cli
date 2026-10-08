"""Tests for pixoo_cli.config: constants and env-var overrides."""

import os
import pytest

from pixoo_cli import config


class TestConstants:
    """Hard-coded defaults are sensible values."""

    def test_grid_size_default(self):
        assert config.GRID_SIZE == 16

    def test_service_uuid_default(self):
        assert config.SERVICE_UUID == "49535343-fe7d-4ae5-8fa9-9fafd205e455"

    def test_write_char_uuid_default(self):
        assert config.WRITE_CHAR_UUID == "49535343-8841-43f4-a8d4-ecbe34729bb3"

    def test_notify_char_uuid_default(self):
        assert config.NOTIFY_CHAR_UUID == "49535343-1e4d-4bd9-ba61-23c647249616"

    def test_device_name_prefixes_default(self):
        assert config.DEVICE_NAME_PREFIXES == ["Pixoo", "DIVOOM"]

    def test_cache_path_default(self):
        assert config.CACHE_PATH == "~/.cache/pixoo-cli/last_device"


class TestEnvOverrides:
    """Each getter respects its corresponding environment variable."""

    def test_get_grid_size_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PIXOO_GRID_SIZE", "32")
        assert config.get_grid_size() == 32

    def test_get_grid_size_invalid_env_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("PIXOO_GRID_SIZE", "abc")
        with pytest.raises(ValueError, match="PIXOO_GRID_SIZE must be an integer"):
            config.get_grid_size()

    def test_get_service_uuid_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PIXOO_SERVICE_UUID", "deadbeef-0000-1000-8000-00805f9b34fb")
        assert config.get_service_uuid() == "deadbeef-0000-1000-8000-00805f9b34fb"

    def test_get_write_char_uuid_from_env(self, monkeypatch: pytest.MonkeyPatch):
        """T13: assert env var PIXOO_WRITE_CHAR_UUID overrides the default constant."""
        monkeypatch.setenv("PIXOO_WRITE_CHAR_UUID", "aabb1113-0000-1000-8000-00805f9b34fb")
        assert config.get_write_char_uuid() == "aabb1113-0000-1000-8000-00805f9b34fb"

    def test_get_notify_char_uuid_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PIXOO_NOTIFY_CHAR_UUID", "ccdd1114-0000-1000-8000-00805f9b34fb")
        assert config.get_notify_char_uuid() == "ccdd1114-0000-1000-8000-00805f9b34fb"

    def test_get_device_name_prefixes_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PIXOO_DEVICE_NAME_PREFIXES", "CustomFoo,Bar")
        assert config.get_device_name_prefixes() == ["CustomFoo", "Bar"]

    def test_get_device_name_prefixes_empty_comma(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PIXOO_DEVICE_NAME_PREFIXES", "Foo,,Bar,")
        assert config.get_device_name_prefixes() == ["Foo", "Bar"]

    def test_get_cache_path_from_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PIXOO_CACHE_PATH", "/tmp/pixoo.cache")
        assert config.get_cache_path() == "/tmp/pixoo.cache"


class TestNoEnvFallback:
    """When no env var is set, the getter returns the hard-coded default."""

    def test_get_grid_size_fallback(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("PIXOO_GRID_SIZE", raising=False)
        assert config.get_grid_size() == config.GRID_SIZE

    def test_get_service_uuid_fallback(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("PIXOO_SERVICE_UUID", raising=False)
        assert config.get_service_uuid() == config.SERVICE_UUID

    def test_get_write_char_uuid_fallback(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("PIXOO_WRITE_CHAR_UUID", raising=False)
        assert config.get_write_char_uuid() == config.WRITE_CHAR_UUID

    def test_get_notify_char_uuid_fallback(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("PIXOO_NOTIFY_CHAR_UUID", raising=False)
        assert config.get_notify_char_uuid() == config.NOTIFY_CHAR_UUID

    def test_get_device_name_prefixes_fallback(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("PIXOO_DEVICE_NAME_PREFIXES", raising=False)
        assert config.get_device_name_prefixes() == config.DEVICE_NAME_PREFIXES

    def test_get_cache_path_fallback(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("PIXOO_CACHE_PATH", raising=False)
        assert config.get_cache_path() == config.CACHE_PATH
