"""Coverage for configuration and discovery admin behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, call, patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from micboard.admin import (
    configuration,
    discovery_admin,
)
from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.audit.configuration_log import ConfigurationAuditLog
from micboard.models.discovery.configuration import ManufacturerConfiguration
from micboard.models.discovery.queue import DeviceMovementLog, DiscoveryQueue

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _request() -> Any:
    request = RequestFactory().get("/admin/")
    request.user = SimpleNamespace(pk=4, is_authenticated=True, is_superuser=True)
    return request


def _admin(admin_class: type, model: type) -> Any:
    return admin_class(model, AdminSite())


def test_configuration_admin_secure_fieldsets_and_display_helpers() -> None:
    model_admin = _admin(configuration.ManufacturerConfigurationAdmin, ManufacturerConfiguration)
    request = _request()
    obj = SimpleNamespace(
        config={"token": "secret"},
        is_active=True,
        is_valid=True,
        updated_by=SimpleNamespace(username="alice"),
        last_validated=None,
        validation_errors={},
    )
    with (
        patch.object(model_admin, "has_change_permission", return_value=False),
        patch.object(configuration, "replace_field", return_value=[("safe", {})]) as replace,
    ):
        assert model_admin.get_fieldsets(request, obj) == [("safe", {})]
    replace.assert_called_once()
    with patch.object(MicboardModelAdmin, "get_fieldsets", return_value=[("base", {})]):
        assert model_admin.get_fieldsets(request, None) == [("base", {})]
    with patch.object(configuration, "redact_secrets", return_value={"token": "***"}):
        assert '"***"' in model_admin.config_redacted(obj)
    assert "Active" in model_admin.status_badge(obj)
    assert "Valid" in model_admin.validation_badge(obj)
    assert model_admin.updated_by_name(obj) == "alice"
    assert model_admin.validation_result(obj) == "Not yet validated"
    assert model_admin.has_import_permission(request) is False
    assert model_admin.has_export_permission(request) is False

    obj.is_active = False
    obj.is_valid = False
    obj.updated_by = None
    obj.last_validated = NOW
    obj.validation_errors = {"errors": ["one", "two", "three", "four"]}
    assert "Inactive" in model_admin.status_badge(obj)
    assert "Invalid" in model_admin.validation_badge(obj)
    assert model_admin.updated_by_name(obj) == "System"
    assert "+1 more" in model_admin.validation_result(obj)
    obj.validation_errors = {"errors": []}
    assert model_admin.validation_result(obj) == "✓ Valid"
    obj.validation_errors = {"errors": ["one", "two"]}
    assert "+" not in model_admin.validation_result(obj)


def test_configuration_admin_actions_validate_apply_enable_and_disable() -> None:
    model_admin = _admin(configuration.ManufacturerConfigurationAdmin, ManufacturerConfiguration)
    model_admin.message_user = Mock()
    good = MagicMock()
    bad = MagicMock()
    with (
        patch.object(
            configuration,
            "validate_manufacturer_config",
            side_effect=[{"is_valid": True, "errors": []}, {"is_valid": False, "errors": ["bad"]}],
        ),
        patch("django.utils.timezone.now", return_value=NOW),
    ):
        model_admin.validate_config(_request(), [good, bad])
    assert good.validation_errors == {}
    assert bad.validation_errors == {"errors": ["bad"]}
    good.save.assert_called_once()
    bad.save.assert_called_once()

    model_admin.message_user.reset_mock()
    with patch.object(configuration, "apply_manufacturer_config", side_effect=[True, False]):
        model_admin.apply_config(_request(), [good, bad])
    assert model_admin.message_user.call_count == 2
    model_admin.message_user.reset_mock()
    with patch.object(configuration, "apply_manufacturer_config", return_value=True):
        model_admin.apply_config(_request(), [good])
    assert model_admin.message_user.call_count == 1
    model_admin.message_user.reset_mock()
    with patch.object(configuration, "apply_manufacturer_config", return_value=False):
        model_admin.apply_config(_request(), [bad])
    assert model_admin.message_user.call_count == 1
    queryset = MagicMock()
    queryset.update.side_effect = [2, 3]
    model_admin.enable_config(_request(), queryset)
    model_admin.disable_config(_request(), queryset)
    assert queryset.update.call_args_list == [call(is_active=True), call(is_active=False)]


def test_configuration_audit_admin_redacts_links_and_badges() -> None:
    model_admin = _admin(configuration.ConfigurationAuditLogAdmin, ConfigurationAuditLog)
    obj = SimpleNamespace(
        old_values={"token": "old"},
        new_values={"token": "new"},
        action="update",
        get_action_display=lambda: "Update",
        configuration=SimpleNamespace(id=2, code="vendor"),
        created_by=SimpleNamespace(username="alice"),
        result="success",
    )
    with (
        patch.object(configuration, "redact_secrets", return_value={"token": "***"}),
        patch.object(configuration, "reverse", return_value="/config/2/"),
    ):
        assert '"***"' in model_admin.old_values_redacted(obj)
        assert '"***"' in model_admin.new_values_redacted(obj)
        assert "Update" in model_admin.get_action_badge(obj)
        assert "vendor" in model_admin.configuration_code(obj)
    assert model_admin.created_by_name(obj) == "alice"
    assert "Success" in model_admin.result_badge(obj)
    obj.created_by = None
    obj.result = "failure"
    obj.action = "unknown"
    assert model_admin.created_by_name(obj) == "System"
    assert "Failed" in model_admin.result_badge(obj)
    assert "Update" in model_admin.get_action_badge(obj)
    assert model_admin.has_import_permission(_request()) is False
    assert model_admin.has_export_permission(_request()) is False


def test_discovery_queue_displays_conflicts_and_actions() -> None:
    model_admin = _admin(discovery_admin.DiscoveryQueueAdmin, DiscoveryQueue)
    obj = SimpleNamespace(
        status="pending",
        is_duplicate=True,
        is_ip_conflict=True,
        is_duplicate_api_id=True,
        api_id_conflict_count=2,
        check_for_duplicates=Mock(return_value={"serial": "duplicate", "empty": None}),
    )
    assert "PENDING" in model_admin.status_badge(obj)
    assert "DUPLICATE" in model_admin.conflict_indicators(obj)
    assert model_admin.conflict_analysis(obj) == "serial: duplicate"
    clean = SimpleNamespace(
        status="unknown",
        is_duplicate=False,
        is_ip_conflict=False,
        is_duplicate_api_id=False,
        check_for_duplicates=Mock(return_value={}),
    )
    assert model_admin.conflict_indicators(clean) == "—"
    assert "No conflicts" in model_admin.conflict_analysis(clean)

    result = SimpleNamespace(imported_count=3)
    with (
        patch(
            "micboard.services.sync.discovery_approval_service.DiscoveryApprovalService.approve",
            return_value=result,
        ),
        patch.object(discovery_admin.messages, "success") as success,
    ):
        model_admin.approve_devices(_request(), MagicMock())
    assert "3" in success.call_args.args[1]
    with (
        patch(
            "micboard.services.sync.discovery_approval_service.DiscoveryApprovalService.approve",
            side_effect=ValidationError(["one", "two"]),
        ),
        patch.object(discovery_admin.messages, "error") as error,
    ):
        model_admin.approve_devices(_request(), MagicMock())
    assert error.call_args.args[1] == "one; two"

    queryset = MagicMock()
    queryset.filter.return_value.update.side_effect = [2, 1]
    with (
        patch.object(discovery_admin.timezone, "now", return_value=NOW),
        patch.object(discovery_admin.messages, "success"),
    ):
        model_admin.reject_devices(_request(), queryset)
        model_admin.mark_as_duplicate(_request(), queryset)
    assert queryset.filter.call_args_list == [call(status="pending"), call(status="pending")]


def test_device_movement_admin_displays_and_acknowledges_changes() -> None:
    model_admin = _admin(discovery_admin.DeviceMovementLogAdmin, DeviceMovementLog)
    device = SimpleNamespace(
        name="Receiver",
        api_device_id="id",
        manufacturer=SimpleNamespace(name="Vendor"),
    )
    obj = SimpleNamespace(
        device=device,
        old_ip="192.0.2.1",
        new_ip="192.0.2.2",
        old_location=SimpleNamespace(name="Old"),
        new_location=SimpleNamespace(name="New"),
        acknowledged=True,
        movement_type="ip_and_location",
    )
    assert model_admin.device_name(obj) == "Receiver"
    assert model_admin.manufacturer(obj) == "Vendor"
    assert "IP:" in model_admin.movement_summary(obj)
    assert "Location:" in model_admin.movement_summary(obj)
    assert "ACKNOWLEDGED" in model_admin.acknowledged_badge(obj)
    assert "Ip And Location" in model_admin.movement_type_display(obj)
    obj.device.name = ""
    obj.old_ip = obj.new_ip
    obj.old_location = obj.new_location
    obj.acknowledged = False
    obj.movement_type = "custom"
    assert model_admin.device_name(obj) == "id"
    assert model_admin.movement_summary(obj) == "No changes detected"
    assert "PENDING" in model_admin.acknowledged_badge(obj)
    assert model_admin.movement_type_display(obj) == " Custom"
    queryset = MagicMock()
    with (
        patch.object(discovery_admin.timezone, "now", return_value=NOW),
        patch.object(discovery_admin.messages, "success"),
    ):
        model_admin.acknowledge_movements(_request(), queryset)
    queryset.filter.assert_called_once_with(acknowledged=False)
