"""Cross-model hardware IP ownership regressions."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from django.core.exceptions import ValidationError
from django.db import connection

import pytest

from micboard.services.hardware.ip_ownership_service import HardwareIPOwnershipService
from tests.factories.hardware import ChargerFactory, WirelessChassisFactory

pytestmark = pytest.mark.django_db


def test_charger_rejects_ip_owned_by_chassis() -> None:
    """A charger cannot claim an address already owned by a chassis."""
    chassis = WirelessChassisFactory(ip="192.0.2.201")

    with pytest.raises(ValidationError, match="wireless chassis"):
        ChargerFactory(ip=chassis.ip)


def test_chassis_rejects_ip_owned_by_charger() -> None:
    """A chassis cannot claim an address already owned by a charger."""
    charger = ChargerFactory(ip="192.0.2.202")

    with pytest.raises(ValidationError, match="charger"):
        WirelessChassisFactory(ip=charger.ip)


def test_nullable_charger_ip_remains_supported() -> None:
    """Chargers without network management do not acquire an address claim."""
    charger = ChargerFactory(ip=None)

    charger.name = "Offline charger"
    charger.save(update_fields=["name", "updated_at"])

    charger.refresh_from_db()
    assert charger.ip is None
    assert charger.name == "Offline charger"


def test_postgresql_claim_uses_transaction_scoped_advisory_lock() -> None:
    """PostgreSQL claims use one deterministic transaction-level lock."""
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor

    with (
        patch.object(connection, "vendor", "postgresql"),
        patch.object(connection, "cursor", return_value=cursor),
    ):
        HardwareIPOwnershipService._lock_address(ip="192.0.2.203", using="default")

    cursor.execute.assert_called_once_with(
        "SELECT pg_advisory_xact_lock(%s)",
        [HardwareIPOwnershipService._advisory_lock_key("192.0.2.203")],
    )


def test_batch_claim_locks_unique_canonical_addresses_in_stable_order() -> None:
    """Batch claims canonicalize, deduplicate, and sort before locking."""
    with patch.object(HardwareIPOwnershipService, "_lock_address") as lock_address:
        HardwareIPOwnershipService.lock_addresses(
            ["192.0.2.210", "192.0.2.2", "192.0.2.210", None, ""],
            using="default",
        )

    assert lock_address.call_args_list == [
        call(ip="192.0.2.2", using="default"),
        call(ip="192.0.2.210", using="default"),
    ]
