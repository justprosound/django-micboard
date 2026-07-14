"""Transactional staged-device deletion and discovery reconciliation contracts."""

from __future__ import annotations

from typing import cast
from unittest.mock import call, patch

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveredDevice
from micboard.services.sync.discovered_device_deletion_service import (
    DiscoveredDeviceDeletionService,
)
from tests.factories.discovery import DiscoveredDeviceFactory, ManufacturerFactory

pytestmark = pytest.mark.django_db


def test_delete_schedules_one_claimed_reconciliation_per_manufacturer(
    django_capture_on_commit_callbacks,
) -> None:
    first_manufacturer = cast(Manufacturer, ManufacturerFactory())
    second_manufacturer = cast(Manufacturer, ManufacturerFactory())
    DiscoveredDeviceFactory(manufacturer=first_manufacturer, ip="192.0.2.50")
    DiscoveredDeviceFactory(manufacturer=first_manufacturer, ip="192.0.2.51")
    DiscoveredDeviceFactory(manufacturer=second_manufacturer, ip="192.0.2.52")
    queryset = DiscoveredDevice.objects.all()

    with (
        patch(
            "micboard.services.sync.discovery_trigger_service._dispatch_scheduled_discovery"
        ) as dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        result = DiscoveredDeviceDeletionService.delete(queryset)

    assert result.deleted_count == 3
    assert result.scheduled_manufacturers == 2
    assert not DiscoveredDevice.objects.exists()
    assert dispatch.call_args_list == [
        call(
            manufacturer_id=first_manufacturer.pk,
            scan_cidrs=False,
            scan_fqdns=False,
        ),
        call(
            manufacturer_id=second_manufacturer.pk,
            scan_cidrs=False,
            scan_fqdns=False,
        ),
    ]


def test_delete_empty_queryset_has_no_remote_side_effect(
    django_capture_on_commit_callbacks,
) -> None:
    with (
        patch(
            "micboard.services.sync.discovery_trigger_service._dispatch_scheduled_discovery"
        ) as dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        result = DiscoveredDeviceDeletionService.delete(DiscoveredDevice.objects.none())

    assert result.deleted_count == 0
    assert result.scheduled_manufacturers == 0
    dispatch.assert_not_called()
