"""Poll-to-alert integration coverage across the native Huey boundary."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.core import mail
from django.test import override_settings

import pytest

from micboard.models.monitoring.alert import Alert
from micboard.tasks.sync.polling import poll_api_server_device
from micboard.utils.dependencies import enqueue_huey_task
from tests.factories.base import UserFactory
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import (
    ManufacturerAPIServerFactory,
    WirelessChassisFactory,
    WirelessUnitFactory,
)
from tests.factories.locations import BuildingFactory, LocationFactory
from tests.factories.monitoring import (
    MonitoringGroupLocationFactory,
    PerformerAssignmentFactory,
    UserAlertPreferenceFactory,
)
from tests.factories.multitenancy import OrganizationFactory


def _device_payload(*, device_id: str, ip: str, battery: int) -> list[dict[str, object]]:
    """Return one representative Shure device snapshot with embedded channel telemetry."""
    return [
        {
            "id": device_id,
            "ipAddress": ip,
            "type": "ULX-D",
            "modelName": "ULXD4Q",
            "deviceName": "Main rack receiver",
            "firmwareVersion": "2.8.1",
            "channels": [
                {
                    "channelNumber": 1,
                    "transmitter": {
                        "slot": 1,
                        "name": "Lead vocal",
                        "batteryBars": battery,
                        "rfLevel": -42,
                        "audioLevel": -12,
                        "status": "online",
                    },
                }
            ],
        }
    ]


@pytest.mark.django_db(transaction=True)
@override_settings(
    MICBOARD_API_SERVER_ALLOWED_HOSTS=["tenant-a-api.example.test"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_native_huey_poll_persists_scoped_update_and_dispatches_one_alert() -> None:
    """Healthy, qualifying, replayed, and cross-tenant polls preserve one lifecycle."""
    manufacturer = ManufacturerFactory(code="shure", name="Shure")
    tenant_a = OrganizationFactory()
    tenant_b = OrganizationFactory()
    location_a = LocationFactory(
        building=BuildingFactory(organization_id=tenant_a.pk),
        name="Tenant A rack",
    )
    location_b = LocationFactory(
        building=BuildingFactory(organization_id=tenant_b.pk),
        name="Tenant B rack",
    )
    server_a = ManufacturerAPIServerFactory(
        manufacturer="shure",
        base_url="https://tenant-a-api.example.test:10000",
        shared_key="tenant-a-server-secret",
        location_name=location_a.name,
    )
    server_b = ManufacturerAPIServerFactory(
        manufacturer="shure",
        base_url="https://tenant-b-api.example.test:10000",
        shared_key="tenant-b-server-secret",
        location_name=location_b.name,
    )
    chassis_a = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="tenant-a-device",
        serial_number="tenant-a-serial",
        ip="192.0.2.10",
        location=location_a,
        max_channels=1,
        status="online",
    )
    chassis_b = WirelessChassisFactory(
        manufacturer=manufacturer,
        api_device_id="tenant-b-device",
        serial_number="tenant-b-serial",
        ip="192.0.2.20",
        location=location_b,
        max_channels=1,
        status="online",
    )
    channel_a = chassis_a.rf_channels.get(channel_number=1)
    channel_b = chassis_b.rf_channels.get(channel_number=1)
    unit_a = WirelessUnitFactory(
        manufacturer=manufacturer,
        base_chassis=chassis_a,
        assigned_resource=channel_a,
        slot=1,
        battery=200,
        status="online",
    )
    unit_b = WirelessUnitFactory(
        manufacturer=manufacturer,
        base_chassis=chassis_b,
        assigned_resource=channel_b,
        slot=1,
        battery=200,
        status="online",
    )
    recipient_a = UserFactory(email="tenant-a-operator@example.test")
    recipient_b = UserFactory(email="tenant-b-operator@example.test")
    assignment_a = PerformerAssignmentFactory(
        wireless_unit=unit_a,
        alert_on_battery_low=True,
        alert_on_signal_loss=False,
        alert_on_audio_low=False,
        alert_on_hardware_offline=False,
    )
    assignment_b = PerformerAssignmentFactory(
        wireless_unit=unit_b,
        alert_on_battery_low=True,
        alert_on_signal_loss=False,
        alert_on_audio_low=False,
        alert_on_hardware_offline=False,
    )
    assignment_a.monitoring_group.users.add(recipient_a)
    assignment_b.monitoring_group.users.add(recipient_b)
    MonitoringGroupLocationFactory(
        monitoring_group=assignment_a.monitoring_group,
        location=location_a,
    )
    MonitoringGroupLocationFactory(
        monitoring_group=assignment_b.monitoring_group,
        location=location_b,
    )
    UserAlertPreferenceFactory(
        user=recipient_a,
        notification_method="email",
        battery_low_threshold=20,
        battery_critical_threshold=10,
    )
    UserAlertPreferenceFactory(
        user=recipient_b,
        notification_method="email",
        battery_low_threshold=20,
        battery_critical_threshold=10,
    )

    healthy = _device_payload(
        device_id=chassis_a.api_device_id,
        ip=str(chassis_a.ip),
        battery=200,
    )
    qualifying = _device_payload(
        device_id=chassis_a.api_device_id,
        ip=str(chassis_a.ip),
        battery=10,
    )
    client_context = MagicMock()
    client_context.__enter__.return_value.devices.get_devices.side_effect = [
        healthy,
        qualifying,
        qualifying,
    ]

    with patch(
        "micboard.integrations.shure.client.ShureSystemAPIClient",
        return_value=client_context,
    ) as client_class:
        healthy_result = enqueue_huey_task(
            poll_api_server_device,
            server_a.pk,
            chassis_a.pk,
        ).get()
        unit_a.refresh_from_db()
        assert healthy_result == {
            "api_server_id": server_a.pk,
            "chassis_id": chassis_a.pk,
            "devices_updated": 1,
        }
        assert unit_a.battery == 200
        assert not Alert.objects.exists()
        assert len(mail.outbox) == 0

        qualifying_result = enqueue_huey_task(
            poll_api_server_device,
            server_a.pk,
            chassis_a.pk,
        ).get()
        replay_result = enqueue_huey_task(
            poll_api_server_device,
            server_a.pk,
            chassis_a.pk,
        ).get()

        transport_calls_before_rejected_poll = client_class.call_count
        rejected_result = enqueue_huey_task(
            poll_api_server_device,
            server_a.pk,
            chassis_b.pk,
        ).get()

    assert qualifying_result["devices_updated"] == 1
    assert replay_result["devices_updated"] == 1
    assert rejected_result is None
    assert client_class.call_count == transport_calls_before_rejected_poll
    assert client_class.call_count == 3
    assert all(
        call.kwargs
        == {
            "base_url": server_a.base_url,
            "shared_key": server_a.shared_key,
        }
        for call in client_class.call_args_list
    )

    chassis_a.refresh_from_db()
    unit_a.refresh_from_db()
    chassis_b.refresh_from_db()
    unit_b.refresh_from_db()
    server_a.refresh_from_db()
    server_b.refresh_from_db()
    alert = Alert.objects.get()
    assert chassis_a.name == "Main rack receiver"
    assert chassis_a.firmware_version == "2.8.1"
    assert unit_a.battery == 10
    assert alert.alert_type == "battery_critical"
    assert alert.user == recipient_a
    assert alert.assignment == assignment_a
    assert alert.channel == channel_a
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [recipient_a.email]
    assert server_a.status == "active"
    assert server_a.last_health_check is not None
    assert server_b.status == "unknown"
    assert server_b.last_health_check is None

    assert chassis_b.name != "Main rack receiver"
    assert unit_b.battery == 200
    assert not Alert.objects.filter(user=recipient_b).exists()
