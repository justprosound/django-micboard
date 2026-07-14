"""Django signal adapters for model persistence lifecycle behavior.

Models stay responsible for persistence. These adapters translate Django's
pre/post-save events into service-layer calls and task-layer dispatches.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import partial
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save

logger = logging.getLogger(__name__)

_CHASSIS_CONTEXT = "_micboard_chassis_save_context"
_CHANNEL_CONTEXT = "_micboard_channel_save_context"
_MANUFACTURER_CONTEXT = "_micboard_manufacturer_save_context"
_UNIT_CONTEXT = "_micboard_unit_save_context"
_chassis_delete_hooks_enabled: ContextVar[bool] = ContextVar(
    "micboard_chassis_delete_hooks_enabled", default=True
)


def _remember_context(instance: Any, name: str, context: dict[str, Any]) -> None:
    setattr(instance, name, context)


def _take_context(instance: Any, name: str) -> dict[str, Any]:
    context = getattr(instance, name, {})
    if hasattr(instance, name):
        delattr(instance, name)
    return context


def _originates_from_model(origin: Any, model: type[Any]) -> bool:
    """Return whether a delete originated from an instance/queryset of ``model``."""
    return origin is not None and getattr(origin, "model", type(origin)) is model


def _persist_derived_fields(
    instance: Any,
    context: dict[str, Any],
    *,
    using: str,
    update_fields: frozenset[str] | None,
) -> None:
    """Persist lifecycle fields omitted by a caller's partial update."""
    if update_fields is None or instance.pk is None:
        return
    derived_fields = set(context.get("update_fields", ())) - set(update_fields)
    if not derived_fields:
        return
    values = {field: getattr(instance, field) for field in derived_fields}
    type(instance)._base_manager.using(using).filter(pk=instance.pk).update(**values)


def _prepare_chassis(sender: type[Any], instance: Any, using: str, **kwargs: Any) -> None:
    if kwargs.get("raw", False):
        return
    from micboard.services.hardware.ip_ownership_service import HardwareIPOwnershipService
    from micboard.services.hardware.wireless_chassis_service import prepare_chassis_for_save

    HardwareIPOwnershipService.validate_for_instance(instance=instance, using=using)
    _remember_context(
        instance,
        _CHASSIS_CONTEXT,
        prepare_chassis_for_save(instance, using=using),
    )


