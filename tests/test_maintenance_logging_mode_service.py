"""Behavioral coverage for maintenance logging-mode selection."""

from __future__ import annotations

from unittest.mock import Mock, call

from micboard.services.maintenance import logging_mode as mode_module
from micboard.services.maintenance.logging_mode import LoggingModeService


def test_logging_mode_expiry_set_and_priority(monkeypatch) -> None:
    original_set_mode = LoggingModeService.set_mode
    monkeypatch.setattr(mode_module.time, "time", Mock(return_value=100.0))
    cache_get = Mock(side_effect=["high", 99.0])
    monkeypatch.setattr(mode_module.cache, "get", cache_get)
    set_mode = Mock()
    monkeypatch.setattr(LoggingModeService, "set_mode", set_mode)
    assert LoggingModeService.get_current_mode() == "normal"
    set_mode.assert_called_once_with("normal")

    monkeypatch.setattr(mode_module.cache, "set", Mock())
    monkeypatch.setattr(mode_module.cache, "delete", Mock())
    monkeypatch.setattr(LoggingModeService, "set_mode", original_set_mode)
    LoggingModeService.set_mode("high", ttl_seconds=30)
    assert mode_module.cache.set.call_args_list == [
        call(mode_module.CACHE_KEY, "high", timeout=None),
        call(mode_module.CACHE_EXPIRY_KEY, 130.0, timeout=None),
    ]
    LoggingModeService.set_mode("normal")
    mode_module.cache.delete.assert_called_once_with(mode_module.CACHE_EXPIRY_KEY)

    monkeypatch.setattr(LoggingModeService, "get_current_mode", Mock(return_value="normal"))
    assert LoggingModeService.should_log("passive") is True
    assert LoggingModeService.should_log("normal") is True
    assert LoggingModeService.should_log("high") is False
    assert LoggingModeService.should_log("unknown") is True  # type: ignore[arg-type]


def test_logging_mode_returns_nonexpired_cached_mode(monkeypatch) -> None:
    monkeypatch.setattr(mode_module.cache, "get", Mock(side_effect=["passive", None]))
    assert LoggingModeService.get_current_mode() == "passive"
