"""Contracts for collision-safe release CalVer calculation."""

from __future__ import annotations

import datetime as dt

import pytest

from scripts.calculate_calver import CalVerError, calculate_next_calver, validate_calver

RELEASE_DATE = dt.date(2026, 7, 15)


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ((), "26.07.15.0"),
        (("v26.07.15.0",), "26.07.15.1"),
        (("v26.07.15.0", "v26.07.15.1"), "26.07.15.2"),
        (
            (
                "v26.07.15.0",
                "v26.07.15.1",
                "v26.07.15.4",
                "v26.07.15.invalid",
                "v2026.7.15.99",
            ),
            "26.07.15.5",
        ),
    ],
)
def test_calculate_next_calver_supports_same_day_releases(
    tags: tuple[str, ...],
    expected: str,
) -> None:
    """The first daily release is bare; later releases increment a numeric suffix."""
    assert calculate_next_calver(tags, release_date=RELEASE_DATE) == expected


@pytest.mark.parametrize("version", ["26.07.15.0", "26.07.15.1", "26.07.15.42"])
def test_validate_calver_accepts_base_and_positive_same_day_revisions(version: str) -> None:
    """Manual backfills may select a daily release or a positive same-day revision."""
    assert validate_calver(version) == version


@pytest.mark.parametrize(
    "version",
    ["2026.07.15", "26.7.15", "26.07.15", "26.07.15.-1", "26.07.15.beta"],
)
def test_validate_calver_rejects_ambiguous_or_malformed_versions(version: str) -> None:
    """A missing micro revision or negative revision is forbidden."""
    with pytest.raises(CalVerError, match=r"YY\.MM\.DD\.MICRO"):
        validate_calver(version)
