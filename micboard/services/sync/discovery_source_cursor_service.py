"""Fair shared-cache cursors for bounded local discovery sources."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from hashlib import blake2s
from typing import Any, NamedTuple, cast

from django.core.cache import cache
from django.db.models import Case, IntegerField, QuerySet, Value, When

from micboard.discovery.limits import clamp_candidate_limit
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.sync.discovery_dtos import DiscoverySourcePage
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

DISCOVERY_SOURCE_CURSOR_TIMEOUT_SECONDS = 7 * 24 * 60 * 60


class DiscoverySource(NamedTuple):
    """Internal description of one string-valued discovery queryset."""

    name: str
    queryset: QuerySet[Any]
    value_field: str


class DiscoverySourceCursorService:
    """Read fair cyclic pages without making discovery cache-dependent."""

    @classmethod
    def rotating_page(
        cls,
        manufacturer: Manufacturer,
        *,
        group: str,
        source: DiscoverySource,
        limit: int,
    ) -> DiscoverySourcePage:
        """Return one PK-ordered circular page and its full-source completeness."""
        page_limit = clamp_candidate_limit(limit)
        if page_limit == 0:
            return DiscoverySourcePage(
                sources_complete=not source.queryset.exists(),
            )

        cursor_key = cls._cursor_key(manufacturer, group=group, source=source.name)
        cursor = cls._read_cursor(cursor_key)
        rows = cast(
            list[tuple[int, object]],
            list(
                source.queryset.annotate(
                    _discovery_cursor_bucket=Case(
                        When(pk__gt=cursor, then=Value(0)),
                        default=Value(1),
                        output_field=IntegerField(),
                    )
                )
                .order_by("_discovery_cursor_bucket", "pk")
                .values_list("pk", source.value_field)[: page_limit + 1]
            ),
        )
        selected = rows[:page_limit]
        if selected:
            cls._write_cursor(cursor_key, selected[-1][0])
        return DiscoverySourcePage(
            values=[str(value) for _pk, value in selected],
            sources_complete=len(rows) <= page_limit,
        )

    @classmethod
    def rotating_pages(
        cls,
        manufacturer: Manufacturer,
        *,
        group: str,
        sources: Sequence[DiscoverySource],
        limit: int,
    ) -> dict[str, DiscoverySourcePage]:
        """Share one hard budget fairly across enabled sources and rotate priority."""
        page_limit = clamp_candidate_limit(limit)
        if not sources:
            return {}

        bounded_sizes = {
            source.name: cls._bounded_size(source.queryset, limit=page_limit) for source in sources
        }
        if page_limit == 0:
            return {
                source.name: DiscoverySourcePage(
                    sources_complete=bounded_sizes[source.name] == 0,
                )
                for source in sources
            }

        priority_key = cls._cursor_key(manufacturer, group=group, source="priority")
        start_index = cls._read_cursor(priority_key) % len(sources)
        ordered_sources = [*sources[start_index:], *sources[:start_index]]
        allocations = cls._allocate_budget(
            ordered_sources,
            bounded_sizes=bounded_sizes,
            limit=page_limit,
        )
        pages = {
            source.name: (
                cls.rotating_page(
                    manufacturer,
                    group=group,
                    source=source,
                    limit=allocations[source.name],
                )
                if allocations[source.name]
                else DiscoverySourcePage(
                    sources_complete=bounded_sizes[source.name] == 0,
                )
            )
            for source in ordered_sources
        }
        if any(page.values for page in pages.values()):
            cls._write_cursor(priority_key, (start_index + 1) % len(sources))
        return pages

    @staticmethod
    def _allocate_budget(
        ordered_sources: Sequence[DiscoverySource],
        *,
        bounded_sizes: dict[str, int],
        limit: int,
    ) -> dict[str, int]:
        """Round-robin an exact shared budget while reclaiming empty-source capacity."""
        allocations = {source.name: 0 for source in ordered_sources}
        remaining = limit
        while remaining:
            advanced = False
            for source in ordered_sources:
                if allocations[source.name] >= bounded_sizes[source.name]:
                    continue
                allocations[source.name] += 1
                remaining -= 1
                advanced = True
                if remaining == 0:
                    break
            if not advanced:
                break
        return allocations

    @staticmethod
    def _bounded_size(queryset: QuerySet[Any], *, limit: int) -> int:
        """Count no more than one page plus its overflow sentinel."""
        if limit == 0:
            return int(queryset.exists())
        return queryset.order_by().values("pk")[: limit + 1].count()

    @staticmethod
    def _cursor_key(
        manufacturer: Manufacturer,
        *,
        group: str,
        source: str,
    ) -> str:
        """Build an isolated cursor key that resets if manufacturer identity changes."""
        identity = blake2s(
            f"{manufacturer.pk}:{manufacturer.code}".encode(),
            digest_size=8,
        ).hexdigest()
        return f"micboard:discovery-source-cursor:v1:{identity}:{group}:{source}"

    @staticmethod
    def _read_cursor(key: str) -> int:
        """Read a validated cursor, defaulting safely during cache outages."""
        try:
            value = cache.get(key, 0)
        except Exception as exc:
            logger.exception(
                "Could not read a discovery source cursor",
                exc_info=sanitized_exception_info(exc),
            )
            return 0
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return 0
        return value

    @staticmethod
    def _write_cursor(key: str, value: int) -> None:
        """Persist a cursor without making discovery depend on cache availability."""
        try:
            cache.set(
                key,
                value,
                timeout=DISCOVERY_SOURCE_CURSOR_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.exception(
                "Could not persist a discovery source cursor",
                exc_info=sanitized_exception_info(exc),
            )
