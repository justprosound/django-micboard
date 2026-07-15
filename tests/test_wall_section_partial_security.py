"""Security and rendering contracts for the wall-section partial."""

from __future__ import annotations

from unittest.mock import patch

from django.urls import reverse
from django.utils.html import escape

import pytest

from micboard.services.kiosk.dtos import (
    KioskChargerGroupSnapshot,
    KioskChargerSnapshot,
    KioskPerformerSnapshot,
    WallSectionSnapshot,
)
from tests.factories.hardware import WallSectionFactory


@pytest.mark.django_db
def test_wall_section_partial_renders_service_data_with_autoescaping(
    admin_client,
    admin_user,
) -> None:
    """Render current section data without trusting model or integration strings."""
    section_name = '<script>alert("section")</script>'
    charger_name = "<img src=x onerror=\"alert('charger')\">"
    performer_name = "<script>alert('performer')</script>"
    performer_title = "<svg onload=\"alert('title')\">"
    section = WallSectionFactory(name=section_name)
    snapshot = WallSectionSnapshot(
        id=section.pk,
        name=section_name,
        layout="grid",
        columns=2,
        performers=[
            KioskChargerGroupSnapshot(
                charger=KioskChargerSnapshot(id=4, name=charger_name, location_id=2),
                performers=[
                    KioskPerformerSnapshot(
                        performer_id=5,
                        performer_name=performer_name,
                        performer_title=performer_title,
                        performer_photo=None,
                        unit_id=6,
                        unit_type="mic_transmitter",
                        unit_battery=220,
                        unit_battery_percent=87,
                        unit_status="online",
                        unit_rf_level=-61,
                        unit_audio_level=-12,
                        channel=None,
                        assignment_priority="high",
                        slot_number=1,
                        charger_id=4,
                    )
                ],
            )
        ],
    )

    with patch(
        "micboard.services.kiosk.services.KioskService.get_section_snapshot",
        return_value=snapshot,
    ) as get_section_snapshot:
        response = admin_client.get(reverse("micboard:wall_section_partial", args=[section.pk]))

    assert response.status_code == 200
    rendered_html = response.content.decode()
    for untrusted_value in (
        section_name,
        charger_name,
        performer_name,
        performer_title,
    ):
        assert str(escape(untrusted_value)) in rendered_html
        assert untrusted_value not in rendered_html
    assert "Battery: 87%" in rendered_html
    assert "RF: -61" in rendered_html
    get_section_snapshot.assert_called_once_with(section.pk, user=admin_user)


@pytest.mark.django_db
def test_wall_section_partial_requires_authentication(django_client) -> None:
    """Reject anonymous requests before loading tenant-scoped section data."""
    section = WallSectionFactory()

    with patch(
        "micboard.services.kiosk.services.KioskService.get_section_snapshot"
    ) as get_section_snapshot:
        response = django_client.get(reverse("micboard:wall_section_partial", args=[section.pk]))

    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")
    get_section_snapshot.assert_not_called()
