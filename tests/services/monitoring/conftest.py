"""Shared monitoring-service test fixtures."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings

import pytest

from tests.factories.base import UserFactory
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory
from tests.factories.monitoring import PerformerAssignmentFactory


@pytest.fixture
def assigned_unit(db) -> SimpleNamespace:
    """Create an assigned unit, RF channel, monitoring group, and user."""
    with (
        override_settings(TESTING=True),
        patch(
            "micboard.services.manufacturer.plugin_registry.PluginRegistry.get_plugin",
            return_value=None,
        ),
    ):
        chassis = WirelessChassisFactory(max_channels=1)
        channel = chassis.rf_channels.get(channel_number=1)
        unit = WirelessUnitFactory(
            base_chassis=chassis,
            manufacturer=chassis.manufacturer,
            assigned_resource=channel,
            slot=1,
        )

    assignment = PerformerAssignmentFactory(wireless_unit=unit, alert_on_audio_low=True)
    user = UserFactory()
    assignment.monitoring_group.users.add(user)
    return SimpleNamespace(unit=unit, assignment=assignment, user=user, channel=channel)
