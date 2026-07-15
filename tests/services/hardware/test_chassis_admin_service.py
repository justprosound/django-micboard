"""Query and projection contracts for wireless-chassis admin reads."""

from __future__ import annotations

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.services.hardware.chassis_admin_service import ChassisAdminService
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory

pytestmark = pytest.mark.django_db


def test_hardware_layout_has_constant_query_count(django_assert_num_queries) -> None:
    """Growing chassis and channel counts must not introduce layout N+1 queries."""
    first = WirelessChassisFactory(status="online", max_channels=2)
    second = WirelessChassisFactory(
        status="degraded",
        manufacturer=first.manufacturer,
        max_channels=2,
    )
    first_unit = WirelessUnitFactory(base_chassis=first, frequency="500.125")
    second_unit = WirelessUnitFactory(base_chassis=second, frequency="")
    RFChannel.objects.filter(chassis=first, channel_number=1).update(
        active_wireless_unit=first_unit
    )
    RFChannel.objects.filter(chassis=second, channel_number=1).update(
        active_iem_receiver=second_unit
    )

    with django_assert_num_queries(2):
        page = ChassisAdminService.get_hardware_layout(queryset=WirelessChassis.objects.all())

    assert len(page.manufacturers) == 1
    chassis = [item for location in page.manufacturers[0].locations for item in location.chassis]
    assert [item.channels[0].frequency for item in chassis] == ["500.125", None]


def test_hardware_summary_is_one_query_and_exposes_no_assignment_metadata(
    django_assert_num_queries,
) -> None:
    """The readonly summary uses the performer domain and never queries per channel."""
    chassis = WirelessChassisFactory(max_channels=2)
    assigned_unit = WirelessUnitFactory(base_chassis=chassis, device_type="mic_transmitter")
    unassigned_unit = WirelessUnitFactory(base_chassis=chassis, slot=2, device_type="iem_receiver")
    RFChannel.objects.filter(chassis=chassis, channel_number=1).update(
        active_wireless_unit=assigned_unit
    )
    RFChannel.objects.filter(chassis=chassis, channel_number=2).update(
        active_iem_receiver=unassigned_unit
    )
    with django_assert_num_queries(1):
        summary = ChassisAdminService.get_hardware_summary(chassis_id=chassis.pk)

    assert [channel.channel_number for channel in summary] == [1, 2]
    assert summary[0].unit_type == "MIC_TRANSMITTER"
    assert summary[1].unit_type == "IEM_RECEIVER"
