"""Request-level contracts for the live DisplayWall browser seam."""

from __future__ import annotations

from django.contrib.staticfiles import finders
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse
from django.utils.html import escape

import pytest

from micboard.services.kiosk.dtos import (
    DisplayWallMetadata,
    DisplayWallSnapshot,
    KioskChargerGroupSnapshot,
    KioskChargerSnapshot,
    KioskPerformerSnapshot,
    WallSectionSnapshot,
)
from tests.factories.base import UserFactory
from tests.factories.hardware import DisplayWallFactory, WallSectionFactory

pytestmark = pytest.mark.django_db

HTMX_RUNTIME = "micboard/vendor/htmx/htmx-2.0.7.min.js"


def test_inherited_and_standalone_pages_load_one_htmx_runtime(django_client) -> None:
    """Both browser shells activate their HTMX attributes exactly once."""
    user = UserFactory(is_staff=True, is_superuser=True)
    wall = DisplayWallFactory()
    django_client.force_login(user)

    inherited = django_client.get(reverse("micboard:charger_dashboard"))
    standalone = django_client.get(reverse("micboard:kiosk_display", args=[wall.kiosk_id]))

    assert inherited.status_code == 200
    assert standalone.status_code == 200
    assert inherited.content.decode().count(HTMX_RUNTIME) == 1
    assert standalone.content.decode().count(HTMX_RUNTIME) == 1
    assert finders.find(HTMX_RUNTIME)
    assert finders.find("micboard/css/accessibility.css")
    assert f'action="{reverse("micboard:kiosk_display", args=[wall.kiosk_id])}"' in (
        standalone.content.decode()
    )
    assert "fetch(heartbeatForm.action" in standalone.content.decode()
    assert "htmx:afterSwap" in standalone.content.decode()
    assert "htmx:responseError" in standalone.content.decode()
    assert "setInterval(updateTimestamp" not in standalone.content.decode()
    assert b"bootstrap-icons@1.11.1" not in inherited.content
    assert b".charger-container {" in inherited.content


def test_charger_poll_uses_dedicated_fragment_without_selector_coupling(django_client) -> None:
    """The live grid swaps the fragment body directly from its bounded endpoint."""
    user = UserFactory(is_staff=True, is_superuser=True)
    django_client.force_login(user)

    dashboard = django_client.get(reverse("micboard:charger_dashboard"))
    fragment = django_client.get(
        reverse("micboard:charger_grid"),
        HTTP_HX_REQUEST="true",
    )

    assert dashboard.status_code == 200
    assert fragment.status_code == 200
    assert f'hx-get="{reverse("micboard:charger_grid")}"' in dashboard.content.decode()
    assert 'hx-select=".charger-grid"' not in dashboard.content.decode()
    assert "charger-container" not in fragment.content.decode()


def test_kiosk_refresh_returns_escaped_html_fragment(django_client) -> None:
    """Periodic refresh returns swappable HTML, never JSON or trusted model text."""
    user = UserFactory(is_staff=True, is_superuser=True)
    wall = DisplayWallFactory()
    section_name = '<script>alert("section")</script>'
    WallSectionFactory(wall=wall, name=section_name)
    django_client.force_login(user)

    response = django_client.get(reverse("micboard:kiosk_content", args=[wall.pk]))

    rendered = response.content.decode()
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert str(escape(section_name)) in rendered
    assert section_name not in rendered
    assert '"status": "ok"' not in rendered


def test_kiosk_heartbeat_uses_csrf_protected_session_write() -> None:
    """Browser token from kiosk GET authorizes only the authenticated heartbeat POST."""
    client = Client(enforce_csrf_checks=True)
    user = UserFactory(is_staff=True, is_superuser=True)
    wall = DisplayWallFactory(last_heartbeat=None)
    client.force_login(user)
    url = reverse("micboard:kiosk_display", args=[wall.kiosk_id])

    page = client.get(url)
    rejected = client.post(url)
    accepted = client.post(url, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)

    assert page.status_code == 200
    assert rejected.status_code == 403
    assert accepted.status_code == 200
    wall.refresh_from_db()
    assert wall.last_heartbeat is not None


def _render_metric_snapshot(
    *,
    battery: int | None,
    rf_level: int | None,
    audio_level: int | None,
) -> str:
    performer = KioskPerformerSnapshot(
        performer_id=1,
        performer_name="Singer",
        performer_title="Lead",
        performer_photo=None,
        unit_id=2,
        unit_type="mic_transmitter",
        unit_battery=battery,
        unit_battery_percent=battery,
        unit_status="online",
        unit_rf_level=rf_level,
        unit_audio_level=audio_level,
        channel=None,
        assignment_priority="normal",
        slot_number=1,
        charger_id=3,
    )
    snapshot = DisplayWallSnapshot(
        wall=DisplayWallMetadata(
            id=4,
            name="Stage",
            kiosk_id="stage",
            display_width_px=1920,
            display_height_px=1080,
            orientation="landscape",
            refresh_interval_seconds=5,
            show_performer_photos=False,
            show_rf_levels=True,
            show_battery_levels=True,
            show_audio_levels=True,
        ),
        sections=[
            WallSectionSnapshot(
                id=5,
                name="Main",
                layout="grid",
                columns=3,
                performers=[
                    KioskChargerGroupSnapshot(
                        charger=KioskChargerSnapshot(id=3, name="Rack", location_id=6),
                        performers=[performer],
                    )
                ],
            )
        ],
    )
    return render_to_string("micboard/kiosk/display_content.html", {"snapshot": snapshot})


def test_kiosk_metrics_distinguish_zero_from_unknown_and_render_audio() -> None:
    """Valid zero telemetry remains visible while missing telemetry uses an em dash."""
    zero_metrics = _render_metric_snapshot(battery=0, rf_level=0, audio_level=0)
    unknown_metrics = _render_metric_snapshot(battery=None, rf_level=None, audio_level=None)

    assert '<div class="stat-value">0%</div>' in zero_metrics
    assert zero_metrics.count('<div class="stat-value">0</div>') == 2
    assert '<div class="stat audio">' in zero_metrics
    assert '<div class="stat-value">—%</div>' in unknown_metrics
    assert unknown_metrics.count('<div class="stat-value">—</div>') == 2
