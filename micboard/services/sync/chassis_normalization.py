"""Normalize a vendor's raw device payloads once, counting what could not be normalized."""

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from micboard.services.core.hardware import NormalizedChassis
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class ChassisNormalizer(Protocol):
    """The vendor operation ingest needs to read a raw device payload."""

    def normalize_device(self, api_data: dict[str, Any]) -> NormalizedChassis | None:
        """Normalize one raw device payload, or return None when it is unusable."""
        raise NotImplementedError


@dataclass(slots=True)
class NormalizedBatch:
    """The payloads a raw inventory normalized to, and how many devices did not."""

    payloads: list[NormalizedChassis] = field(default_factory=list)
    unnormalizable: int = 0


def normalize_batch(
    raw_devices: Iterable[Mapping[str, Any]], plugin: ChassisNormalizer
) -> NormalizedBatch:
    """Normalize every raw device once; a device that raises or yields nothing is counted.

    The device's identity is unknown when it cannot be normalized, so a caller reconciling
    absent chassis must treat any unnormalizable device as an incomplete inventory.
    """
    batch = NormalizedBatch()
    for position, raw in enumerate(raw_devices, start=1):
        try:
            payload = plugin.normalize_device(dict(raw))
        except Exception as exc:
            logger.exception(
                "Error normalizing vendor device at snapshot position %s",
                position,
                exc_info=sanitized_exception_info(exc),
            )
            payload = None
        if payload is None:
            batch.unnormalizable += 1
        else:
            batch.payloads.append(payload)
    return batch