def _finish_chassis(
    sender: type[Any],
    instance: Any,
    created: bool,
    using: str,
    update_fields: frozenset[str] | None,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw", False):
        return
    from micboard.services.core.hardware_post_save_hooks import HardwarePostSaveHooks
    from micboard.services.hardware.wireless_chassis_service import finalize_chassis_save

    context = _take_context(instance, _CHASSIS_CONTEXT)
    _persist_derived_fields(instance, context, using=using, update_fields=update_fields)
    finalize_chassis_save(instance, context, using=using)
    HardwarePostSaveHooks.handle_chassis_save(
        chassis=instance,
        created=created,
        using=using,
    )
    transaction.on_commit(
        partial(_dispatch_chassis_discovery, chassis_id=instance.pk, using=using),
        using=using,
        robust=True,
    )


def _dispatch_chassis_discovery(*, chassis_id: int, using: str) -> None:
    if getattr(settings, "TESTING", False):
        return
    try:
        from micboard.tasks.sync.discovery import sync_receiver_discovery
        from micboard.utils.dependencies import enqueue_huey_task, huey_is_configured

        if huey_is_configured():
            enqueue_huey_task(sync_receiver_discovery, chassis_id, using=using)
        else:
            logger.debug("Native Huey is unavailable or unconfigured; skipping chassis discovery")
    except Exception:
        logger.exception("Failed to schedule discovery for chassis %s", chassis_id)


def _delete_chassis(sender: type[Any], instance: Any, using: str, **kwargs: Any) -> None:
    if not _chassis_delete_hooks_enabled.get():
        return
    from micboard.models.discovery.manufacturer import Manufacturer

    if _originates_from_model(kwargs.get("origin"), Manufacturer):
        return
    from micboard.services.core.hardware_post_save_hooks import HardwarePostSaveHooks

    HardwarePostSaveHooks.handle_chassis_delete(chassis=instance, using=using)


@contextmanager
def suppress_chassis_delete_hooks() -> Iterator[None]:
    """Suppress per-row cleanup while an adapter registers grouped cleanup."""
    token = _chassis_delete_hooks_enabled.set(False)
    try:
        yield
    finally:
        _chassis_delete_hooks_enabled.reset(token)


def _prepare_charger(sender: type[Any], instance: Any, using: str, **kwargs: Any) -> None:
    if kwargs.get("raw", False):
        return
    from micboard.services.hardware.ip_ownership_service import HardwareIPOwnershipService

    HardwareIPOwnershipService.validate_for_instance(instance=instance, using=using)


def _prepare_unit(sender: type[Any], instance: Any, **kwargs: Any) -> None:
    if kwargs.get("raw", False):
        return
    from micboard.services.hardware.wireless_unit_service import prepare_unit_for_save

    _remember_context(instance, _UNIT_CONTEXT, prepare_unit_for_save(instance))


def _finish_unit(
    sender: type[Any],
    instance: Any,
    using: str,
    update_fields: frozenset[str] | None,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw", False):
        return
    from micboard.services.hardware.wireless_unit_service import finalize_unit_save

    context = _take_context(instance, _UNIT_CONTEXT)
    _persist_derived_fields(instance, context, using=using, update_fields=update_fields)
    finalize_unit_save(instance, context)


def _prepare_channel(sender: type[Any], instance: Any, **kwargs: Any) -> None:
    if kwargs.get("raw", False):
        return
    from micboard.services.hardware.rf_channel_service import prepare_channel_for_save

    _remember_context(instance, _CHANNEL_CONTEXT, prepare_channel_for_save(instance))


def _finish_channel(
    sender: type[Any],
    instance: Any,
    using: str,
    update_fields: frozenset[str] | None,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw", False):
        return
    from micboard.services.hardware.rf_channel_service import finalize_channel_save

    context = _take_context(instance, _CHANNEL_CONTEXT)
    _persist_derived_fields(instance, context, using=using, update_fields=update_fields)
    finalize_channel_save(instance, context)


def _prepare_building(sender: type[Any], instance: Any, **kwargs: Any) -> None:
    if kwargs.get("raw", False):
        return
    from micboard.services.locations.structure_service import prepare_building

    prepare_building(instance)


def _prepare_manufacturer(
    sender: type[Any],
    instance: Any,
    using: str,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw", False):
        return
    created = instance._state.adding
    old_active = False
    if not created:
        old_active = (
            sender._default_manager.using(using)
            .filter(pk=instance.pk)
            .values_list("is_active", flat=True)
            .first()
        )
    _remember_context(
        instance,
        _MANUFACTURER_CONTEXT,
        {"created": created, "old_active": old_active},
    )


def _finish_manufacturer(
    sender: type[Any],
    instance: Any,
    created: bool,
    using: str,
    **kwargs: Any,
) -> None:
    if kwargs.get("raw", False):
        return
    from micboard.services.manufacturer.signals import handle_manufacturer_save

    context = _take_context(instance, _MANUFACTURER_CONTEXT)
    should_discover = handle_manufacturer_save(
        manufacturer=instance,
        created=created,
        old_active=context.get("old_active", False),
    )
    if should_discover:
        _schedule_manufacturer_discovery(
            manufacturer_id=instance.pk,
            scan_cidrs=False,
            scan_fqdns=False,
            using=using,
        )


def _delete_manufacturer(sender: type[Any], instance: Any, **kwargs: Any) -> None:
    from micboard.services.manufacturer.signals import handle_manufacturer_delete

    handle_manufacturer_delete(manufacturer=instance)


def _schedule_manufacturer_discovery(
    *,
    manufacturer_id: int,
    scan_cidrs: bool,
    scan_fqdns: bool,
    using: str,
) -> None:
    connection = transaction.get_connection(using)
    savepoints = set(connection.savepoint_ids)
    discovery_key = (manufacturer_id, scan_cidrs, scan_fqdns)
    if any(
        callback_savepoints == savepoints
        and getattr(callback, "_micboard_discovery_key", None) == discovery_key
        for callback_savepoints, callback, _robust in connection.run_on_commit
    ):
        return

    callback = partial(
        _dispatch_manufacturer_discovery,
        manufacturer_id=manufacturer_id,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
    )
    callback.__dict__["_micboard_discovery_key"] = discovery_key
    transaction.on_commit(callback, using=using, robust=True)


def _dispatch_manufacturer_discovery(
    *, manufacturer_id: int, scan_cidrs: bool, scan_fqdns: bool
) -> None:
    from micboard.tasks.sync.discovery import dispatch_manufacturer_discovery

    dispatch_manufacturer_discovery(
        manufacturer_id,
        scan_cidrs=scan_cidrs,
        scan_fqdns=scan_fqdns,
    )


def _config_saved(sender: type[Any], instance: Any, using: str, **kwargs: Any) -> None:
    if kwargs.get("raw", False):
        return
    from micboard.services.discovery.registry_service import discovery_manufacturer_for_config

    if manufacturer_id := discovery_manufacturer_for_config(instance):
        _schedule_manufacturer_discovery(
            manufacturer_id=manufacturer_id,
            scan_cidrs=True,
            scan_fqdns=True,
            using=using,
        )


def _registry_entry_changed(sender: type[Any], instance: Any, using: str, **kwargs: Any) -> None:
    if kwargs.get("raw", False):
        return
    from micboard.models.discovery.manufacturer import Manufacturer

    if _originates_from_model(kwargs.get("origin"), Manufacturer):
        return
    from micboard.services.discovery.registry_service import discovery_manufacturer_for_entry

    if manufacturer_id := discovery_manufacturer_for_entry(instance):
        _schedule_manufacturer_discovery(
            manufacturer_id=manufacturer_id,
            scan_cidrs=True,
            scan_fqdns=True,
            using=using,
        )


def register_model_lifecycle() -> None:
    """Connect all model lifecycle adapters exactly once."""
    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.models.discovery.registry import DiscoveryCIDR, DiscoveryFQDN, MicboardConfig
    from micboard.models.hardware.charger import Charger
    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.models.hardware.wireless_unit import WirelessUnit
    from micboard.models.locations.structure import Building
    from micboard.models.rf_coordination.rf_channel import RFChannel

    connections = (
        (pre_save, _prepare_chassis, WirelessChassis, "micboard.prepare_chassis"),
        (post_save, _finish_chassis, WirelessChassis, "micboard.finish_chassis"),
        (pre_delete, _delete_chassis, WirelessChassis, "micboard.delete_chassis"),
        (pre_save, _prepare_charger, Charger, "micboard.prepare_charger"),
        (pre_save, _prepare_unit, WirelessUnit, "micboard.prepare_unit"),
        (post_save, _finish_unit, WirelessUnit, "micboard.finish_unit"),
        (pre_save, _prepare_channel, RFChannel, "micboard.prepare_channel"),
        (post_save, _finish_channel, RFChannel, "micboard.finish_channel"),
        (pre_save, _prepare_building, Building, "micboard.prepare_building"),
        (pre_save, _prepare_manufacturer, Manufacturer, "micboard.prepare_manufacturer"),
        (post_save, _finish_manufacturer, Manufacturer, "micboard.finish_manufacturer"),
        (post_delete, _delete_manufacturer, Manufacturer, "micboard.delete_manufacturer"),
        (post_save, _config_saved, MicboardConfig, "micboard.config_saved"),
        (post_save, _registry_entry_changed, DiscoveryCIDR, "micboard.cidr_saved"),
        (post_save, _registry_entry_changed, DiscoveryFQDN, "micboard.fqdn_saved"),
        (post_delete, _registry_entry_changed, DiscoveryFQDN, "micboard.fqdn_deleted"),
    )
    for signal, receiver, sender, dispatch_uid in connections:
        signal.connect(receiver, sender=sender, dispatch_uid=dispatch_uid, weak=False)
