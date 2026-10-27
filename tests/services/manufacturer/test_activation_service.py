"""Activation lookup contract for work queued against one manufacturer."""

import pytest

from micboard.services.manufacturer.activation_service import ManufacturerActivationService
from tests.factories.discovery import ManufacturerFactory


@pytest.mark.django_db
def test_get_active_returns_the_active_manufacturer() -> None:
    manufacturer = ManufacturerFactory(is_active=True)

    assert ManufacturerActivationService.get_active(manufacturer.pk) == manufacturer


@pytest.mark.django_db
def test_get_active_returns_none_for_an_inactive_manufacturer() -> None:
    manufacturer = ManufacturerFactory(is_active=False)

    assert ManufacturerActivationService.get_active(manufacturer.pk) is None


@pytest.mark.django_db
def test_get_active_returns_none_for_a_missing_manufacturer() -> None:
    assert ManufacturerActivationService.get_active(0) is None
