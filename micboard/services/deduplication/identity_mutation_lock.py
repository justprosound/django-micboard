"""Database-backed serialization for device identity mutations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import transaction

from micboard.models.discovery.manufacturer import Manufacturer


class DeviceIdentityMutationLockService:
    """Serialize global chassis identity reads and writes without a lock model."""

    @staticmethod
    @contextmanager
    def acquire(*, manufacturer: Manufacturer) -> Iterator[Manufacturer]:
        """Lock the shared sentinel first, then yield a fresh locked manufacturer."""
        with transaction.atomic():
            sentinel = Manufacturer.objects.select_for_update().only("pk").order_by("pk").first()
            if sentinel is None:
                raise Manufacturer.DoesNotExist("Device identity mutation lock is unavailable")

            locked_manufacturer = Manufacturer.objects.select_for_update().get(pk=manufacturer.pk)
            yield locked_manufacturer
