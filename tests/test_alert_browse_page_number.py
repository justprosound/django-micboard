"""Page-number normalization for the alert browse service."""

import pytest

from micboard.services.monitoring.alert_browse_service import AlertBrowseService


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (None, 1),
        ("", 1),
        ("not-a-page", 1),
        (object(), 1),
        ("0", 1),
        (-4, 1),
        ("3", 3),
        (7, 7),
    ],
)
def test_page_number_is_positive_and_tolerates_bad_input(page: object, expected: int) -> None:
    """Missing, unparseable and non-positive pages resolve to page 1."""
    assert AlertBrowseService._normalize_page_number(page) == expected
