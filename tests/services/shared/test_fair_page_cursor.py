"""The fair-page cursor: durable, fail-open rotation over a bounded, ordered page."""

from typing import Any
from unittest.mock import MagicMock, patch

from django.core.cache import caches
from django.db.models import Q

import pytest
from pydantic import BaseModel, Field

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.shared import fair_page_cursor
from micboard.services.shared.fair_page_cursor import (
    CursorSpec,
    clear_cursor,
    fair_composite_page,
    fair_composite_rows,
    fair_page,
    fair_page_rows,
    flag_cursor,
    model_cursor,
    pair_cursor,
    position_cursor,
    read_cursor,
    write_cursor,
)
from tests.factories.hardware import WirelessChassisFactory

TIMEOUT = 60


class _State(BaseModel):
    after_id: int = Field(default=0, ge=0)


def _manufacturers(count: int) -> list[Manufacturer]:
    return [
        Manufacturer.objects.create(code=f"fair-{index}", name=f"Fair {index}")
        for index in range(count)
    ]


def _codes(rows: list[Manufacturer]) -> list[str]:
    return [row.code for row in rows]


def test_cursor_round_trips_through_the_cache_with_its_timeout() -> None:
    spec = position_cursor("test cursor", timeout=TIMEOUT)
    backend = MagicMock()
    backend.get.return_value = 7
    handler = MagicMock()
    handler.__getitem__.return_value = backend

    with patch.object(fair_page_cursor, "caches", handler):
        assert read_cursor(spec, "k") == 7
        write_cursor(spec, "k", 9)
        clear_cursor(spec, "k")

    backend.get.assert_called_once_with("k")
    backend.set.assert_called_once_with("k", 9, timeout=TIMEOUT)
    backend.delete.assert_called_once_with("k")


def test_cache_alias_selects_the_backend() -> None:
    spec = position_cursor("test cursor", timeout=TIMEOUT)
    handler = MagicMock()
    handler.__getitem__.return_value.get.return_value = 3

    with patch.object(fair_page_cursor, "caches", handler):
        assert read_cursor(spec, "k", cache_alias="realtime") == 3

    handler.__getitem__.assert_called_once_with("realtime")


