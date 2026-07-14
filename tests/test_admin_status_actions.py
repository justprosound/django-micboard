"""Lifecycle-safe coverage for reusable hardware admin actions."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, patch

from micboard.admin.base_admin import AdminStatusActionsMixin


@patch("micboard.services.core.hardware_lifecycle.get_lifecycle_manager")
def test_status_action_uses_validated_lifecycle_per_selected_item(
    get_lifecycle_manager: MagicMock,
) -> None:
    """Generic admin actions cannot bypass timestamps, audit, or broadcasts with update()."""
    first = SimpleNamespace(manufacturer=SimpleNamespace(code="vendor-one"))
    second = SimpleNamespace(manufacturer=SimpleNamespace(code="vendor-two"))
    lifecycle = get_lifecycle_manager.return_value
    lifecycle.transition_device.side_effect = [True, False]
    action_host = AdminStatusActionsMixin()
    action_host.message_user = Mock()

    action_host.mark_online(SimpleNamespace(), [first, second])

    assert get_lifecycle_manager.call_args_list == [call("vendor-one"), call("vendor-two")]
    assert lifecycle.transition_device.call_args_list == [
        call(
            first,
            "online",
            reason="Status changed to online through Django admin",
        ),
        call(
            second,
            "online",
            reason="Status changed to online through Django admin",
        ),
    ]
    assert "Transitioned 1 item(s)" in action_host.message_user.call_args.args[1]
