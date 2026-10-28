"""Chassis online/offline admin actions run on real rows through the status lifecycle."""

from unittest.mock import patch

from django.contrib import messages
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

import pytest

from micboard.admin.receivers import WirelessChassisAdmin
from micboard.models.audit.activity_log import ActivityLog
from micboard.models.hardware.wireless_chassis import WirelessChassis
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db


def _request(user: object) -> object:
    request = RequestFactory().post("/admin/micboard/wirelesschassis/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def _flashed(request: object) -> list[tuple[int, str]]:
    return [(m.level, str(m.message)) for m in request._messages]  # type: ignore[attr-defined]


def _run(action: str, user: object, *chassis: WirelessChassis) -> object:
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())
    request = _request(user)
    queryset = WirelessChassis.objects.filter(pk__in=[c.pk for c in chassis])
    getattr(model_admin, action)(request, queryset)
    return request


@pytest.mark.parametrize(
    ("action", "status"),
    [
        ("mark_online", "discovered"),
        ("mark_online", "retired"),
        ("mark_offline", "retired"),
    ],
)
def test_disallowed_move_is_reported_to_the_operator_not_raised(
    action: str, status: str, admin_user: object
) -> None:
    """A status the graph refuses leaves the row alone and says why."""
    chassis = WirelessChassisFactory(status=status)

    request = _run(action, admin_user, chassis)

    chassis.refresh_from_db()
    assert chassis.status == status
    flashed = _flashed(request)
    assert any(level == messages.WARNING and str(chassis.pk) in text for level, text in flashed)
    assert any("0 chassis" in text for _level, text in flashed)


@pytest.mark.parametrize(
    ("action", "start", "end", "online"),
    [("mark_online", "offline", "online", True), ("mark_offline", "online", "offline", False)],
)
def test_allowed_move_keeps_timestamps_audit_and_broadcast(
    action: str,
    start: str,
    end: str,
    online: bool,
    admin_user: object,
    django_capture_on_commit_callbacks: object,
) -> None:
    """The lifecycle still stamps, audits and broadcasts an allowed move."""
    chassis = WirelessChassisFactory(status=start)
    audits = ActivityLog.objects.filter(operation="status_change", object_id=chassis.pk).count()

    with (
        patch(
            "micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_status"
        ) as broadcast,
        django_capture_on_commit_callbacks(execute=True),  # type: ignore[operator]
    ):
        request = _run(action, admin_user, chassis)

    chassis.refresh_from_db()
    assert (chassis.status, chassis.is_online) == (end, online)
    assert (chassis.last_online_at if online else chassis.last_offline_at) is not None
    assert (
        ActivityLog.objects.filter(operation="status_change", object_id=chassis.pk).count()
        == audits + 1
    )
    assert broadcast.call_args.kwargs["status"] == end
    assert any("1 chassis" in text for _level, text in _flashed(request))


def test_mixed_selection_updates_allowed_chassis_and_names_each_refused_one(
    admin_user: object,
) -> None:
    """One refused chassis does not stop its siblings."""
    allowed = WirelessChassisFactory(status="offline")
    refused = WirelessChassisFactory(status="discovered")

    request = _run("mark_online", admin_user, allowed, refused)

    allowed.refresh_from_db()
    refused.refresh_from_db()
    assert (allowed.status, refused.status) == ("online", "discovered")
    flashed = _flashed(request)
    assert [t for lvl, t in flashed if lvl == messages.WARNING and str(refused.pk) in t]
    assert any("1 chassis" in text for _level, text in flashed)
