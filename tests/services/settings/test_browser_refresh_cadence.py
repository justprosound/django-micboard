"""How often each browser surface re-polls the server, and who decides that.

Every live Micboard surface refreshes by short-polling over ordinary HTTP, so the poll
interval multiplied by the number of open tabs is the whole request volume a deployment's
reverse proxy carries. That number therefore has to be reachable from host settings rather
than from markup, and it has to be bounded at both ends so that neither a typo nor a stored
value can storm the proxy or stall a surface for an hour.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import override_settings

import pytest

from micboard.services.settings.browser_refresh_service import (
    BROWSER_REFRESH_SURFACES,
    MAX_REFRESH_INTERVAL_SECONDS,
    MIN_REFRESH_INTERVAL_SECONDS,
    browser_refresh_cadence,
)

TEMPLATE_ROOT = Path(__file__).resolve().parents[3] / "micboard" / "templates"


def test_each_surface_has_a_default_a_deployer_never_has_to_supply() -> None:
    """Out of the box every surface resolves to the interval Micboard has always used."""
    assert browser_refresh_cadence.seconds_for("alerts") == 5
    assert browser_refresh_cadence.seconds_for("assignments") == 5
    assert browser_refresh_cadence.seconds_for("chargers") == 10
    assert browser_refresh_cadence.seconds_for("kiosk_heartbeat") == 30


@override_settings(MICBOARD_CONFIG={"REFRESH_INTERVAL_ALERTS": 60})
def test_a_host_can_slow_one_surface_without_touching_the_others() -> None:
    """Proxy pressure is usually one busy page, so the knob is per surface."""
    assert browser_refresh_cadence.seconds_for("alerts") == 60
    assert browser_refresh_cadence.seconds_for("assignments") == 5


@override_settings(MICBOARD_CONFIG={"REFRESH_INTERVAL_ALERTS": 0})
def test_an_interval_below_the_floor_is_raised_to_it() -> None:
    """A zero or negative interval would poll as fast as the browser can issue requests."""
    assert browser_refresh_cadence.seconds_for("alerts") == MIN_REFRESH_INTERVAL_SECONDS


@override_settings(MICBOARD_CONFIG={"REFRESH_INTERVAL_CHARGERS": 999_999})
def test_an_interval_above_the_ceiling_is_lowered_to_it() -> None:
    """Past an hour a browser timer is effectively off, which hides staleness instead."""
    assert browser_refresh_cadence.seconds_for("chargers") == MAX_REFRESH_INTERVAL_SECONDS


@override_settings(MICBOARD_CONFIG={"REFRESH_INTERVAL_ASSIGNMENTS": "not a number"})
def test_an_unusable_value_falls_back_to_the_default_rather_than_breaking_the_page() -> None:
    """A malformed interval must not render `hx-trigger="every s"` into the markup."""
    assert browser_refresh_cadence.seconds_for("assignments") == 5


def test_milliseconds_are_derived_from_the_same_bounded_seconds() -> None:
    """The kiosk heartbeat is a JavaScript timer, so it needs the same number in ms."""
    assert browser_refresh_cadence.milliseconds_for("kiosk_heartbeat") == 30_000


def test_an_unknown_surface_is_a_programming_error() -> None:
    """Surfaces are declared here, not invented at a call site or in a template."""
    with pytest.raises(ValueError, match="unknown_surface"):
        browser_refresh_cadence.seconds_for("unknown_surface")


def test_no_template_hardcodes_its_own_poll_interval() -> None:
    """The point of the module is that markup stops declaring cadence.

    A literal interval in a template is invisible to settings and to this module, so it
    silently reintroduces the problem for whichever surface reintroduces it.
    """
    literal_interval = re.compile(r'hx-trigger="every (?!\{\{)')
    offenders = [
        f"{path.relative_to(TEMPLATE_ROOT)}:{number}"
        for path in TEMPLATE_ROOT.rglob("*.html")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if literal_interval.search(line)
    ]
    assert offenders == [], f"templates declaring a literal poll interval: {offenders}"


def test_every_declared_surface_resolves() -> None:
    """The declaration table is the interface, so nothing in it may be unresolvable."""
    for surface in BROWSER_REFRESH_SURFACES:
        assert browser_refresh_cadence.seconds_for(surface) >= MIN_REFRESH_INTERVAL_SECONDS


@override_settings(MICBOARD_CONFIG={"REFRESH_INTERVAL_ALERTS": float("inf")})
def test_a_non_finite_interval_falls_back_instead_of_raising() -> None:
    """`int(float("inf"))` raises `OverflowError`, which would break the page.

    `MICBOARD_CONFIG` is host-supplied and unvalidated, so an unusable value has to leave
    the surface rendering at its default rate rather than fail the request.
    """
    assert browser_refresh_cadence.seconds_for("alerts") == 5


@override_settings(MICBOARD_CONFIG={"REFRESH_INTERVAL_ALERTS": float("nan")})
def test_a_nan_interval_falls_back_instead_of_raising() -> None:
    """`int(float("nan"))` raises `ValueError`; the surface still has to render."""
    assert browser_refresh_cadence.seconds_for("alerts") == 5


@pytest.mark.parametrize(("configured", "expected"), [(0.5, 5), (5.7, 5), (12.0, 12)])
def test_a_fractional_interval_is_read_as_a_typo_not_as_truncation(
    configured: float,
    expected: int,
) -> None:
    """`int()` would silently truncate, turning `0.5` into the fastest allowed poll.

    A fractional interval is far more likely to be a mistake than a request to truncate, so
    it falls back to the default. A float that is already whole is used as written.
    """
    with override_settings(MICBOARD_CONFIG={"REFRESH_INTERVAL_ALERTS": configured}):
        assert browser_refresh_cadence.seconds_for("alerts") == expected


@override_settings(MICBOARD_CONFIG={"REFRESH_INTERVAL_ALERTS": "30"})
def test_a_numeric_string_is_still_accepted() -> None:
    """Environment-derived configuration arrives as a string and must keep working."""
    assert browser_refresh_cadence.seconds_for("alerts") == 30
