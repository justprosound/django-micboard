"""Resumable charger inventory pagination and cache-failure contracts."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from django.test import override_settings

import pytest

from micboard.services.chargers.polling_service import (
    HARD_MAX_CHARGER_INVENTORY_SIZE,
    ChargerPollingService,
)


def _manufacturer() -> SimpleNamespace:
    return SimpleNamespace(pk=7, code="shure")


def _cache_backend(
    initial: dict[str, object] | None = None,
) -> tuple[Mock, dict[str, object]]:
    values = dict(initial or {})
    backend = Mock()
    backend.get.side_effect = values.get

    def set_value(key: str, value: object, *, timeout: int) -> None:
        del timeout
        values[key] = value

    backend.set.side_effect = set_value
    backend.delete.side_effect = lambda key: values.pop(key, None) is not None
    return backend, values


def _plugin(inventory: object) -> Mock:
    plugin = Mock()
    plugin.get_devices.return_value = inventory
    plugin.get_device_channels.return_value = []
    plugin.get_client.return_value.is_healthy.return_value = True
    return plugin


def _plugin_patch(plugin: Mock):
    return patch(
        "micboard.services.chargers.polling_service.get_manufacturer_plugin",
        return_value=Mock(return_value=plugin),
    )


def _snapshot_ids(value: object) -> list[str]:
    assert isinstance(value, list)
    identifiers: list[str] = []
    for station in value:
        assert isinstance(station, dict)
        station_id = station.get("id")
        assert isinstance(station_id, str)
        identifiers.append(station_id)
    return identifiers


def _inventory_fingerprint(inventory: Sequence[object]) -> str:
    return ChargerPollingService._inventory_fingerprint(inventory)


def test_inventory_fingerprint_uses_only_bounded_consumed_identity_fields() -> None:
    common = {
        "model": " SBC250\n",
        "device_type": " charger ",
        "name": "display names are not inventory identity",
    }
    first = [{**common, "api_device_id": f" {'a' * 254}ignored-tail"}]
    second = [
        {
            **common,
            "api_device_id": f"{'a' * 254} different-tail",
            "model": "SBC250",
            "device_type": "charger",
            "name": "changed display name",
        }
    ]

    fingerprint = _inventory_fingerprint(first)

    assert len(fingerprint) == 64
    assert fingerprint == _inventory_fingerprint(second)


def test_inventory_fingerprint_changes_with_normalized_identity_order() -> None:
    first = [
        {"api_device_id": "charger-a", "model": "SBC250"},
        {"api_device_id": "charger-b", "device_type": "SBC850"},
    ]
    reordered = list(reversed(first))

    assert _inventory_fingerprint(first) != _inventory_fingerprint(reordered)


def test_inventory_above_fingerprint_ceiling_preserves_last_complete_snapshot() -> None:
    manufacturer = _manufacturer()
    cursor_key = ChargerPollingService._cursor_key(manufacturer)
    public_key = "charger_data_shure"
    previous_snapshot = [{"id": "previous-complete-snapshot"}]
    backend, values = _cache_backend(
        {
            public_key: previous_snapshot,
            cursor_key: {"untrusted": "partial state"},
        }
    )
    plugin = _plugin(
        [
            {"api_device_id": f"receiver-{index}", "model": "AD4Q"}
            for index in range(HARD_MAX_CHARGER_INVENTORY_SIZE + 1)
        ]
    )

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        result = ChargerPollingService.poll(manufacturer)

    assert result.scanned_count == 0
    assert result.cached_count == 0
    assert result.inventory_truncated is True
    assert values[public_key] is previous_snapshot
    assert cursor_key not in values
    plugin.get_device_channels.assert_not_called()


@override_settings(MICBOARD_CHARGER_MAX_DEVICES=2)
def test_repeated_poll_reaches_station_behind_ordinary_inventory_prefix() -> None:
    """A stable first page of receivers cannot permanently hide a later charger."""
    manufacturer = _manufacturer()
    cursor_key = ChargerPollingService._cursor_key(manufacturer)
    public_key = "charger_data_shure"
    previous_snapshot = [{"id": "previous-complete-snapshot"}]
    backend, values = _cache_backend({public_key: previous_snapshot})
    inventory = [
        {"api_device_id": "receiver-1", "model": "AD4Q"},
        {"api_device_id": "receiver-2", "model": "ULXD4Q"},
        {"api_device_id": "charger-1", "model": "SBC250"},
    ]
    plugin = _plugin(inventory)

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        first = ChargerPollingService.poll(manufacturer)

        assert values[public_key] is previous_snapshot
        assert values[cursor_key] == {
            "next_offset": 2,
            "inventory_size": 3,
            "inventory_fingerprint": _inventory_fingerprint(inventory),
            "stations": [],
        }
        plugin.get_device_channels.assert_not_called()

        second = ChargerPollingService.poll(manufacturer)

    assert first.scanned_count == 2
    assert first.cached_count == 0
    assert second.scanned_count == 1
    assert second.cached_count == 1
    assert cursor_key not in values
    assert _snapshot_ids(values[public_key]) == ["charger-1"]
    plugin.get_device_channels.assert_called_once_with("charger-1")


@override_settings(MICBOARD_CHARGER_MAX_DEVICES=2)
def test_channel_failure_in_any_page_preserves_last_complete_snapshot() -> None:
    """A failed station subrequest makes the entire paginated cycle non-publishable."""
    manufacturer = _manufacturer()
    cursor_key = ChargerPollingService._cursor_key(manufacturer)
    public_key = "charger_data_shure"
    previous_snapshot = [{"id": "previous-complete-snapshot"}]
    backend, values = _cache_backend({public_key: previous_snapshot})
    inventory = [
        {"api_device_id": "charger-failed", "model": "SBC250"},
        {"api_device_id": "charger-good", "model": "SBC250"},
        {"api_device_id": "charger-tail", "model": "SBC250"},
    ]
    plugin = _plugin(inventory)
    plugin.get_device_channels.side_effect = [RuntimeError("private channel failure"), [], []]

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        first = ChargerPollingService.poll(manufacturer)

        assert first.failed_count == 1
        assert values[cursor_key]["cycle_failed"] is True
        assert _snapshot_ids(values[cursor_key]["stations"]) == ["charger-good"]
        assert values[public_key] is previous_snapshot

        completed = ChargerPollingService.poll(manufacturer)

    assert completed.failed_count == 0
    assert cursor_key not in values
    assert values[public_key] is previous_snapshot


@override_settings(MICBOARD_CHARGER_MAX_DEVICES=2)
def test_cursor_accumulates_in_inventory_order_and_deduplicates_across_pages() -> None:
    manufacturer = _manufacturer()
    backend, values = _cache_backend()
    plugin = _plugin(
        [
            {"api_device_id": "charger-z", "model": "SBC250"},
            {"api_device_id": "receiver", "model": "AD4Q"},
            {"api_device_id": "charger-a", "model": "SBC850"},
            {"api_device_id": " charger-z ", "model": "SBC250"},
        ]
    )

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        ChargerPollingService.poll(manufacturer)
        result = ChargerPollingService.poll(manufacturer)

    assert result.cached_count == 2
    assert _snapshot_ids(values["charger_data_shure"]) == [
        "charger-z",
        "charger-a",
    ]
    assert plugin.get_device_channels.call_args_list == [call("charger-z"), call("charger-a")]


@override_settings(MICBOARD_CHARGER_MAX_DEVICES=2)
def test_changed_inventory_size_restarts_cycle_without_stale_stations() -> None:
    manufacturer = _manufacturer()
    public_key = "charger_data_shure"
    previous_snapshot = [{"id": "previous-complete-snapshot"}]
    backend, values = _cache_backend({public_key: previous_snapshot})
    plugin = _plugin(
        [
            {"api_device_id": "stale-charger", "model": "SBC250"},
            {"api_device_id": "receiver-1", "model": "AD4Q"},
            {"api_device_id": "receiver-2", "model": "AD4Q"},
            {"api_device_id": "later-charger", "model": "SBC850"},
        ]
    )

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        ChargerPollingService.poll(manufacturer)
        plugin.get_devices.return_value = [
            {"api_device_id": "replacement-charger", "model": "SBC250"},
            {"api_device_id": "receiver", "model": "AD4Q"},
            {"api_device_id": "tail-charger", "model": "SBC850"},
        ]
        restarted = ChargerPollingService.poll(manufacturer)

        assert restarted.scanned_count == 2
        assert values[public_key] is previous_snapshot

        completed = ChargerPollingService.poll(manufacturer)

    assert completed.cached_count == 2
    assert _snapshot_ids(values[public_key]) == [
        "replacement-charger",
        "tail-charger",
    ]
    assert plugin.get_device_channels.call_args_list == [
        call("stale-charger"),
        call("replacement-charger"),
        call("tail-charger"),
    ]


@override_settings(MICBOARD_CHARGER_MAX_DEVICES=2)
def test_same_length_inventory_reorder_restarts_without_hybrid_station_order() -> None:
    manufacturer = _manufacturer()
    backend, values = _cache_backend()
    plugin = _plugin(
        [
            {"api_device_id": "charger-a", "model": "SBC250"},
            {"api_device_id": "charger-b", "model": "SBC250"},
            {"api_device_id": "charger-c", "model": "SBC250"},
        ]
    )

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        ChargerPollingService.poll(manufacturer)
        plugin.get_devices.return_value = [
            {"api_device_id": "charger-c", "model": "SBC250"},
            {"api_device_id": "charger-b", "model": "SBC250"},
            {"api_device_id": "charger-a", "model": "SBC250"},
        ]

        restarted = ChargerPollingService.poll(manufacturer)
        completed = ChargerPollingService.poll(manufacturer)

    assert restarted.scanned_count == 2
    assert completed.cached_count == 3
    assert _snapshot_ids(values["charger_data_shure"]) == [
        "charger-c",
        "charger-b",
        "charger-a",
    ]
    assert plugin.get_device_channels.call_args_list == [
        call("charger-a"),
        call("charger-b"),
        call("charger-c"),
        call("charger-b"),
        call("charger-a"),
    ]


@override_settings(MICBOARD_CHARGER_MAX_DEVICES=2)
def test_same_length_identity_change_discards_stale_accumulated_station() -> None:
    manufacturer = _manufacturer()
    backend, values = _cache_backend()
    plugin = _plugin(
        [
            {"api_device_id": "stale-charger", "model": "SBC250"},
            {"api_device_id": "receiver", "model": "AD4Q"},
            {"api_device_id": "tail-charger", "model": "SBC850"},
        ]
    )

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        ChargerPollingService.poll(manufacturer)
        plugin.get_devices.return_value = [
            {"api_device_id": "replacement-charger", "model": "SBC250"},
            {"api_device_id": "receiver", "model": "AD4Q"},
            {"api_device_id": "tail-charger", "model": "SBC850"},
        ]

        ChargerPollingService.poll(manufacturer)
        completed = ChargerPollingService.poll(manufacturer)

    assert completed.cached_count == 2
    assert _snapshot_ids(values["charger_data_shure"]) == [
        "replacement-charger",
        "tail-charger",
    ]
    assert plugin.get_device_channels.call_args_list == [
        call("stale-charger"),
        call("replacement-charger"),
        call("tail-charger"),
    ]


@override_settings(MICBOARD_CHARGER_MAX_DEVICES=2)
def test_invalid_cursor_restarts_first_page_and_preserves_public_snapshot() -> None:
    manufacturer = _manufacturer()
    cursor_key = ChargerPollingService._cursor_key(manufacturer)
    public_key = "charger_data_shure"
    previous_snapshot = [{"id": "previous-complete-snapshot"}]
    backend, values = _cache_backend(
        {
            cursor_key: {"next_offset": -1, "inventory_size": 3, "stations": []},
            public_key: previous_snapshot,
        }
    )
    inventory = [
        {"api_device_id": "receiver-1", "model": "AD4Q"},
        {"api_device_id": "receiver-2", "model": "AD4Q"},
        {"api_device_id": "charger-1", "model": "SBC250"},
    ]
    plugin = _plugin(inventory)

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        result = ChargerPollingService.poll(manufacturer)

    assert result.scanned_count == 2
    assert values[public_key] is previous_snapshot
    assert values[cursor_key] == {
        "next_offset": 2,
        "inventory_size": 3,
        "inventory_fingerprint": _inventory_fingerprint(inventory),
        "stations": [],
    }
    plugin.get_device_channels.assert_not_called()


@pytest.mark.parametrize(
    "cached_fingerprint",
    [None, "not-a-valid-sha256-fingerprint"],
)
@override_settings(MICBOARD_CHARGER_MAX_DEVICES=2)
def test_missing_or_invalid_cursor_fingerprint_restarts_first_page(
    cached_fingerprint: str | None,
) -> None:
    manufacturer = _manufacturer()
    cursor_key = ChargerPollingService._cursor_key(manufacturer)
    inventory = [
        {"api_device_id": "receiver-1", "model": "AD4Q"},
        {"api_device_id": "receiver-2", "model": "AD4Q"},
        {"api_device_id": "charger-1", "model": "SBC250"},
    ]
    cached_cursor: dict[str, object] = {
        "next_offset": 2,
        "inventory_size": 3,
        "stations": [{"id": "stale", "name": "Stale", "status": "online", "slots": []}],
    }
    if cached_fingerprint is not None:
        cached_cursor["inventory_fingerprint"] = cached_fingerprint
    backend, values = _cache_backend({cursor_key: cached_cursor})
    plugin = _plugin(inventory)

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        result = ChargerPollingService.poll(manufacturer)

    assert result.scanned_count == 2
    assert result.cached_count == 0
    assert values[cursor_key] == {
        "next_offset": 2,
        "inventory_size": 3,
        "inventory_fingerprint": _inventory_fingerprint(inventory),
        "stations": [],
    }
    plugin.get_device_channels.assert_not_called()


@override_settings(MICBOARD_CHARGER_MAX_DEVICES=2)
def test_partial_poll_contains_cursor_read_and_write_failures(caplog) -> None:
    secret = "credential=cache-secret\nforged"
    backend = Mock()
    backend.get.side_effect = RuntimeError(secret)
    backend.set.side_effect = RuntimeError(secret)
    plugin = _plugin(
        [
            {"api_device_id": "receiver-1", "model": "AD4Q"},
            {"api_device_id": "receiver-2", "model": "AD4Q"},
            {"api_device_id": "charger-1", "model": "SBC250"},
        ]
    )

    with (
        _plugin_patch(plugin),
        patch("micboard.services.chargers.polling_service.cache", backend),
        caplog.at_level("ERROR"),
    ):
        result = ChargerPollingService.poll(_manufacturer())

    assert result.scanned_count == 2
    assert result.cached_count == 0
    assert secret not in caplog.text
    backend.set.assert_called_once()
    backend.delete.assert_not_called()


def test_complete_poll_contains_snapshot_write_and_cursor_delete_failures(caplog) -> None:
    secret = "credential=cache-secret\nforged"
    backend = Mock()
    backend.get.return_value = None
    backend.set.side_effect = RuntimeError(secret)
    backend.delete.side_effect = RuntimeError(secret)
    plugin = _plugin([{"api_device_id": "charger-1", "model": "SBC250"}])

    with (
        _plugin_patch(plugin),
        patch("micboard.services.chargers.polling_service.cache", backend),
        caplog.at_level("ERROR"),
    ):
        result = ChargerPollingService.poll(_manufacturer())

    assert result.cached_count == 1
    assert secret not in caplog.text
    backend.set.assert_called_once()
    backend.delete.assert_called_once()


@override_settings(MICBOARD_CHARGER_MAX_DEVICES=2)
def test_truncated_one_shot_inventory_preserves_complete_public_snapshot() -> None:
    manufacturer = _manufacturer()
    cursor_key = ChargerPollingService._cursor_key(manufacturer)
    public_key = "charger_data_shure"
    previous_snapshot = [{"id": "previous-complete-snapshot"}]
    backend, values = _cache_backend(
        {
            cursor_key: {"next_offset": 1, "inventory_size": 3, "stations": []},
            public_key: previous_snapshot,
        }
    )
    consumed = 0

    def inventory() -> Iterator[dict[str, str]]:
        nonlocal consumed
        for index in range(3):
            consumed += 1
            yield {"api_device_id": f"charger-{index}", "model": "SBC250"}

    plugin = _plugin(inventory())
    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        result = ChargerPollingService.poll(manufacturer)

    assert consumed == 3
    assert result.inventory_truncated is True
    assert result.cached_count == 2
    assert values[public_key] is previous_snapshot
    assert cursor_key not in values


@override_settings(MICBOARD_CHARGER_MAX_STATIONS=1)
def test_cursor_stations_are_rebounded_in_stable_order_when_limit_shrinks() -> None:
    manufacturer = _manufacturer()
    cursor_key = ChargerPollingService._cursor_key(manufacturer)
    inventory = [
        {"api_device_id": "first", "model": "SBC250"},
        {"api_device_id": "second", "model": "SBC850"},
        {"api_device_id": "receiver", "model": "AD4Q"},
    ]
    backend, values = _cache_backend(
        {
            cursor_key: {
                "next_offset": 2,
                "inventory_size": 3,
                "inventory_fingerprint": _inventory_fingerprint(inventory),
                "stations": [
                    {"id": "first", "name": "First", "status": "online", "slots": []},
                    {
                        "id": "first",
                        "name": "Duplicate",
                        "status": "offline",
                        "slots": [],
                    },
                    {"id": "second", "name": "Second", "status": "online", "slots": []},
                ],
            }
        }
    )
    plugin = _plugin(inventory)

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        result = ChargerPollingService.poll(manufacturer)

    assert result.cached_count == 1
    assert result.stations_truncated is True
    assert _snapshot_ids(values["charger_data_shure"]) == ["first"]
    plugin.get_device_channels.assert_not_called()


@override_settings(MICBOARD_CHARGER_MAX_DEVICES=2, MICBOARD_CHARGER_MAX_STATIONS=2)
def test_station_cap_retains_same_exact_vendor_order_prefix_across_cycles() -> None:
    """A complete snapshot remains stable instead of rotating partial station cohorts."""
    manufacturer = _manufacturer()
    backend, values = _cache_backend()
    plugin = _plugin(
        [{"api_device_id": f"charger-{index}", "model": "SBC250"} for index in range(4)]
    )

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        ChargerPollingService.poll(manufacturer)
        first_cycle = ChargerPollingService.poll(manufacturer)
        ChargerPollingService.poll(manufacturer)
        second_cycle = ChargerPollingService.poll(manufacturer)

    assert first_cycle.cached_count == second_cycle.cached_count == 2
    assert first_cycle.stations_truncated is second_cycle.stations_truncated is True
    assert _snapshot_ids(values["charger_data_shure"]) == [
        "charger-0",
        "charger-1",
    ]
    assert plugin.get_device_channels.call_args_list == [
        call("charger-0"),
        call("charger-1"),
        call("charger-0"),
        call("charger-1"),
    ]


@override_settings(
    MICBOARD_CHARGER_MAX_DEVICES=2,
    MICBOARD_CHARGER_MAX_STATIONS=1,
    MICBOARD_CHARGER_MAX_SLOTS=1,
)
def test_cursor_retains_snapshot_truncation_flags_until_cycle_completion() -> None:
    manufacturer = _manufacturer()
    cursor_key = ChargerPollingService._cursor_key(manufacturer)
    backend, values = _cache_backend()
    plugin = _plugin(
        [
            {"api_device_id": "charger-0", "model": "SBC250"},
            {"api_device_id": "charger-1", "model": "SBC850"},
            {"api_device_id": "receiver", "model": "AD4Q"},
        ]
    )
    plugin.get_device_channels.return_value = [
        {"channel": 0, "tx": {"battery_percentage": 50}},
        {"channel": 1, "tx": {"battery_percentage": 75}},
    ]

    with _plugin_patch(plugin), patch("micboard.services.chargers.polling_service.cache", backend):
        partial = ChargerPollingService.poll(manufacturer)

        assert partial.stations_truncated is True
        assert partial.slots_truncated is True
        cursor = values[cursor_key]
        assert isinstance(cursor, dict)
        assert cursor["stations_truncated"] is True
        assert cursor["slots_truncated"] is True

        complete = ChargerPollingService.poll(manufacturer)

    assert complete.stations_truncated is True
    assert complete.slots_truncated is True
    assert _snapshot_ids(values["charger_data_shure"]) == ["charger-0"]
