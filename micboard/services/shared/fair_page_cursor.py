"""Fair, bounded pages over a queryset, resumed from a fail-open cache cursor.

Bounded background work (alert fanout, discovery, subscriptions, broadcasts, charger polling)
visits a large inventory a page at a time. A cursor kept in the cache says where the next page
starts, so every row is eventually reached. The cache is only an optimisation of fairness: any
outage or malformed value restarts from a fresh cursor and never fails the caller.

``CursorSpec`` describes one kind of cursor (value shape, timeout, log label); ``read_cursor``,
``write_cursor`` and ``clear_cursor`` persist it; ``fair_page`` and ``fair_page_rows`` select
one circular page starting after a cursor position.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from django.core.cache import caches
from django.db import models
from django.db.models import Case, IntegerField, Q, QuerySet, Value, When

from pydantic import BaseModel

from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

DEFAULT_CACHE_ALIAS = "default"
_BUCKET = "_fair_page_bucket"


@dataclass(frozen=True, slots=True)
class CursorSpec[CursorT]:
    """One kind of cursor: how it is validated, stored and named in logs."""

    label: str
    timeout: int
    fresh: Callable[[], CursorT]
    parse: Callable[[object], CursorT]
    dump: Callable[[CursorT], object] | None = None

    def serialize(self, cursor: CursorT) -> object:
        """Return the cache representation of ``cursor``; plain values are stored as they are."""
        if self.dump is None:
            return cursor
        return self.dump(cursor)


def _parse_position(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("A cursor position is a non-negative integer.")
    return value


def _parse_pair(value: object) -> tuple[int, int]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError("A composite cursor is a pair of positions.")
    first, second = value
    return _parse_position(first), _parse_position(second)


def _parse_flag(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("A flag cursor is a boolean.")
    return value


def position_cursor(label: str, *, timeout: int) -> CursorSpec[int]:
    """Return a spec for a non-negative integer position, such as the last visited pk."""
    return CursorSpec(label=label, timeout=timeout, fresh=lambda: 0, parse=_parse_position)


def pair_cursor(label: str, *, timeout: int) -> CursorSpec[tuple[int, int]]:
    """Return a spec for a composite position of two non-negative integers."""
    return CursorSpec(label=label, timeout=timeout, fresh=lambda: (0, 0), parse=_parse_pair)


def flag_cursor(label: str, *, timeout: int) -> CursorSpec[bool]:
    """Return a spec for an alternating boolean, false until first written."""
    return CursorSpec(label=label, timeout=timeout, fresh=lambda: False, parse=_parse_flag)


def model_cursor[StateT: BaseModel](
    label: str,
    *,
    timeout: int,
    model: type[StateT],
    fresh: Callable[[], StateT] | None = None,
    exclude_defaults: bool = False,
) -> CursorSpec[StateT]:
    """Return a spec for a pydantic state that is stored as a plain dict."""
    return CursorSpec(
        label=label,
        timeout=timeout,
        fresh=fresh or model,
        parse=model.model_validate,
        dump=lambda state: state.model_dump(exclude_defaults=exclude_defaults),
    )


def read_cursor[CursorT](
    spec: CursorSpec[CursorT],
    key: str,
    *,
    cache_alias: str = DEFAULT_CACHE_ALIAS,
) -> CursorT:
    """Return the cached cursor, or a fresh one when it is missing, malformed or unreadable."""
    try:
        value = caches[cache_alias].get(key)
    except Exception as exc:
        logger.exception(
            "Could not read %s at %s",
            spec.label,
            key,
            exc_info=sanitized_exception_info(exc),
        )
        return spec.fresh()
    if value is None:
        return spec.fresh()
    try:
        return spec.parse(value)
    except TypeError, ValueError:
        return spec.fresh()


def write_cursor[CursorT](
    spec: CursorSpec[CursorT],
    key: str,
    cursor: CursorT,
    *,
    cache_alias: str = DEFAULT_CACHE_ALIAS,
) -> None:
    """Persist a cursor with the spec's timeout, tolerating a cache outage."""
    try:
        caches[cache_alias].set(key, spec.serialize(cursor), timeout=spec.timeout)
    except Exception as exc:
        logger.exception(
            "Could not persist %s at %s",
            spec.label,
            key,
            exc_info=sanitized_exception_info(exc),
        )


