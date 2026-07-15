"""Typed data transferred through discovery synchronization services."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from micboard.discovery.limits import MAX_DISCOVERY_CANDIDATES
from micboard.services.shared.base_dto import PydanticBaseDTO


class DiscoverySyncSummary(PydanticBaseDTO):
    """Mutable progress and outcome for one manufacturer synchronization."""

    manufacturer: int
    status: Literal["running", "success", "failed"] = "running"
    created_receivers: int = 0
    missing_ips_submitted: int = 0
    scanned_ips_submitted: int = 0
    errors: list[str] = Field(default_factory=list)

    def record_error(self, message: str) -> None:
        """Record a failure and make the summary terminally unsuccessful."""
        self.errors.append(message)
        self.status = "failed"


class DiscoveryCandidateSubmission(PydanticBaseDTO):
    """Outcome of one vendor discovery-list batch submission."""

    submitted_ips: list[str] = Field(default_factory=list)
    failed_ips: list[str] = Field(default_factory=list)
    rejected_count: int = 0


class DiscoverySourcePage(PydanticBaseDTO):
    """One bounded circular page from a single local discovery source."""

    values: list[str] = Field(default_factory=list, max_length=MAX_DISCOVERY_CANDIDATES)
    sources_complete: bool = True


class DiscoveryCandidatePage(PydanticBaseDTO):
    """One aggregate bounded page of local discovery candidates."""

    candidates: list[str] = Field(default_factory=list, max_length=MAX_DISCOVERY_CANDIDATES)
    sources_complete: bool = True


class DiscoveryScanSourcePage(PydanticBaseDTO):
    """One aggregate bounded page of configured network scan sources."""

    cidrs: list[str] = Field(default_factory=list, max_length=MAX_DISCOVERY_CANDIDATES)
    fqdns: list[str] = Field(default_factory=list, max_length=MAX_DISCOVERY_CANDIDATES)
    source_order: list[Literal["cidrs", "fqdns"]] = Field(default_factory=list, max_length=2)
    sources_complete: bool = True


class DiscoveryQueueDevice(PydanticBaseDTO):
    """Database-safe normalized discovery queue payload."""

    api_device_id: str = Field(max_length=100)
    device_type: str = Field(max_length=20)
    firmware_version: str = Field(max_length=50)
    fqdn: str = Field(max_length=255)
    ip: str = Field(max_length=45)
    metadata: dict[str, Any]
    model: str = Field(max_length=50)
    name: str = Field(max_length=100)
    serial_number: str = Field(min_length=1, max_length=100)


class DiscoverySourceReconciliation(PydanticBaseDTO):
    """Completeness and write outcome for one vendor discovery reconciliation."""

    manufacturer: int
    success: bool
    sources_complete: bool
    remote_source_complete: bool
    additions_succeeded: bool
    removals_succeeded: bool


class DiscoveredDeviceDeletionResult(PydanticBaseDTO):
    """Outcome of deleting staged devices and scheduling remote reconciliation."""

    deleted_count: int = 0
    scheduled_manufacturers: int = 0


class DiscoveryReconciliationResult(PydanticBaseDTO):
    """Stable outcome returned by one claimed vendor reconciliation."""

    manufacturer: int
    status: Literal["success", "busy", "failed"]
    reason: str = ""
