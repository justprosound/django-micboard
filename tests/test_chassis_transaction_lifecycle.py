"""Regression tests for chassis lifecycle delegation and commit boundaries."""

from __future__ import annotations

from unittest.mock import Mock, patch

from django.contrib import admin
from django.db import transaction
from django.test import RequestFactory

import pytest

from micboard.admin.receivers import WirelessChassisAdmin
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveryFQDN
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.core.hardware_post_save_hooks import HardwarePostSaveHooks
from tests.factories.hardware import WirelessChassisFactory


@pytest.mark.django_db
def test_admin_save_model_runs_chassis_save_hook_once() -> None:
    """Admin persistence must rely on the model lifecycle instead of replaying it."""
    chassis = WirelessChassisFactory()
    chassis.name = "Updated through admin"
    request = RequestFactory().post("/admin/micboard/wirelesschassis/")
    model_admin = WirelessChassisAdmin(WirelessChassis, admin.site)

    with patch.object(HardwarePostSaveHooks, "handle_chassis_save") as handle_save:
        model_admin.save_model(request, chassis, form=Mock(), change=True)

    handle_save.assert_called_once_with(
        chassis=chassis,
        created=False,
        using="default",
    )


@pytest.mark.django_db
def test_admin_delete_model_runs_chassis_delete_hook_once() -> None:
    """Admin deletion must rely on the model lifecycle instead of replaying it."""
    chassis = WirelessChassisFactory()
    chassis_pk = chassis.pk
    request = RequestFactory().post("/admin/micboard/wirelesschassis/delete/")
    model_admin = WirelessChassisAdmin(WirelessChassis, admin.site)

    with patch.object(HardwarePostSaveHooks, "handle_chassis_delete") as handle_delete:
        model_admin.delete_model(request, chassis)

    handle_delete.assert_called_once_with(chassis=chassis, using="default")
    assert not WirelessChassis.objects.filter(pk=chassis_pk).exists()


@pytest.mark.django_db
def test_admin_bulk_delete_registers_one_grouped_cleanup() -> None:
    """Bulk deletion must preserve the external cleanup contract without per-row hooks."""
    first = WirelessChassisFactory()
    second = WirelessChassisFactory(manufacturer=first.manufacturer)
    chassis_ids = {first.pk, second.pk}
    request = RequestFactory().post("/admin/micboard/wirelesschassis/")
    model_admin = WirelessChassisAdmin(WirelessChassis, admin.site)
    queryset_class = type(WirelessChassis._default_manager.all())
    select_for_update_method = queryset_class.select_for_update

    def assert_atomic_cleanup(
        *,
        chassis_list: list[WirelessChassis],
        using: str,
    ) -> None:
        assert transaction.get_connection().in_atomic_block
        assert {chassis.pk for chassis in chassis_list} == chassis_ids
        assert using == "default"

    with (
        patch.object(
            queryset_class,
            "select_for_update",
            autospec=True,
            side_effect=select_for_update_method,
        ) as select_for_update,
        patch.object(
            HardwarePostSaveHooks,
            "handle_chassis_bulk_delete",
            side_effect=assert_atomic_cleanup,
        ) as handle_bulk_delete,
    ):
        model_admin.delete_queryset(
            request,
            WirelessChassis.objects.filter(pk__in=chassis_ids),
        )

    select_for_update.assert_called_once()
    handle_bulk_delete.assert_called_once()
    cleanup_targets = handle_bulk_delete.call_args.kwargs["chassis_list"]
    assert {chassis.pk for chassis in cleanup_targets} == chassis_ids
    assert not WirelessChassis.objects.filter(pk__in=chassis_ids).exists()


@pytest.mark.django_db
def test_queryset_delete_groups_chassis_cleanup(django_capture_on_commit_callbacks) -> None:
    """Queryset deletion submits one cleanup batch instead of one callback per row."""
    first = WirelessChassisFactory()
    second = WirelessChassisFactory(manufacturer=first.manufacturer)

    with (
        patch.object(HardwarePostSaveHooks, "_remove_ips_from_discovery") as cleanup,
        django_capture_on_commit_callbacks(execute=True),
    ):
        WirelessChassis.objects.filter(pk__in=[first.pk, second.pk]).delete()

    cleanup.assert_called_once()
    assert {target.ip for target in cleanup.call_args.kwargs["targets"]} == {
        str(first.ip),
        str(second.ip),
    }


@pytest.mark.django_db
def test_manufacturer_cascade_skips_obsolete_discovery_cleanup() -> None:
    """Deleting a vendor cannot enqueue scans or cleanups for its deleted children."""
    first = WirelessChassisFactory()
    WirelessChassisFactory(manufacturer=first.manufacturer)
    DiscoveryFQDN.objects.create(
        manufacturer=first.manufacturer,
        fqdn="cascade.invalid",
    )

    with (
        patch.object(HardwarePostSaveHooks, "handle_chassis_delete") as chassis_cleanup,
        patch("micboard.model_lifecycle._schedule_manufacturer_discovery") as schedule_discovery,
    ):
        Manufacturer.objects.filter(pk=first.manufacturer_id).delete()

    chassis_cleanup.assert_not_called()
    schedule_discovery.assert_not_called()