def clear_cursor(
    spec: CursorSpec[Any],
    key: str,
    *,
    cache_alias: str = DEFAULT_CACHE_ALIAS,
) -> None:
    """Drop a cursor once its cycle is complete, tolerating a cache outage."""
    try:
        caches[cache_alias].delete(key)
    except Exception as exc:
        logger.exception(
            "Could not clear %s at %s",
            spec.label,
            key,
            exc_info=sanitized_exception_info(exc),
        )


def _window(
    queryset: QuerySet[Any],
    *,
    after_pk: int,
    limit: int,
    fields: Sequence[str] | None,
) -> tuple[list[Any], bool]:
    """Read the rows after ``after_pk``, then wrap to the start only if the page is short.

    Each read is a ``pk`` range ordered by ``pk`` with a ``limit + 1`` sentinel, so the database
    can stop early on the primary-key index instead of ordering the whole queryset.
    """

    def read(rows: QuerySet[Any], count: int) -> list[Any]:
        ordered = rows.order_by("pk")
        if fields is not None:
            ordered = ordered.values_list(*fields)
        return list(ordered[:count])

    head = read(queryset.filter(pk__gt=after_pk), limit + 1)
    if len(head) > limit:
        return head[:limit], True
    if after_pk <= 0:
        return head, False
    remaining = limit - len(head)
    tail = read(queryset.filter(pk__lte=after_pk), remaining + 1)
    return [*head, *tail[:remaining]], len(tail) > remaining


def fair_page[ModelT: models.Model](
    queryset: QuerySet[ModelT],
    *,
    after_pk: int,
    limit: int,
) -> tuple[list[ModelT], bool]:
    """Return at most ``limit`` rows circularly ordered by pk after ``after_pk``, and whether more remain."""
    return _window(queryset, after_pk=after_pk, limit=limit, fields=None)


def fair_page_rows(
    queryset: QuerySet[Any],
    *,
    after_pk: int,
    fields: Sequence[str],
    limit: int,
) -> tuple[list[tuple[Any, ...]], bool]:
    """Like ``fair_page`` but projects ``fields`` into tuples."""
    return _window(queryset, after_pk=after_pk, limit=limit, fields=fields)


def _bucketed[ModelT: models.Model](
    queryset: QuerySet[ModelT],
    *,
    after: Q,
    order_by: Sequence[str],
) -> QuerySet[ModelT]:
    """Order the rows past ``after`` first and the rest second, in one query."""
    bucket = Case(
        When(after, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    ordered: QuerySet[ModelT] = queryset.annotate(**{_BUCKET: bucket}).order_by(_BUCKET, *order_by)
    return ordered


def fair_composite_page[ModelT: models.Model](
    queryset: QuerySet[ModelT],
    *,
    after: Q,
    order_by: Sequence[str] = ("pk",),
    limit: int,
) -> tuple[list[ModelT], bool]:
    """Page a small, already-narrowed queryset in one query, whatever ``after`` expresses.

    A computed bucket cannot use a primary-key range, so reserve this for querysets bounded by
    an index on their own (one unit's assignments) and for composite positions a single pk range
    cannot express. Use ``fair_page`` for large or joined inventories.
    """
    rows = list(_bucketed(queryset, after=after, order_by=order_by)[: limit + 1])
    return rows[:limit], len(rows) > limit


def fair_composite_rows(
    queryset: QuerySet[Any],
    *,
    after: Q,
    order_by: Sequence[str],
    fields: Sequence[str],
    limit: int,
) -> tuple[list[tuple[Any, ...]], bool]:
    """Like ``fair_composite_page`` but projects ``fields`` into tuples."""
    ordered = _bucketed(queryset, after=after, order_by=order_by)
    rows = cast(list[tuple[Any, ...]], list(ordered.values_list(*fields)[: limit + 1]))
    return rows[:limit], len(rows) > limit
