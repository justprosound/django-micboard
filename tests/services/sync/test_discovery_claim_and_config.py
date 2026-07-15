"""Discovery claim leasing and persisted vendor configuration contracts."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.utils import timezone

import pytest

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES
from micboard.models.discovery.registry import (
    DiscoveryCIDR,
    DiscoveryFQDN,
    DiscoveryJob,
    MicboardConfig,
)
from micboard.services.sync.discovery_claim_service import (
    DISCOVERY_SYNC_LEASE_SECONDS,
    STALE_DISCOVERY_NOTE,
    DiscoverySyncClaimService,
)
from micboard.services.sync.discovery_configuration_service import (
    SUPPORTED_MODELS_CONFIG_KEY,
    DiscoveryConfigurationService,
)
from micboard.services.sync.discovery_sync_service import CLAIM_FAILURE_REASON, DiscoverySyncService
from tests.factories.discovery import DiscoveryJobFactory, ManufacturerFactory

pytestmark = pytest.mark.django_db


def test_claim_expires_stale_job_before_creating_new_owner() -> None:
    manufacturer = ManufacturerFactory()
    stale_job = DiscoveryJobFactory(
        manufacturer=manufacturer,
        status="running",
        started_at=timezone.now() - timedelta(seconds=DISCOVERY_SYNC_LEASE_SECONDS + 1),
    )

    claim = DiscoverySyncClaimService.claim(manufacturer.pk)

    assert claim is not None
    claimed_manufacturer, claimed_job = claim
    stale_job.refresh_from_db()
    assert claimed_manufacturer == manufacturer
    assert claimed_job.status == "running"
    assert claimed_job.pk != stale_job.pk
    assert stale_job.status == "failed"
    assert stale_job.finished_at is not None
    assert stale_job.note == STALE_DISCOVERY_NOTE


def test_claim_rejects_inactive_manufacturer() -> None:
    """Queued discovery cannot acquire a new claim after a manufacturer is disabled."""
    manufacturer = ManufacturerFactory(is_active=False)

    with pytest.raises(type(manufacturer).DoesNotExist):
        DiscoverySyncClaimService.claim(manufacturer.pk)

    assert not DiscoveryJob.objects.exists()


def test_claim_rolls_back_stale_expiration_when_new_job_creation_fails() -> None:
    manufacturer = ManufacturerFactory()
    stale_job = DiscoveryJobFactory(
        manufacturer=manufacturer,
        status="running",
        started_at=timezone.now() - timedelta(seconds=DISCOVERY_SYNC_LEASE_SECONDS + 1),
    )

    with patch(
        "micboard.services.sync.discovery_claim_service.DiscoveryJob.objects.create",
        side_effect=RuntimeError("database unavailable"),
    ):
        result = DiscoverySyncService().run(manufacturer.pk)

    stale_job.refresh_from_db()
    assert result["errors"] == [CLAIM_FAILURE_REASON]
    assert stale_job.status == "running"
    assert stale_job.finished_at is None
    assert stale_job.note == ""


def test_add_config_entries_persists_truthy_values_and_contains_bad_rows() -> None:
    manufacturer = ManufacturerFactory()
    cidr_create = Mock(return_value=(object(), True))
    fqdn_create = Mock(return_value=(object(), True))
    with (
        patch(
            "micboard.services.sync.discovery_configuration_service."
            "DiscoveryCIDR.objects.get_or_create",
            cidr_create,
        ),
        patch(
            "micboard.services.sync.discovery_configuration_service."
            "DiscoveryFQDN.objects.get_or_create",
            fqdn_create,
        ),
    ):
        result = DiscoveryConfigurationService.add_entries(
            manufacturer,
            cidrs=["192.0.2.0/24", "invalid"],
            fqdns=["one.example.test", "", "bad host"],
        )

    cidr_create.assert_called_once_with(
        manufacturer=manufacturer,
        cidr="192.0.2.0/24",
    )
    fqdn_create.assert_called_once_with(
        manufacturer=manufacturer,
        fqdn="one.example.test",
    )
    assert result is False


def test_add_config_entries_canonicalizes_and_rejects_invalid_values() -> None:
    manufacturer = ManufacturerFactory()

    result = DiscoveryConfigurationService.add_entries(
        manufacturer,
        cidrs=["192.0.2.17/24", "invalid\nnetwork"],
        fqdns=["Receiver.Example.Test.", "bad host\nforged"],
    )

    assert list(
        DiscoveryCIDR.objects.filter(manufacturer=manufacturer).values_list("cidr", flat=True)
    ) == ["192.0.2.0/24"]
    assert list(
        DiscoveryFQDN.objects.filter(manufacturer=manufacturer).values_list("fqdn", flat=True)
    ) == ["receiver.example.test"]
    assert result is False


def test_add_config_entries_accepts_absent_lists() -> None:
    manufacturer = ManufacturerFactory()
    with (
        patch(
            "micboard.services.sync.discovery_configuration_service."
            "DiscoveryCIDR.objects.get_or_create"
        ) as cidr_create,
        patch(
            "micboard.services.sync.discovery_configuration_service."
            "DiscoveryFQDN.objects.get_or_create"
        ) as fqdn_create,
    ):
        result = DiscoveryConfigurationService.add_entries(manufacturer, cidrs=None, fqdns=None)

    cidr_create.assert_not_called()
    fqdn_create.assert_not_called()
    assert result is True


def test_add_config_entries_bounds_arbitrary_inputs_before_persistence() -> None:
    manufacturer = ManufacturerFactory()
    consumed = 0

    def cidrs():
        nonlocal consumed
        for index in range(MAX_DISCOVERY_CANDIDATES + 2):
            consumed += 1
            yield f"10.{index // 256}.{index % 256}.0/24"

    with patch(
        "micboard.services.sync.discovery_configuration_service.DiscoveryCIDR.objects.get_or_create"
    ) as create:
        result = DiscoveryConfigurationService.add_entries(
            manufacturer,
            cidrs=cidrs(),
            fqdns=None,
        )

    assert result is False
    assert consumed == MAX_DISCOVERY_CANDIDATES + 1
    assert create.call_count == MAX_DISCOVERY_CANDIDATES


def test_persist_supported_models_skips_unavailable_or_empty_capability() -> None:
    manufacturer = ManufacturerFactory()
    assert DiscoveryConfigurationService.persist_supported_models(manufacturer, None) is True
    assert DiscoveryConfigurationService.persist_supported_models(manufacturer, object()) is True

    empty_client = SimpleNamespace(get_supported_device_models=Mock(return_value=[]))
    assert (
        DiscoveryConfigurationService.persist_supported_models(manufacturer, empty_client) is True
    )

    failing_client = SimpleNamespace(
        get_supported_device_models=Mock(side_effect=RuntimeError("endpoint unavailable"))
    )
    assert (
        DiscoveryConfigurationService.persist_supported_models(manufacturer, failing_client)
        is False
    )

    assert not MicboardConfig.objects.exists()


def test_persist_supported_models_creates_and_updates_vendor_neutral_snapshot() -> None:
    manufacturer = ManufacturerFactory()
    first_client = SimpleNamespace(
        get_supported_device_models=Mock(return_value=("ULXD4Q", "SBC250"))
    )
    second_client = SimpleNamespace(
        get_supported_device_models=Mock(return_value=["AD4Q", "SBC250"])
    )

    DiscoveryConfigurationService.persist_supported_models(manufacturer, first_client)
    DiscoveryConfigurationService.persist_supported_models(manufacturer, second_client)

    config = MicboardConfig.objects.get(
        manufacturer=manufacturer,
        key=SUPPORTED_MODELS_CONFIG_KEY,
    )
    assert config.value == '["AD4Q", "SBC250"]'


def test_persist_supported_models_contains_database_failure() -> None:
    manufacturer = ManufacturerFactory()
    client = SimpleNamespace(get_supported_device_models=Mock(return_value=["model"]))
    with patch(
        "micboard.services.sync.discovery_configuration_service."
        "MicboardConfig.objects.get_or_create",
        side_effect=RuntimeError("database unavailable"),
    ):
        assert DiscoveryConfigurationService.persist_supported_models(manufacturer, client) is False


def test_persist_supported_models_bounds_vendor_generator_before_serialization() -> None:
    manufacturer = ManufacturerFactory()
    consumed = 0

    def supported_models():
        nonlocal consumed
        for index in range(MAX_DISCOVERY_CANDIDATES + 2):
            consumed += 1
            yield f"model-{index}"

    client = SimpleNamespace(get_supported_device_models=Mock(return_value=supported_models()))

    assert DiscoveryConfigurationService.persist_supported_models(manufacturer, client) is False
    assert consumed == MAX_DISCOVERY_CANDIDATES + 1
    assert not MicboardConfig.objects.exists()