@pytest.mark.django_db
def test_queryset_fqdn_delete_deduplicates_discovery(
    django_capture_on_commit_callbacks,
) -> None:
    manufacturer = WirelessChassisFactory().manufacturer
    DiscoveryFQDN.objects.bulk_create(
        [
            DiscoveryFQDN(manufacturer=manufacturer, fqdn="one.invalid"),
            DiscoveryFQDN(manufacturer=manufacturer, fqdn="two.invalid"),
        ]
    )

    with (
        patch("micboard.model_lifecycle._dispatch_manufacturer_discovery") as dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        DiscoveryFQDN.objects.filter(manufacturer=manufacturer).delete()

    dispatch.assert_called_once_with(
        manufacturer_id=manufacturer.pk,
        scan_cidrs=True,
        scan_fqdns=True,
    )


@pytest.mark.django_db(transaction=True)
def test_deferred_status_broadcast_runs_after_commit() -> None:
    """A deferred status event must not escape its transaction before commit."""
    chassis = WirelessChassisFactory(status="discovered")

    with patch(
        "micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_status"
    ) as broadcast:
        with transaction.atomic():
            chassis.status = "provisioning"
            chassis.save()

            broadcast.assert_not_called()

        broadcast.assert_called_once_with(
            service_code=chassis.manufacturer.code,
            device_id=chassis.pk,
            device_type="WirelessChassis",
            status="provisioning",
            is_active=False,
        )


@pytest.mark.django_db(transaction=True)
def test_deferred_status_broadcast_is_discarded_on_rollback() -> None:
    """A rolled-back status event must never reach realtime consumers."""
    chassis = WirelessChassisFactory(status="discovered")

    with patch(
        "micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_status"
    ) as broadcast:
        with transaction.atomic():
            chassis.status = "provisioning"
            chassis.save()
            transaction.set_rollback(True)

        broadcast.assert_not_called()

    chassis.refresh_from_db()
    assert chassis.status == "discovered"


@pytest.mark.django_db(transaction=True)
def test_deferred_status_broadcast_uses_final_committed_state() -> None:
    """Repeated saves in one transaction emit one event for the final state."""
    chassis = WirelessChassisFactory(status="discovered")

    with patch(
        "micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_status"
    ) as broadcast:
        with transaction.atomic():
            chassis.status = "provisioning"
            chassis.save()
            chassis.status = "online"
            chassis.save()

            broadcast.assert_not_called()

        broadcast.assert_called_once_with(
            service_code=chassis.manufacturer.code,
            device_id=chassis.pk,
            device_type="WirelessChassis",
            status="online",
            is_active=True,
        )


@pytest.mark.django_db(transaction=True)
def test_rolled_back_savepoint_does_not_suppress_later_status_broadcast() -> None:
    """A discarded callback marker cannot hide a later committed status event."""
    chassis = WirelessChassisFactory(status="discovered")

    with patch(
        "micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_status"
    ) as broadcast:
        with transaction.atomic():
            try:
                with transaction.atomic():
                    chassis.status = "provisioning"
                    chassis.save()
                    raise RuntimeError("discard inner write")
            except RuntimeError as exc:
                assert str(exc) == "discard inner write"

            chassis.refresh_from_db()
            chassis.status = "provisioning"
            chassis.save()

        broadcast.assert_called_once_with(
            service_code=chassis.manufacturer.code,
            device_id=chassis.pk,
            device_type="WirelessChassis",
            status="provisioning",
            is_active=False,
        )


@pytest.mark.django_db(transaction=True)
def test_deferred_status_broadcast_skips_deleted_chassis() -> None:
    """A status event must not describe a row deleted before commit."""
    chassis = WirelessChassisFactory(status="discovered")

    with patch(
        "micboard.services.notification.broadcast_service.BroadcastService.broadcast_device_status"
    ) as broadcast:
        with transaction.atomic():
            chassis.status = "provisioning"
            chassis.save()
            chassis.delete()

        broadcast.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_deferred_external_save_hooks_run_after_commit() -> None:
    """Manufacturer and task effects must wait for durable persistence."""
    chassis = WirelessChassisFactory()

    with patch.object(HardwarePostSaveHooks, "_run_external_save_hooks") as run_hooks:
        with transaction.atomic():
            chassis.name = "Committed chassis name"
            chassis.save()

            run_hooks.assert_not_called()

        run_hooks.assert_called_once_with(
            chassis_id=chassis.pk,
            created=False,
            using="default",
        )


@pytest.mark.django_db(transaction=True)
def test_deferred_external_save_hooks_are_discarded_on_rollback() -> None:
    """Manufacturer and task effects must not run for rolled-back writes."""
    chassis = WirelessChassisFactory()
    original_name = chassis.name

    with patch.object(HardwarePostSaveHooks, "_run_external_save_hooks") as run_hooks:
        with transaction.atomic():
            chassis.name = "Rolled-back chassis name"
            chassis.save()
            transaction.set_rollback(True)

        run_hooks.assert_not_called()

    chassis.refresh_from_db()
    assert chassis.name == original_name


@pytest.mark.django_db(transaction=True)
def test_delete_cleanup_runs_after_commit() -> None:
    """Manufacturer cleanup must observe a durable chassis deletion."""
    chassis = WirelessChassisFactory()

    with patch.object(HardwarePostSaveHooks, "_remove_ips_from_discovery") as cleanup:
        with transaction.atomic():
            chassis.delete()

            cleanup.assert_not_called()

        cleanup.assert_called_once()
        targets = cleanup.call_args.kwargs["targets"]
        assert len(targets) == 1
        assert targets[0].ip == str(chassis.ip)
        assert cleanup.call_args.kwargs["using"] == "default"


@pytest.mark.django_db(transaction=True)
def test_delete_cleanup_is_discarded_on_rollback() -> None:
    """Manufacturer cleanup must not run when chassis deletion rolls back."""
    chassis = WirelessChassisFactory()
    chassis_pk = chassis.pk

    with patch.object(HardwarePostSaveHooks, "_remove_ips_from_discovery") as cleanup:
        with transaction.atomic():
            chassis.delete()
            transaction.set_rollback(True)

        cleanup.assert_not_called()

    assert WirelessChassis.objects.filter(pk=chassis_pk).exists()
