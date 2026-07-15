"""Charger polling cache adapter contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from micboard.services.chargers.polling_cache import ChargerPollingCacheAdapter
from micboard.services.chargers.polling_dtos import (
    ChargerInventoryPage,
    ChargerPollingCursor,
    ChargerStationSnapshot,
)


def _manufacturer() -> SimpleNamespace:
    return SimpleNamespace(pk=7, code="shure")


def _station() -> ChargerStationSnapshot:
    return ChargerStationSnapshot(id="station-1", name="Charger", status="online", slots=[])


def test_cache_keys_and_cursor_round_trip_are_owned_by_adapter() -> None:
    manufacturer = _manufacturer()
    backend = Mock()
    backend.get.return_value = {
        "next_offset": 2,
        "inventory_size": 3,
        "inventory_fingerprint": "a" * 64,
        "stations": [_station().model_dump()],
    }

    with patch("micboard.services.chargers.polling_cache.cache", backend):
        cursor = ChargerPollingCacheAdapter.read_cursor(manufacturer)
        ChargerPollingCacheAdapter.write_cursor(manufacturer, cursor)
        ChargerPollingCacheAdapter.publish_snapshot(manufacturer, cursor.stations)
        ChargerPollingCacheAdapter.clear_cursor(manufacturer)

    cursor_key = "micboard:charger-poll:v1:7:shure"
    backend.get.assert_called_once_with(cursor_key)
    assert backend.set.call_args_list[0].args == (
        cursor_key,
        cursor.model_dump(exclude_defaults=True),
    )
    assert backend.set.call_args_list[1].args == (
        "charger_data_shure",
        [_station().model_dump()],
    )
    backend.delete.assert_called_once_with(cursor_key)


def test_cache_backend_failures_are_contained_and_redacted(caplog) -> None:
    manufacturer = _manufacturer()
    secret = "credential=cache-secret\nforged"
    backend = Mock()
    backend.get.side_effect = RuntimeError(secret)
    backend.set.side_effect = RuntimeError(secret)
    backend.delete.side_effect = RuntimeError(secret)
    cursor = ChargerPollingCursor(next_offset=0, inventory_size=0, stations=[])

    with (
        patch("micboard.services.chargers.polling_cache.cache", backend),
        caplog.at_level("ERROR"),
    ):
        recovered = ChargerPollingCacheAdapter.read_cursor(manufacturer)
        ChargerPollingCacheAdapter.write_cursor(manufacturer, cursor)
        ChargerPollingCacheAdapter.publish_snapshot(manufacturer, [_station()])
        ChargerPollingCacheAdapter.clear_cursor(manufacturer)

    assert recovered == cursor
    assert backend.set.call_count == 2
    backend.delete.assert_called_once()
    assert secret not in caplog.text


def test_continuation_policy_writes_only_resumable_pages() -> None:
    manufacturer = _manufacturer()
    station = _station()
    resumable_page = ChargerInventoryPage(
        items=[],
        start_offset=0,
        next_offset=2,
        inventory_size=3,
        inventory_fingerprint="b" * 64,
        inventory_truncated=True,
        cycle_complete=False,
    )
    one_shot_page = ChargerInventoryPage(
        items=[],
        start_offset=0,
        next_offset=0,
        inventory_truncated=True,
        cycle_complete=False,
    )

    with (
        patch.object(ChargerPollingCacheAdapter, "write_cursor") as write_cursor,
        patch.object(ChargerPollingCacheAdapter, "clear_cursor") as clear_cursor,
    ):
        ChargerPollingCacheAdapter.persist_continuation(
            manufacturer,
            inventory_page=resumable_page,
            stations=[station],
            stations_truncated=True,
            slots_truncated=True,
            cycle_failed=True,
        )
        ChargerPollingCacheAdapter.persist_continuation(
            manufacturer,
            inventory_page=one_shot_page,
            stations=[station],
            stations_truncated=False,
            slots_truncated=False,
            cycle_failed=False,
        )

    persisted = write_cursor.call_args.args[1]
    assert persisted.next_offset == 2
    assert persisted.stations == [station]
    assert persisted.stations_truncated is True
    assert persisted.slots_truncated is True
    assert persisted.cycle_failed is True
    clear_cursor.assert_called_once_with(manufacturer)


def test_finish_cycle_publishes_only_successful_snapshots_and_always_clears() -> None:
    manufacturer = _manufacturer()
    stations = [_station()]

    with (
        patch.object(ChargerPollingCacheAdapter, "publish_snapshot") as publish_snapshot,
        patch.object(ChargerPollingCacheAdapter, "clear_cursor") as clear_cursor,
    ):
        ChargerPollingCacheAdapter.finish_cycle(
            manufacturer,
            stations=stations,
            publish=False,
        )
        ChargerPollingCacheAdapter.finish_cycle(
            manufacturer,
            stations=stations,
            publish=True,
        )

    publish_snapshot.assert_called_once_with(manufacturer, stations)
    assert clear_cursor.call_count == 2
