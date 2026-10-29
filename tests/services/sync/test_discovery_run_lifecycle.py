"""Behavioral coverage for the shared claimed-run lifecycle."""

from types import SimpleNamespace

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.sync.discovery_dtos import DiscoverySyncSummary
from micboard.services.sync.discovery_run_lifecycle import (
    MANUFACTURER_INACTIVE_REASON,
    MANUFACTURER_STATUS_CHECK_FAILURE_REASON,
    ClaimedRunStatus,
    DiscoveryClaimedRun,
)
from tests.factories.discovery import ManufacturerFactory

pytestmark = pytest.mark.django_db

WORK_FAILURE = "work_failed"


class FakeClaims:
    """Claim service double whose claim and finalize behaviour is set per test."""

    def __init__(self, *, claim=None, claim_error=None, finalized=True, finalize_error=None):
        self._claim = claim
        self._claim_error = claim_error
        self._finalized = finalized
        self._finalize_error = finalize_error
        self.finalized_with: list[DiscoverySyncSummary] = []

    def claim(self, manufacturer_id: int):
        if self._claim_error is not None:
            raise self._claim_error
        return self._claim

    def finalize(self, job, summary: DiscoverySyncSummary) -> bool:
        if self._finalize_error is not None:
            raise self._finalize_error
        self.finalized_with.append(summary)
        return self._finalized


@pytest.fixture
def active(monkeypatch) -> None:
    monkeypatch.setattr(
        "micboard.services.sync.discovery_run_lifecycle.ManufacturerActivationService.is_active",
        lambda manufacturer_id: True,
    )


def _run(claims: FakeClaims, work=None):
    calls: list[int] = []

    def default_work(manufacturer, summary) -> None:
        calls.append(manufacturer.pk)

    outcome = DiscoveryClaimedRun(claims).run(
        7,
        operation="discovery test",
        work=work or default_work,
        work_failure_reason=WORK_FAILURE,
    )
    return outcome, calls


def _claimed() -> FakeClaims:
    return FakeClaims(claim=(ManufacturerFactory.build(pk=7), SimpleNamespace(pk=1)))


@pytest.mark.parametrize(
    ("claims", "status"),
    [
        (FakeClaims(claim_error=Manufacturer.DoesNotExist()), ClaimedRunStatus.NOT_FOUND),
        (FakeClaims(claim_error=RuntimeError("db")), ClaimedRunStatus.CLAIM_FAILED),
        (FakeClaims(claim=None), ClaimedRunStatus.BUSY),
    ],
)
def test_unclaimed_runs_never_start_work(claims: FakeClaims, status: ClaimedRunStatus) -> None:
    outcome, calls = _run(claims)

    assert outcome.status is status
    assert calls == []
    assert outcome.summary.errors == []
    assert claims.finalized_with == []


@pytest.mark.usefixtures("active")
def test_successful_work_is_finalized() -> None:
    claims = _claimed()

    outcome, calls = _run(claims)

    assert outcome.status is ClaimedRunStatus.FINALIZED
    assert outcome.work_completed
    assert calls == [7]
    assert claims.finalized_with == [outcome.summary]


@pytest.mark.usefixtures("active")
def test_work_exception_is_contained_and_finalized_as_failure() -> None:
    claims = _claimed()

    def failing(manufacturer, summary) -> None:
        raise RuntimeError("vendor down")

    outcome, _ = _run(claims, failing)

    assert outcome.status is ClaimedRunStatus.FINALIZED
    assert not outcome.work_completed
    assert outcome.summary.errors == [WORK_FAILURE]
    assert claims.finalized_with == [outcome.summary]


@pytest.mark.parametrize(
    ("is_active", "reason"),
    [
        (lambda manufacturer_id: False, MANUFACTURER_INACTIVE_REASON),
        (lambda manufacturer_id: 1 / 0, MANUFACTURER_STATUS_CHECK_FAILURE_REASON),
    ],
)
def test_failed_activation_check_skips_work_but_finalizes(
    monkeypatch, is_active, reason: str
) -> None:
    monkeypatch.setattr(
        "micboard.services.sync.discovery_run_lifecycle.ManufacturerActivationService.is_active",
        is_active,
    )
    claims = _claimed()

    outcome, calls = _run(claims)

    assert outcome.status is ClaimedRunStatus.FINALIZED
    assert calls == []
    assert outcome.summary.errors == [reason]
    assert claims.finalized_with == [outcome.summary]


@pytest.mark.usefixtures("active")
def test_finalize_exception_and_expired_claim_are_reported() -> None:
    failed, _ = _run(
        FakeClaims(
            claim=(ManufacturerFactory.build(pk=7), SimpleNamespace(pk=1)),
            finalize_error=RuntimeError("db"),
        )
    )
    expired, _ = _run(
        FakeClaims(
            claim=(ManufacturerFactory.build(pk=7), SimpleNamespace(pk=1)),
            finalized=False,
        )
    )

    assert failed.status is ClaimedRunStatus.FINALIZE_FAILED
    assert failed.work_completed
    assert expired.status is ClaimedRunStatus.CLAIM_EXPIRED
    assert expired.work_completed