@pytest.mark.parametrize(
    ("spec", "fresh"),
    [
        (position_cursor("position", timeout=TIMEOUT), 0),
        (pair_cursor("pair", timeout=TIMEOUT), (0, 0)),
        (flag_cursor("flag", timeout=TIMEOUT), False),
        (model_cursor("model", timeout=TIMEOUT, model=_State), _State()),
    ],
)
def test_cache_outage_is_fail_open_and_redacted(
    spec: CursorSpec[Any],
    fresh: object,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "redis://private-credential"
    backend = MagicMock()
    backend.get.side_effect = RuntimeError(secret)
    backend.set.side_effect = RuntimeError(secret)
    backend.delete.side_effect = RuntimeError(secret)
    handler = MagicMock()
    handler.__getitem__.return_value = backend

    with patch.object(fair_page_cursor, "caches", handler), caplog.at_level("ERROR"):
        assert read_cursor(spec, "k") == fresh
        write_cursor(spec, "k", fresh)
        clear_cursor(spec, "k")

    assert secret not in caplog.text
    assert caplog.text.count("Could not") == 3


@pytest.mark.parametrize(
    ("spec", "invalid", "fresh"),
    [
        (position_cursor("position", timeout=TIMEOUT), True, 0),
        (position_cursor("position", timeout=TIMEOUT), -1, 0),
        (position_cursor("position", timeout=TIMEOUT), "3", 0),
        (pair_cursor("pair", timeout=TIMEOUT), (True, 0), (0, 0)),
        (pair_cursor("pair", timeout=TIMEOUT), (1, 2, 3), (0, 0)),
        (pair_cursor("pair", timeout=TIMEOUT), 5, (0, 0)),
        (flag_cursor("flag", timeout=TIMEOUT), 1, False),
        (model_cursor("model", timeout=TIMEOUT, model=_State), {"after_id": -1}, _State()),
        (model_cursor("model", timeout=TIMEOUT, model=_State), "junk", _State()),
    ],
)
def test_invalid_cached_value_resets_to_a_fresh_cursor(
    spec: CursorSpec[Any],
    invalid: object,
    fresh: object,
) -> None:
    key = "fair-page-invalid"
    caches["default"].set(key, invalid)
    try:
        assert read_cursor(spec, key) == fresh
    finally:
        caches["default"].delete(key)


def test_missing_cached_value_is_a_fresh_cursor() -> None:
    spec = pair_cursor("pair", timeout=TIMEOUT)
    assert read_cursor(spec, "fair-page-never-written") == (0, 0)


def test_model_cursor_dump_options_are_applied() -> None:
    spec = model_cursor("model", timeout=TIMEOUT, model=_State, exclude_defaults=True)
    key = "fair-page-model"
    try:
        write_cursor(spec, key, _State(after_id=0))
        assert caches["default"].get(key) == {}
        write_cursor(spec, key, _State(after_id=4))
        assert read_cursor(spec, key) == _State(after_id=4)
    finally:
        caches["default"].delete(key)


@pytest.mark.django_db
def test_page_rotates_circularly_by_primary_key() -> None:
    rows = _manufacturers(5)
    queryset = Manufacturer.objects.filter(pk__in=[row.pk for row in rows])
    cursor = 0
    seen: list[list[str]] = []
    truncations: list[bool] = []
    for _ in range(4):
        page, truncated = fair_page(queryset, after_pk=cursor, limit=2)
        seen.append(_codes(page))
        truncations.append(truncated)
        cursor = page[-1].pk

    assert seen == [
        ["fair-0", "fair-1"],
        ["fair-2", "fair-3"],
        ["fair-4", "fair-0"],
        ["fair-1", "fair-2"],
    ]
    assert truncations == [True, True, True, True]


@pytest.mark.django_db
def test_page_is_bounded_and_reports_completeness() -> None:
    rows = _manufacturers(3)
    queryset = Manufacturer.objects.filter(pk__in=[row.pk for row in rows])

    page, truncated = fair_page(queryset, after_pk=rows[0].pk, limit=3)

    assert _codes(page) == ["fair-1", "fair-2", "fair-0"]
    assert truncated is False
    assert fair_page(queryset, after_pk=0, limit=0) == ([], True)
    assert fair_page(queryset.none(), after_pk=0, limit=2) == ([], False)


@pytest.mark.django_db
def test_page_resumes_after_the_cursor_row_is_deleted() -> None:
    rows = _manufacturers(4)
    queryset = Manufacturer.objects.filter(pk__in=[row.pk for row in rows])
    cursor = rows[1].pk
    rows[1].delete()

    page, truncated = fair_page(queryset, after_pk=cursor, limit=2)
    assert _codes(page) == ["fair-2", "fair-3"]
    assert truncated is True

    page, truncated = fair_page(queryset, after_pk=rows[3].pk + 100, limit=2)
    assert _codes(page) == ["fair-0", "fair-2"]
    assert truncated is True


@pytest.mark.django_db
def test_page_over_a_joined_distinct_queryset_does_not_repeat_rows(
    django_assert_num_queries,
) -> None:
    rows = _manufacturers(3)
    for row in rows:
        WirelessChassisFactory(manufacturer=row)
        WirelessChassisFactory(manufacturer=row)
    queryset = Manufacturer.objects.filter(
        pk__in=[row.pk for row in rows],
        wirelesschassis__isnull=False,
    ).distinct()

    with django_assert_num_queries(1):
        page, truncated = fair_page(queryset, after_pk=0, limit=2)
    assert _codes(page) == ["fair-0", "fair-1"]
    assert truncated is True

    with django_assert_num_queries(2):
        page, truncated = fair_page(queryset, after_pk=rows[1].pk, limit=3)
    assert _codes(page) == ["fair-2", "fair-0", "fair-1"]
    assert truncated is False


@pytest.mark.django_db
def test_page_rows_project_requested_fields_in_rotation_order() -> None:
    rows = _manufacturers(3)
    queryset = Manufacturer.objects.filter(pk__in=[row.pk for row in rows])

    page, truncated = fair_page_rows(
        queryset,
        after_pk=rows[1].pk,
        fields=("pk", "code"),
        limit=2,
    )

    assert page == [(rows[2].pk, "fair-2"), (rows[0].pk, "fair-0")]
    assert truncated is True


@pytest.mark.django_db
def test_composite_rows_rotate_past_a_two_part_position() -> None:
    rows = _manufacturers(3)
    queryset = Manufacturer.objects.filter(pk__in=[row.pk for row in rows])
    after = Q(pk__gt=rows[1].pk) | Q(pk=rows[1].pk, name__gt="Fair 1")

    page, truncated = fair_composite_rows(
        queryset,
        after=after,
        order_by=("pk", "name"),
        fields=("pk", "name"),
        limit=2,
    )

    assert page == [(rows[2].pk, "Fair 2"), (rows[0].pk, "Fair 0")]
    assert truncated is True


@pytest.mark.django_db
def test_composite_page_rotates_instances_in_one_query(django_assert_num_queries) -> None:
    rows = _manufacturers(3)
    queryset = Manufacturer.objects.filter(pk__in=[row.pk for row in rows])

    with django_assert_num_queries(1):
        page, truncated = fair_composite_page(queryset, after=Q(pk__gt=rows[1].pk), limit=3)

    assert _codes(page) == ["fair-2", "fair-0", "fair-1"]
    assert truncated is False
